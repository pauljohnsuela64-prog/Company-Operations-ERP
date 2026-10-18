from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

from finance_validation import money, EXPENSE_MAX, BUDGET_MAX, budget_values, expense_values
import expense_repository as expenses
import budget_repository as budgets


class FinanceValidationTests(unittest.TestCase):
    def test_exact_schema_boundaries(self):
        for value in ['0.01', '12', '1,234.56', '9999999999.99', Decimal('0.10')]:
            self.assertEqual(money(value), Decimal(str(value).replace(',', '')))
        self.assertEqual(money(BUDGET_MAX, maximum=BUDGET_MAX), BUDGET_MAX)
        with self.assertRaises(ValueError): money(BUDGET_MAX)

    def test_invalid_money_never_rounds(self):
        for value in ['NaN', 'sNaN', 'Infinity', '-Infinity', '0', '-1', '1.001', '1.000',
                      '10000000000', '1,2', '1e2', '', None, True, 0.1]:
            with self.subTest(value=value), self.assertRaises(ValueError): money(value)
        with self.assertRaises(ValueError): money('1000000000000', maximum=BUDGET_MAX)

    def test_bad_budget_input_opens_no_connection(self):
        for changes in [{'department_id': '-1'}, {'budget_year': 'NaN'}, {'budget_year': '10000'},
                        {'budget_amount': '1.001'}, {'budget_amount': 'Infinity'}, {'notes': 'x'*256}]:
            args = dict(department_id=1, budget_year=2026, budget_amount='1.00', notes=None)
            args.update(changes)
            for operation, extra in [(budgets.create_department_budget, dict(created_by=1)),
                                     (budgets.update_department_budget, dict(budget_id=1))]:
                with self.subTest(changes=changes), patch.object(budgets, 'get_connection') as connect:
                    with self.assertRaises(ValueError): operation(**args, **extra)
                    connect.assert_not_called()

    def test_bad_expense_input_opens_no_connection(self):
        for changes in [{'expense_date':'2026-02-30'}, {'expense_date':'0001-01-01'}, {'category_id':'1.0'},
                        {'supplier_id':2147483648}, {'amount':'NaN'}, {'amount':'1.001'},
                        {'description':''}, {'description':'x'*256}, {'reference_number':'x'*101},
                        {'notes':'x'*256}, {'payment_method':'WIRE'}]:
            args = dict(expense_date='2026-01-01', category_id=1, department_id=None, supplier_id=None,
                        purchase_order_id=None, description='Test', amount='1.00', reference_number=None,
                        payment_method=None, notes=None)
            args.update(changes)
            for operation, extra in [(expenses.create_expense, dict(created_by=1)),
                                     (expenses.update_expense, dict(expense_id=1))]:
                with self.subTest(changes=changes), patch.object(expenses, 'get_connection') as connect:
                    with self.assertRaises(ValueError): operation(**args, **extra)
                    connect.assert_not_called()

    def test_valid_calendar_and_optional_fields(self):
        self.assertEqual(budget_values('1', '2026', '1,000.00', ''), (1,2026,Decimal('1000'),None))
        self.assertEqual(expense_values('2024-02-29', '1', '', '', '', ' Test ', '0.01', '', '', '')[:2],
                         (date(2024,2,29),1))
