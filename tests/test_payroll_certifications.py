from datetime import date,datetime
from decimal import Decimal
from importlib.util import spec_from_file_location,module_from_spec
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
import payroll_certification_repository as repository
import employee_repository as employees
import payroll_repository as compensation


class CertificationTests(unittest.TestCase):
    def test_production_has_no_source_authority_adapter(self):
        self.assertIsNone(repository.authoritative_evidence({},7))

    def test_supporting_references_are_not_placeholders(self):
        for value in ('','pending','n/a','x'*256,None):
            with self.assertRaises(ValueError):repository.reference(value,'Evidence')
        self.assertEqual(repository.reference(' HR-001 ','Evidence'),'HR-001')

    def test_date_validation_and_calendar_limits(self):
        for value in ('2028-02-30','0000-01-01','20280229',datetime(2028,2,29)):
            with self.assertRaises(ValueError):repository.optional_date(value,'Coverage')
        self.assertEqual(repository.optional_date('2028-02-29','Coverage'),date(2028,2,29))
        dates=repository.scheduled_dates(dict(start_date=date(9999,12,16),end_date=date(9999,12,31)))
        self.assertEqual(dates[-1],'9999-12-31')

    def test_digest_is_order_independent_and_material(self):
        self.assertEqual(repository.digest(dict(b=Decimal('1.00'),a=date(2028,1,1))),repository.digest(dict(a=date(2028,1,1),b=Decimal('1'))))
        self.assertNotEqual(repository.digest(dict(amount=Decimal('1'))),repository.digest(dict(amount=Decimal('2'))))
        self.assertEqual(repository.revision_token(dict(id=1)),repository.revision_token(dict(id=1,source_stale=True)))

    def test_stale_tokens_fail(self):
        row=dict(id=1)
        with self.assertRaisesRegex(ValueError,'changed'):repository._expected(row,repository.digest(dict(id=2)))

    def test_profile_edit_does_not_lock_or_overwrite_eligibility(self):
        conn=Mock();cursor=conn.cursor.return_value;cursor.fetchone.return_value=(date(2020,1,1),'Active')
        with patch.object(employees,'get_connection',return_value=conn),patch.object(employees,'lock_payroll_inputs') as guard:
            employees.update_employee(9,'E-9',None,'Synthetic',None,'Employee',None,None,None,'2020-01-01','Active')
            guard.assert_not_called()
        update=cursor.execute.call_args_list[-1].args[0]
        self.assertNotIn('hire_date',update);self.assertNotIn('employment_status',update)

    def test_material_source_edit_locks_guard_before_write(self):
        for module,operation,previous in (
            (employees,lambda:employees.update_employee(9,'E-9',None,'Synthetic',None,'Employee',None,None,None,'2021-01-01','Active'),(date(2020,1,1),'Active')),
            (compensation,lambda:compensation.update_employee_compensation(1,'MONTHLY','2000','2020-01-01',None,7),('MONTHLY',Decimal('1000'),date(2020,1,1)))):
            conn=Mock();cursor=conn.cursor.return_value;cursor.fetchone.return_value=previous
            with patch.object(module,'get_connection',return_value=conn),patch.object(module,'lock_payroll_inputs') as guard:
                operation();guard.assert_called_once_with(cursor)
            conn.start_transaction.assert_called_once();conn.commit.assert_called_once()

    def test_revocation_does_not_require_valid_policy_or_cutoff(self):
        cursor=Mock();cursor.fetchone.return_value=dict(payroll_period_id=1,status='PAID',policy_version_id=None)
        self.assertEqual(repository._period(cursor,1,False)['status'],'PAID')
        cursor.execute.assert_called_once()

    def test_migration_007_import_and_transaction_safety(self):
        spec=spec_from_file_location('unit007',Path(__file__).resolve().parents[1]/'database/migrations/007_payroll_correction_references.py')
        module=module_from_spec(spec)
        with patch('mysql.connector.connect') as connect,patch('dotenv.load_dotenv') as dotenv:
            spec.loader.exec_module(module);connect.assert_not_called();dotenv.assert_not_called()
        conn=Mock(in_transaction=True)
        with self.assertRaises(RuntimeError):module.upgrade(conn)
        conn.cursor.assert_not_called()
