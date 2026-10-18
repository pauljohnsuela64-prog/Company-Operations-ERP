"""Migration import, definition and SQL-normalization contracts without databases."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


def load_migration():
    spec = spec_from_file_location('policy_migration',
        Path(__file__).resolve().parents[1]/'database/migrations/005_payroll_policy.py')
    migration = module_from_spec(spec); spec.loader.exec_module(migration)
    return migration


class PolicyMigrationTests(unittest.TestCase):
    def test_import_never_connects_or_reads_configuration(self):
        with patch('mysql.connector.connect') as connect, patch('dotenv.load_dotenv') as dotenv:
            load_migration()
            connect.assert_not_called(); dotenv.assert_not_called()

    def test_normalization_keeps_literals_and_expression_grouping(self):
        migration = load_migration(); normalize = migration._normal_sql
        self.assertEqual(normalize('((`a` > 0))'), normalize('a > 0'))
        self.assertNotEqual(normalize('(a AND b) OR c'), normalize('a AND (b OR c)'))
        self.assertNotEqual(normalize("x = 'BLOCK'"), normalize("x = 'block'"))
        self.assertNotEqual(normalize('SELECT a FROM b'), normalize('SELECTa FROMb'))

    def test_check_comparison_preserves_and_or_precedence(self):
        normalize = load_migration()._normal_check
        self.assertEqual(normalize('a > 0 AND b > 0'), normalize('((`a` > 0) and (`b` > 0))'))
        self.assertNotEqual(normalize('(a AND b) OR c'), normalize('a AND (b OR c)'))

    def test_json_vocabulary_has_no_open_object_properties(self):
        for schema in load_migration().JSON_RULES.values():
            if schema['type'] == 'object':
                self.assertFalse(schema['additionalProperties'])
                self.assertEqual(set(schema['required']), set(schema['properties']))
            else:
                self.assertEqual(schema['maxItems'], 1)

    def test_enum_literal_case_is_part_of_the_column_contract(self):
        actual = dict(COLUMN_TYPE="enum('a','b')", IS_NULLABLE='YES', COLUMN_DEFAULT=None,
                      EXTRA='', GENERATION_EXPRESSION='', CHARACTER_SET_NAME='ascii', COLLATION_NAME='ascii_bin')
        with self.assertRaisesRegex(RuntimeError, 'Incompatible column'):
            load_migration()._verify_column('payroll_periods', 'cutoff_code',
                "ENUM('A','B') CHARACTER SET ascii COLLATE ascii_bin NULL", actual, explicit_charset=True)

    def test_existing_transaction_is_never_committed_by_migration(self):
        connection = Mock(in_transaction=True)
        with self.assertRaisesRegex(RuntimeError, 'fresh migration connection'):
            load_migration().upgrade(connection)
        connection.commit.assert_not_called(); connection.cursor.assert_not_called()
