"""No application wiring: explicit-only migration import and schema comparison."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class LifecycleMigrationTests(unittest.TestCase):
    def load_migration(self):
        path=Path(__file__).resolve().parents[1]/'database/migrations/009_hr_employment_lifecycle.py'
        spec=importlib.util.spec_from_file_location('inert_hr009',path)
        module=importlib.util.module_from_spec(spec)
        with patch('mysql.connector.connect',side_effect=AssertionError('No implicit connection')), \
             patch('dotenv.load_dotenv',side_effect=AssertionError('No environment loading')):
            spec.loader.exec_module(module)
        return module

    def test_inert_import_and_transaction_rejection(self):
        migration=self.load_migration()
        with self.assertRaises(RuntimeError):migration.upgrade(SimpleNamespace(in_transaction=True))

    def test_schema_comparison_preserves_grouping_case_and_operators(self):
        canonical=self.load_migration().canonical
        self.assertEqual(canonical("((`revision` >= 1))"),canonical('revision>=1'))
        self.assertEqual(canonical("source_type = _utf8mb4\\'DOCUMENT\\'"),canonical("source_type='DOCUMENT'"))
        for left,right in [("x='HIRE'","x='hire'"),('x>=1','x>1'),
                           ('(a or b) and c','a or (b and c)'),('x in (0,1)','x in (0,1,2)')]:
            self.assertNotEqual(canonical(left),canonical(right))


if __name__=='__main__':unittest.main()
