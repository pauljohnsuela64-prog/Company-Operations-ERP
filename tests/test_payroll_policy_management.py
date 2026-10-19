from datetime import date, datetime, timezone
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import unittest
from unittest.mock import patch
from werkzeug.datastructures import MultiDict
import payroll_policy_validation as validation


def valid_policy():
    values=validation.initial_policy()
    values.update(policy_name='Synthetic Payroll',effective_from='2035-01-01')
    return values


class PolicyManagementTests(unittest.TestCase):
    def test_frozen_migration_vocabulary_matches_application(self):
        spec=spec_from_file_location('contract_005',Path(__file__).resolve().parents[1]/'database/migrations/005_payroll_policy.py')
        migration=module_from_spec(spec);spec.loader.exec_module(migration)
        self.assertEqual(validation.JSON_RULES,migration.JSON_RULES)

    def test_exact_name_and_date_boundaries(self):
        for day in ('1000-01-01','2035-02-16','9999-12-16'):
            values=valid_policy();values.update(policy_name='a'*100,effective_from=day)
            self.assertEqual(validation.policy_values(values)['effective_from'],date.fromisoformat(day))
        for field,value in [('policy_name','a'*101),('policy_name','  '),('effective_from','0001-01-01'),
                            ('effective_from','2035-02-29'),('effective_from','2035-01-02'),('effective_from',datetime.now())]:
            values=valid_policy();values[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validation.policy_values(values)

    def test_json_values_unknown_keys_duplicate_keys_and_types(self):
        for field,value in [('cutoff_rules','{"a_start":1,"a_start":1,"a_end":15,"b_start":16,"b_end":"MONTH_END"}'),
                ('cutoff_rules',dict(a_start=True,a_end=15,b_start=16,b_end='MONTH_END')),
                ('supported_pay_types','["HOURLY"]'),('payment_rules','{"mode":"MANUAL","sql":"anything"}'),
                ('attendance_rules','NaN'),('payment_rules','null'),('payment_rules','x'*4097),('full_cutoff_divisor',True),
                ('calculator_key','OTHER'),('currency_code','USD')]:
            values=valid_policy();values[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validation.policy_values(values)

    def test_forms_reject_duplicates_and_unexpected_actor_fields(self):
        data=validation.form_values(valid_policy())
        self.assertEqual(validation.parse_form(MultiDict(data))['policy_name'],'Synthetic Payroll')
        for extra in [('created_by','9'),('policy_name','Injected')]:
            form=MultiDict(data);form.add(*extra)
            with self.assertRaises(ValueError):validation.parse_form(form)

    def test_unresolved_and_approval_reference_validation(self):
        with self.assertRaisesRegex(ValueError,'UNRESOLVED'):validation.require_resolved(valid_policy())
        for reference in ('','  ','pending','N/A','---','x'*256):
            with self.assertRaises(ValueError):validation.approval_reference(reference)
        self.assertEqual(validation.approval_reference(' HR-001 '),'HR-001')

    def test_hash_is_order_independent_and_detects_material_changes(self):
        values=valid_policy();values.update(policy_version_id=1,version_number=2,approval_reference='HR-001')
        digest=validation.configuration_hash(values);values['configuration_hash']=digest
        validation.verify_configuration_hash(values)
        values['cutoff_rules']=dict(reversed(list(values['cutoff_rules'].items())))
        validation.verify_configuration_hash(values)
        values['policy_name']='Different approved name'
        with self.assertRaises(ValueError):validation.verify_configuration_hash(values)

    def test_explicit_company_timezone_and_midnight_boundary(self):
        with patch.object(validation,'datetime',wraps=datetime) as clock:
            clock.now.return_value=datetime(2026,10,18,16,0,tzinfo=timezone.utc)
            self.assertEqual(validation.company_today('Asia/Manila'),date(2026,10,19))
            self.assertEqual(validation.company_today('Etc/UTC'),date(2026,10,18))
        for zone in ('','Not/AZone',None):
            with self.assertRaises(ValueError):validation.company_today(zone)
