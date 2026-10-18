"""Freshness contracts and mandatory first-lock coverage without company DBs."""
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
import mysql.connector
from payroll_freshness import lock_payroll_inputs,verify_calculations

ROOT=Path(__file__).resolve().parents[1]


class PayrollFreshnessTests(unittest.TestCase):
    def test_guard_fails_closed_for_missing_upgrade_timeout_and_deadlock(self):
        cursor=Mock();cursor.fetchone.return_value=None
        with self.assertRaisesRegex(ValueError,'upgrade'):lock_payroll_inputs(cursor)
        for number in [1205,1213,1146]:
            cursor.execute.side_effect=mysql.connector.Error(errno=number,msg='Synthetic')
            with self.assertRaises(ValueError):lock_payroll_inputs(cursor)

    def test_legacy_and_changed_evidence_rejected(self):
        cursor=Mock()
        for version,digest in [(None,None),(99,'x'*64)]:
            cursor.fetchall.return_value=[dict(payroll_entry_id=1,calculation_input_version=version,calculation_input_hash=digest)]
            with self.assertRaisesRegex(ValueError,'unverified'):verify_calculations(cursor,1)
        cursor.fetchall.return_value=[dict(payroll_entry_id=1,calculation_input_version=1,calculation_input_hash='a'*64)]
        with patch('payroll_freshness.fingerprint',return_value='b'*64):
            with self.assertRaisesRegex(ValueError,'inputs or results changed'):verify_calculations(cursor,1)
        with patch('payroll_freshness.fingerprint',return_value='a'*64):verify_calculations(cursor,1)

    def test_all_participating_writers_lock_before_other_queries(self):
        expected={
            'attendance_repository.py':{'create_attendance_record','update_attendance_record'},
            'leave_repository.py':{'create_leave_type','update_leave_type','set_leave_type_active_status','create_leave_request','approve_leave_request','reject_leave_request','cancel_leave_request'},
            'payroll_period_repository.py':{'create_payroll_period','update_payroll_period','cancel_payroll_period'},
            'payroll_entry_repository.py':{'generate_payroll_entries'},
            'payroll_adjustment_repository.py':{'add_payroll_adjustment','delete_payroll_adjustment'},
            'payroll_calculation_repository.py':{'calculate_monthly_payroll_period'},
            'payroll_workflow_repository.py':{'submit_payroll_for_approval','return_payroll_to_draft','approve_payroll_period','mark_payroll_period_as_paid'},
        }
        for filename,names in expected.items():
            tree=ast.parse((ROOT/filename).read_text())
            for node in tree.body:
                if not isinstance(node,ast.FunctionDef) or node.name not in names:continue
                calls=sorted((n for n in ast.walk(node) if isinstance(n,ast.Call)),key=lambda n:n.lineno)
                guard=next(c for c in calls if ast.unparse(c.func)=='lock_payroll_inputs')
                start=next(c for c in calls if ast.unparse(c.func)=='connection.start_transaction')
                queries=[c for c in calls if ast.unparse(c.func)=='cursor.execute']
                self.assertLess(start.lineno,guard.lineno,(filename,node.name))
                self.assertTrue(all(guard.lineno<c.lineno for c in queries),(filename,node.name))

    def test_migration_import_never_connects(self):
        with patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')) as connect:
            spec=importlib.util.spec_from_file_location('safe_migration',ROOT/'database/migrations/004_payroll_freshness.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            connect.assert_not_called()
