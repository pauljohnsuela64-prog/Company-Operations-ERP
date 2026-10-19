"""Offline migration contracts. Database behavior is tested by the isolated smoke suite."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def load():
    spec=spec_from_file_location('test_006',Path(__file__).resolve().parents[1]/'database/migrations/006_payroll_certification.py')
    module=module_from_spec(spec);spec.loader.exec_module(module)
    return module


class CertificationMigrationTests(unittest.TestCase):
    def test_import_has_no_configuration_or_database_side_effects(self):
        with patch('mysql.connector.connect') as connect,patch('dotenv.load_dotenv') as dotenv:
            self.assertEqual(len(load().TABLES),4)
            connect.assert_not_called();dotenv.assert_not_called()

    def test_existing_transaction_is_never_committed(self):
        connection=Mock(in_transaction=True)
        with self.assertRaisesRegex(RuntimeError,'fresh migration connection'):load().upgrade(connection)
        connection.cursor.assert_not_called();connection.commit.assert_not_called()

    def test_history_foreign_keys_never_cascade(self):
        module=load()
        for manifest in (*module.TABLES.values(),*module.ADDITIONS.values()):
            for definition in manifest[2].values():self.assertEqual(definition[-2:],('RESTRICT','RESTRICT'))

    def test_normalization_preserves_logic_and_literals(self):
        normal=load()._normal_check
        self.assertEqual(normal('(a AND b) AND c'),normal('a AND (b AND c)'))
        self.assertNotEqual(normal('a AND (b OR c)'),normal('(a AND b) OR c'))
        self.assertNotEqual(normal("x='PHP'"),normal("x='php'"))

    def test_no_backfill_permission_seed_or_legacy_version_change(self):
        module=load()
        self.assertNotIn('payroll_input_guard',module.TABLES)
        self.assertEqual(module.ADDITIONS['payroll_entries'][0],[('current_calculation_evidence_id','BIGINT UNSIGNED NULL')])
        self.assertEqual(set(module.TABLES),{module.CERT,module.MEMBER,module.EVENT,module.EVIDENCE})

    def test_bounded_roster_calendar_and_payload(self):
        module=load()
        for schema in (module.ROSTER_SCHEMA,module.CALENDAR_SCHEMA,module.SCHEDULE_SCHEMA,module.PAYLOAD_SCHEMA):
            self.assertFalse(schema['additionalProperties'])
            self.assertEqual(set(schema['required']),set(schema['properties']))
        self.assertTrue(module.IDS['uniqueItems'])
        self.assertTrue(module.DATES['uniqueItems'])

    def test_sealing_has_atomic_business_events(self):
        module=load();table,event,timing,body=module.TRIGGERS['pcc_seal_events_006']
        self.assertEqual((table,event,timing),(module.CERT,'UPDATE','AFTER'))
        self.assertIn("'CERTIFY'",body);self.assertIn("'SUPERSEDE'",body)
        self.assertNotIn('audit_logs',body)
