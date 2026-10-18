"""Draft date invalidation is independent of the pending freshness migration."""
from datetime import date
import unittest
from unittest.mock import MagicMock,patch
import payroll_period_repository as repository


class PayrollPeriodInvalidationTests(unittest.TestCase):
    def setUp(self):
        self.connection=MagicMock();self.cursor=self.connection.cursor.return_value
        self.cursor.fetchone.return_value=dict(start_date=date(2026,2,2),end_date=date(2026,2,6),status='DRAFT')
        self.cursor.fetchall.return_value=[dict(payroll_entry_id=1,status='CALCULATED')]
        self.cursor.rowcount=1
        self.patch=patch.object(repository,'get_connection',return_value=self.connection)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.guard=patch.object(repository,'lock_payroll_inputs');self.guard.start();self.addCleanup(self.guard.stop)

    def update(self,end=date(2026,2,2)):
        return repository.update_payroll_period(1,'Synthetic',date(2026,2,2),end,date(2026,2,7),None,7)

    def test_date_edit_locks_parent_then_entries_and_clears_calculation(self):
        self.assertTrue(self.update())
        queries=[' '.join(call.args[0].split()) for call in self.cursor.execute.call_args_list]
        self.assertIn('FROM payroll_periods',queries[0]);self.assertIn('FOR UPDATE',queries[0])
        self.assertIn('FROM payroll_entries',queries[1]);self.assertIn('FOR UPDATE',queries[1])
        self.assertTrue(queries[2].startswith('UPDATE payroll_periods'))
        self.assertIn("status = 'DRAFT', calculated_by = NULL, calculated_at = NULL",queries[3])
        self.assertFalse(any('UPDATE employee_compensation' in query or 'DELETE' in query for query in queries))
        self.connection.start_transaction.assert_called_once();self.connection.commit.assert_called_once()

    def test_metadata_edit_does_not_invalidate(self):
        self.assertTrue(self.update(end=date(2026,2,6)))
        self.assertEqual(self.cursor.execute.call_count,2)

    def test_non_draft_or_missing_period_never_writes(self):
        for status in ['PROCESSING','APPROVED','PAID','CANCELLED',None]:
            self.cursor.reset_mock();self.connection.reset_mock()
            self.cursor.fetchone.return_value=None if status is None else dict(start_date=date(2026,2,2),end_date=date(2026,2,6),status=status)
            self.assertFalse(self.update())
            self.assertEqual(self.cursor.execute.call_count,1)
            self.connection.commit.assert_not_called();self.connection.rollback.assert_called_once()

    def test_finalized_child_in_inconsistent_draft_is_not_rewritten(self):
        for status in ['APPROVED','PAID']:
            self.cursor.fetchall.return_value=[dict(payroll_entry_id=1,status=status)]
            with self.assertRaisesRegex(ValueError,'history requires review'):self.update()
        self.connection.commit.assert_not_called()

    def test_commit_failure_rolls_back_and_closes(self):
        self.connection.commit.side_effect=RuntimeError('Synthetic commit failure')
        with self.assertRaises(RuntimeError):self.update()
        self.connection.rollback.assert_called_once();self.cursor.close.assert_called_once();self.connection.close.assert_called_once()
