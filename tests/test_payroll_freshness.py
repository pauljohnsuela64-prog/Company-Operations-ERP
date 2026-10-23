"""Evidence boundaries and writer participation without a real connection."""
import ast
import importlib.util
from datetime import date
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
import payroll_freshness as freshness


class EvidenceTests(unittest.TestCase):
    def test_migration_import_has_no_network_or_startup_ddl(self):
        root = Path(__file__).resolve().parents[1]
        with patch('mysql.connector.connect', side_effect=AssertionError('No company connection')) as connect:
            spec = importlib.util.spec_from_file_location('freshness_migration_test', root/'database/migrations/010_payroll_attendance_freshness.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            self.assertTrue(callable(module.migrate))
            connect.assert_not_called()

    def test_fresh_install_definitions_match_migration_constants(self):
        root = Path(__file__).resolve().parents[1]
        for filename, ddl in (('core_schema.sql',freshness.GUARD_DDL),
                              ('attendance_schema.sql',freshness.GENERATIONS_DDL),
                              ('payroll_calculation_schema.sql',freshness.SNAPSHOTS_DDL)):
            self.assertIn(ddl, (root/'database'/filename).read_text())
        schema=(root/'database/payroll_calculation_schema.sql').read_text()
        for name,kind in freshness.EVIDENCE_COLUMNS.items():
            self.assertIn('ADD COLUMN '+name+' '+kind.upper()+' NULL', schema)

    def test_work_dates_include_leap_and_maximum_date_without_overflow(self):
        self.assertEqual(list(freshness.work_dates(date(2024,2,28), date(2024,3,1))),
                         [date(2024,2,28), date(2024,2,29), date(2024,3,1)])
        self.assertEqual(list(freshness.work_dates(date(9999,12,31), date(9999,12,31))), [date(9999,12,31)])

    def test_guard_is_required_and_never_created_by_runtime(self):
        cursor = MagicMock(); cursor.fetchone.return_value = None
        with patch.object(freshness, 'inspect_structure'):
            with self.assertRaisesRegex(freshness.FreshnessError, 'coordination'):
                freshness.lock_guard(cursor)
        cursor.execute.assert_called_once_with('SELECT guard_id FROM payroll_attendance_guard WHERE guard_id=1 FOR UPDATE')

    def test_missing_or_nontransactional_storage_fails_closed(self):
        for row in (None, {'ENGINE': 'MyISAM'}):
            cursor = MagicMock(); cursor.fetchone.return_value = row
            with self.assertRaises(freshness.FreshnessError):
                freshness.inspect_structure(cursor, evidence=True)
            self.assertTrue(all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_move_keys_are_deduplicated_ordered_and_parameterized(self):
        cursor = MagicMock(); cursor.fetchone.side_effect = [None, (4,)]
        cursor.rowcount = 1
        keys = [(2,date(2026,1,5)), (1,date(2026,1,5)), (2,date(2026,1,5))]
        freshness.advance(cursor, keys)
        reads = [call.args[1] for call in cursor.execute.call_args_list if call.args[0].startswith('SELECT')]
        self.assertEqual(reads, [(1,date(2026,1,5)), (2,date(2026,1,5))])
        self.assertEqual(len(cursor.execute.call_args_list), 4)

    def test_exhaustion_never_attempts_increment_or_counter_reset(self):
        cursor = MagicMock(); cursor.fetchone.return_value = (freshness.MAX_GENERATION,)
        with self.assertRaisesRegex(freshness.FreshnessError, 'exhausted'):
            freshness.advance(cursor, [(1,date(2026,1,5))])
        self.assertEqual(cursor.execute.call_count, 1)

    def test_legacy_unknown_version_or_changed_scope_never_attests(self):
        for version, start in ((None,date(2026,1,5)), (2,date(2026,1,5)), (1,date(2026,1,6))):
            cursor = MagicMock()
            cursor.fetchall.return_value = [(1,7,version,start,date(2026,1,5))]
            with self.assertRaisesRegex(freshness.FreshnessError, 'unverified'):
                freshness.validate(cursor, 1, date(2026,1,5), date(2026,1,5), payment=True)
            self.assertEqual(cursor.execute.call_count, 1)

    def test_incomplete_wrong_employee_or_changed_generation_reject(self):
        for snapshots in ([], [(date(2026,1,5),8,1)], [(date(2026,1,5),7,1)]):
            cursor = MagicMock()
            cursor.fetchall.side_effect = [[(1,7,1,date(2026,1,5),date(2026,1,5))], snapshots]
            with patch.object(freshness, 'generations', return_value={date(2026,1,5):2}):
                with self.assertRaisesRegex(freshness.FreshnessError, 'changed'):
                    freshness.validate(cursor, 1, date(2026,1,5), date(2026,1,5))

    def test_absent_day_generation_zero_is_saved_but_does_not_remove_missing_day_policy(self):
        cursor = MagicMock()
        with patch.object(freshness, 'generations', return_value={}):
            freshness.save(cursor, 1,7,date(2026,1,5),date(2026,1,5))
        self.assertEqual(cursor.executemany.call_args.args[1], [(1,date(2026,1,5),7,0)])
        self.assertIn('attendance_evidence_version', cursor.execute.call_args.args[0])

    def test_all_payroll_mutators_coordinate_before_existing_business_locks(self):
        root = Path(__file__).resolve().parents[1]
        names = {
            'payroll_calculation_repository.py':['calculate_monthly_payroll_period'],
            'payroll_workflow_repository.py':['submit_payroll_for_approval','return_payroll_to_draft','approve_payroll_period','mark_payroll_period_as_paid'],
            'payroll_entry_repository.py':['generate_payroll_entries'],
            'payroll_adjustment_repository.py':['add_payroll_adjustment','delete_payroll_adjustment'],
            'payroll_period_repository.py':['create_payroll_period','update_payroll_period','cancel_payroll_period']}
        for filename, functions in names.items():
            tree = ast.parse((root/filename).read_text(encoding='utf-8-sig'))
            for function in functions:
                node = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name==function)
                calls = sorted((n for n in ast.walk(node) if isinstance(n, ast.Call)), key=lambda n:(n.lineno,n.col_offset))
                guard = next(n for n in calls if ast.unparse(n.func)=='freshness.lock_guard')
                # SQL and the existing schedule-lock helper must follow the guard.
                writes = [n for n in calls if ast.unparse(n.func) in ('cursor.execute','_lock_nonoverlapping_schedule')]
                self.assertTrue(all(n.lineno>guard.lineno for n in writes), function)
