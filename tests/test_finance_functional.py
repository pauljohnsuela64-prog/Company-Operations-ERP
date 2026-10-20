"""Finance form redisplay, budget permissions, years and exact usage boundaries."""
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
import importlib
import unittest
from unittest.mock import patch

from security_helpers import csrf_client, csrf_token_for, stamp_session, user_state


class FormValues(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.options, self.values, self.current = {}, {}, None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.current = attrs.get('name')
            self.options[self.current] = []
        elif tag == 'option' and self.current:
            self.options[self.current].append((attrs.get('value', ''), 'selected' in attrs))
        elif tag == 'input' and attrs.get('name'):
            self.values[attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'select':
            self.current = None

    def selected(self, name):
        options = self.options[name]
        selected = [value for value, chosen in options if chosen]
        assert len(selected) <= 1, (name, options)
        return selected[0] if selected else options[0][0]


class FinanceFunctionalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-finance-functional', ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state = user_state(permissions=['finance.view', 'finance.expenses.manage'])
        self.mock('get_authorization_state', side_effect=lambda _: self.state)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.audit = self.mock('create_audit_log')
        self.expense = dict(expense_id=41, expense_number='EXP-41', status='DRAFT',
                            expense_date=date(2026, 1, 1), category_id=1, department_id=1,
                            supplier_id=1, purchase_order_id=1, payment_method='CASH',
                            description='Saved', amount=Decimal('1.00'), reference_number='Saved', notes='Saved')
        self.mock('get_expense_by_id', return_value=self.expense)
        self.mock('get_active_expense_categories', return_value=[dict(category_id=1, category_code='A', category_name='A'), dict(category_id=2, category_code='B', category_name='B')])
        self.departments = [dict(department_id=i, department_code=str(i), department_name=str(i)) for i in [1, 2]]
        self.mock('get_active_departments', return_value=self.departments)
        self.mock('get_all_departments', return_value=self.departments)
        self.mock('get_active_suppliers', return_value=[dict(supplier_id=i, supplier_name=str(i)) for i in [1, 2]])
        self.mock('get_all_purchase_orders', return_value=[dict(purchase_order_id=i, po_number=str(i), status='DRAFT') for i in [1, 2]])
        self.budget = dict(budget_id=1, department_id=1, department_name='1', budget_year=2026,
                           budget_amount=Decimal('1000000.00'), spent_amount=Decimal('0.00'), remaining_amount=Decimal('1000000.00'))
        from budget_management import listing_values
        def budget_page(args,default_year):
            selected=listing_values(args,default_year)
            summary=dict(department_count=1,total_budget=self.budget['budget_amount'],total_spent=self.budget['spent_amount'],total_remaining=self.budget['remaining_amount'])
            return dict(records=[self.budget],summary=summary,total=1,pages=1,first=1,last=1,filters=selected)
        self.budgets = self.mock('get_department_budget_page',side_effect=budget_page)
        self.client = csrf_client(self.erp.app)
        with self.client.session_transaction() as sess:
            stamp_session(self.erp.app, sess, self.state)
        self.form = dict(expense_date='2026-02-03', category_id='2', department_id='2', supplier_id='2',
                         purchase_order_id='2', payment_method='CARD', description='Edited <text>',
                         amount='0', reference_number='REF', notes='Retained notes')

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.erp, name, **kwargs))

    def test_add_invalid_then_correct_keeps_all_selections_and_text(self):
        write = self.mock('create_expense', side_effect=[ValueError('Amount must be greater than zero.'), (41, 'EXP-41')])
        response = self.client.post('/finance/expenses/add', data=self.form)
        self.assertEqual(response.status_code, 200)
        fields = FormValues(response.get_data(as_text=True))
        for name in ['category_id', 'department_id', 'supplier_id', 'purchase_order_id', 'payment_method']:
            self.assertEqual(fields.selected(name), self.form[name])
        for name in ['expense_date', 'description', 'amount', 'reference_number']:
            self.assertEqual(fields.values[name], self.form[name])
        self.assertIn('Retained notes', response.get_data(as_text=True))
        self.audit.assert_not_called()
        corrected = dict(self.form, amount='0.20')
        self.assertEqual(self.client.post('/finance/expenses/add', data=corrected).status_code, 302)
        self.assertEqual(write.call_args.args[2:5], ('2', '2', '2'))
        self.audit.assert_called_once()

    def test_edit_uses_post_selections_including_explicit_clear(self):
        self.mock('update_expense', side_effect=ValueError('Invalid amount.'))
        for form in [self.form, dict(self.form, department_id='', supplier_id='', purchase_order_id='', payment_method='')]:
            fields = FormValues(self.client.post('/finance/expenses/41/edit', data=form).get_data(as_text=True))
            for name in ['category_id', 'department_id', 'supplier_id', 'purchase_order_id', 'payment_method']:
                self.assertEqual(fields.selected(name), form[name])
        fields = FormValues(self.client.get('/finance/expenses/41/edit').get_data(as_text=True))
        self.assertEqual(fields.selected('department_id'), '1')
        self.assertEqual(fields.selected('payment_method'), 'CASH')
        self.audit.assert_not_called()

    def test_missing_malformed_and_ineligible_selections_do_not_fall_back(self):
        self.mock('create_expense', side_effect=ValueError('Invalid reference.'))
        for value in ['999', '-1', '<invalid>']:
            form = dict(self.form, category_id=value, department_id=value, supplier_id=value,
                        purchase_order_id=value, payment_method=value)
            html = self.client.post('/finance/expenses/add', data=form).get_data(as_text=True)
            self.assertIn('invalid or no longer eligible', html)
            self.assertNotIn('<invalid>', html)
            fields = FormValues(html)
            for name in ['category_id', 'department_id', 'supplier_id', 'purchase_order_id', 'payment_method']:
                self.assertEqual(fields.selected(name), value)
        # An existing draft's now-unavailable references are also retained on GET.
        self.expense.update(category_id=999, department_id=999, supplier_id=999, purchase_order_id=999)
        fields = FormValues(self.client.get('/finance/expenses/41/edit').get_data(as_text=True))
        self.assertEqual(fields.selected('category_id'), '999')
        self.assertEqual(fields.selected('department_id'), '999')
        self.audit.assert_not_called()

    def test_canonical_identifier_selection_and_missing_category(self):
        self.mock('create_expense', side_effect=ValueError('Invalid amount.'))
        fields = FormValues(self.client.post('/finance/expenses/add', data=dict(self.form, department_id=' 0002 ')).get_data(as_text=True))
        self.assertEqual(fields.selected('department_id'), '2')
        self.mock('update_expense', side_effect=ValueError('Category required.'))
        fields = FormValues(self.client.post('/finance/expenses/41/edit', data=dict(self.form, category_id='')).get_data(as_text=True))
        self.assertEqual(fields.selected('category_id'), '')

    def test_viewer_controls_and_backend_forgery_csrf_and_revocation(self):
        html = self.client.get('/finance/budgets').get_data(as_text=True)
        self.assertIn('/finance/budgets/add', html)
        self.assertIn('/finance/budgets/1/edit', html)
        self.state = dict(self.state, permissions=frozenset(['finance.view']))
        html = self.client.get('/finance/budgets').get_data(as_text=True)
        self.assertNotIn('/finance/budgets/add', html)
        self.assertNotIn('/finance/budgets/1/edit', html)
        self.assertIn('/finance/budgets/1', html)
        write = self.mock('create_department_budget')
        self.assertTrue(self.client.post('/finance/budgets/add', data={}).location.endswith('/dashboard'))
        self.assertTrue(self.client.get('/finance/budgets/1/edit').location.endswith('/dashboard'))
        raw = self.erp.app.test_client()
        with raw.session_transaction() as sess:
            stamp_session(self.erp.app, sess, self.state)
        self.assertEqual(raw.post('/finance/budgets/add', data={}).status_code, 400)
        write.assert_not_called()
        self.audit.assert_not_called()

    def test_budget_years_and_department_filter_remain_selected(self):
        for year in [date.today().year, date.today().year-2, 2010, date.today().year+1, 1000, 9999]:
            response = self.client.get(f'/finance/budgets?year={year}&department_id=1')
            self.assertEqual(response.status_code, 200)
            fields = FormValues(response.get_data(as_text=True))
            self.assertEqual(fields.selected('year'), str(year))
            self.assertEqual(fields.selected('department_id'), '1')
            self.assertEqual(self.budgets.call_args.args[0]['year'],str(year))

    def test_invalid_years_report_error_without_broadening_department_filter(self):
        for year in ['', 'NaN', '999', '10000', '2026.0', '-2026']:
            response=self.client.get('/finance/budgets',query_string=dict(year=year,department_id=2))
            self.assertEqual(response.status_code,400)
            html=response.get_data(as_text=True)
            self.assertIn('Budget year must be between',html)
            self.assertNotIn('Total Budget',html)
            fields=FormValues(html)
            self.assertEqual(fields.selected('department_id'),'2')

    def test_budget_labels_use_exact_amounts_even_when_percent_rounds_to_100(self):
        for spent, label in [('700000.00', 'Normal'), ('999999.99', 'Warning'),
                             ('1000000.00', 'Fully Used'), ('1000000.01', 'Over Budget')]:
            self.budget.update(spent_amount=Decimal(spent), remaining_amount=Decimal('1000000.00')-Decimal(spent))
            html = self.client.get('/finance/budgets').get_data(as_text=True)
            self.assertIn(label, html)
            for other in {'Normal', 'Warning', 'Fully Used', 'Over Budget'}-{label}:
                self.assertNotIn('>'+''.join(other.split())+'<', ''.join(html.split()))
            if spent != '700000.00':
                self.assertIn('100.0%', html)


if __name__ == '__main__':
    unittest.main()
