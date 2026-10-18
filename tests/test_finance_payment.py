"""Atomic payment failure boundaries without any database access."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch

import expense_repository as expenses


class AtomicPaymentTests(unittest.TestCase):
    def pay(self, rows, fail=None, changed=1):
        connection = MagicMock()
        cursor = connection.cursor.return_value
        cursor.fetchone.side_effect = rows
        cursor.rowcount = changed
        if fail:
            cursor.execute.side_effect = fail
        return connection, patch.object(expenses, 'get_connection', return_value=connection)

    @staticmethod
    def expense(**changes):
        return dict(status='APPROVED', amount=Decimal('0.20'), department_id=1,
                    expense_date=date(2026, 1, 1), **changes)

    def test_decimal_boundary_and_explicit_fresh_snapshot_isolation(self):
        connection, guard = self.pay([self.expense(), {'budget_amount': Decimal('0.30')},
                                      {'spent_amount': Decimal('0.10')}])
        with guard:
            self.assertTrue(expenses.mark_expense_as_paid(1))
        connection.start_transaction.assert_called_once_with(isolation_level='READ COMMITTED')
        queries = [c.args[0] for c in connection.cursor.return_value.execute.call_args_list]
        self.assertIn('FOR UPDATE', queries[0])
        self.assertIn('FROM department_budgets', queries[1])
        self.assertIn('FOR UPDATE', queries[1])
        self.assertIn('SUM(amount)', queries[2])
        self.assertNotIn('FOR UPDATE', queries[2])
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_rejected_payment_rolls_back_and_never_updates(self):
        for rows, message in [
            ([None], 'Expense not found'),
            ([dict(status='PAID')], 'Only approved'),
            ([self.expense(), None, {'department_name': 'Ops'}], 'Ops does not have a budget for 2026'),
            ([self.expense(), {'budget_amount': Decimal('0.29')}, {'spent_amount': Decimal('0.10')}], '\u20b10.01'),
        ]:
            with self.subTest(message=message):
                connection, guard = self.pay(rows)
                with guard, self.assertRaisesRegex(ValueError, message):
                    expenses.mark_expense_as_paid(1)
                connection.commit.assert_not_called()
                connection.rollback.assert_called_once()
                self.assertFalse(any('UPDATE expenses' in c.args[0] for c in connection.cursor.return_value.execute.call_args_list))

    def test_statement_and_commit_failures_roll_back_and_close(self):
        for stage in ['statement', 'commit']:
            connection, guard = self.pay([dict(status='APPROVED', amount=Decimal('1'), department_id=None)],
                                         RuntimeError('failed') if stage == 'statement' else None)
            if stage == 'commit':
                connection.commit.side_effect = RuntimeError('failed')
            with guard, self.assertRaisesRegex(RuntimeError, 'failed'):
                expenses.mark_expense_as_paid(1)
            connection.rollback.assert_called_once()
            connection.close.assert_called_once()
            connection.cursor.return_value.close.assert_called_once()

    def test_departmentless_preserves_policy_and_conditional_update_guard(self):
        for changed in [1, 0]:
            connection, guard = self.pay([dict(status='APPROVED', amount=Decimal('1'), department_id=None)], changed=changed)
            with guard:
                if changed:
                    self.assertTrue(expenses.mark_expense_as_paid(1))
                else:
                    with self.assertRaisesRegex(ValueError, 'Only approved'):
                        expenses.mark_expense_as_paid(1)
            self.assertFalse(any('department_budgets' in c.args[0] for c in connection.cursor.return_value.execute.call_args_list))
