"""Finance business audit boundaries; real company DB access is forbidden."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch

from security_helpers import csrf_client, stamp_session, user_state


def cases():
    expense=dict(expense_date='2026-01-01', category_id='42', department_id='', supplier_id='',
                 purchase_order_id='', description='private-description', amount='123456.78',
                 notes='private-notes', reference_number='private-reference')
    category=dict(category_code='CAT',category_name='private-name',description='private-description')
    budget=dict(department_id='3',budget_year='2026',budget_amount='123456.78',notes='private-notes')
    return [
        ('/finance/expenses/add', expense, 'create_expense', (41,'EXP-000041'), 'CREATE','EXPENSE',41,'EXP-000041'),
        ('/finance/expenses/41/edit', expense, 'update_expense', True, 'UPDATE','EXPENSE',41,'EXP-000041'),
        ('/finance/expenses/41/cancel', {}, 'cancel_expense', True, 'CANCEL','EXPENSE',41,'EXP-000041'),
        ('/finance/expense-categories/add', category, 'create_expense_category', 42,'CREATE','EXPENSE_CATEGORY',42,'CAT'),
        ('/finance/expense-categories/42/edit', category, 'update_expense_category', True,'UPDATE','EXPENSE_CATEGORY',42,'CAT'),
        ('/finance/expense-categories/42/status', {}, 'set_expense_category_active_status', True,'DEACTIVATE','EXPENSE_CATEGORY',42,'CAT'),
        ('/finance/expense-categories/42/status', {}, 'set_expense_category_active_status', True,'ACTIVATE','EXPENSE_CATEGORY',42,'CAT'),
        ('/finance/budgets/add', budget, 'create_department_budget', 43,'CREATE','DEPARTMENT_BUDGET',43,'DPT'),
        ('/finance/budgets/43/edit', budget, 'update_department_budget', None,'UPDATE','DEPARTMENT_BUDGET',43,'DPT'),
    ]


class FinanceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-finance-audit',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.state=user_state(permissions=['finance.expenses.manage','finance.categories.manage'])
        self.mock('get_authorization_state',side_effect=lambda _:self.state)
        self.mock('render_template',return_value='form')
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.audit=self.mock('create_audit_log')
        self.expense=dict(expense_id=41,expense_number='EXP-000041',status='DRAFT')
        self.category=dict(category_id=42,category_code='CAT',is_active=True)
        self.mock('get_expense_by_id',return_value=self.expense)
        self.mock('get_expense_category_by_id',return_value=self.category)
        self.mock('get_department_budget_by_id',return_value=dict(budget_id=43,department_id=3,budget_year=2026))
        self.mock('get_active_departments',return_value=[dict(department_id=3,department_code='DPT')])
        self.mock('get_active_expense_categories',return_value=[self.category])
        self.mock('get_active_suppliers',return_value=[])
        self.mock('get_all_purchase_orders',return_value=[])
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)

    def mock(self,name,**kwargs):return self.stack.enter_context(patch.object(self.erp,name,**kwargs))

    def test_success_actor_numeric_id_readable_label_and_privacy(self):
        for path,data,operation,result,action,entity,eid,label in cases():
            with self.subTest(action=action,entity=entity),patch.object(self.erp,operation,return_value=result) as write:
                self.category['is_active']=action!='ACTIVATE'
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                for key,value in dict(user_id=7,username='acting.user',module='FINANCE',action=action,entity_type=entity,entity_id=eid).items():
                    self.assertEqual(event[key],value)
                self.assertIn(label,event['description'])
                self.assertIn(str(eid),event['description'])
                if entity=='DEPARTMENT_BUDGET':self.assertIn('2026',event['description'])
                for secret in ['private-description','private-reference','private-name','private-notes','123456.78']:
                    self.assertNotIn(secret,str(event))

    def test_rejections_and_commit_failures_never_audit(self):
        for error in [ValueError('Validation failure'), RuntimeError('Commit failure')]:
            for path,data,operation,*_ in cases():
                with self.subTest(path=path,error=type(error).__name__),patch.object(self.erp,operation,side_effect=error):
                    self.audit.reset_mock()
                    try:self.client.post(path,data=data)
                    except (ValueError,RuntimeError):pass
                    self.audit.assert_not_called()

    def test_unsuccessful_results_do_not_audit(self):
        for path,data,operation,*_ in cases():
            if operation.startswith('create'):continue
            with self.subTest(operation=operation),patch.object(self.erp,operation,return_value=False):
                self.audit.reset_mock()
                self.client.post(path,data=data)
                self.audit.assert_not_called()

    def test_audit_failure_does_not_fail_successful_business_response(self):
        self.audit.side_effect=RuntimeError('Audit unavailable')
        for path,data,operation,result,*_ in cases():
            with self.subTest(path=path),patch.object(self.erp,operation,return_value=result) as write:
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()

    def test_csrf_revoked_and_disabled_accounts_prevent_write_and_audit(self):
        raw=self.erp.app.test_client()
        with raw.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)
        for path,data,operation,*_ in cases():
            with patch.object(self.erp,operation) as write:
                for extra in [{},{'csrf_token':'forged'}]:
                    self.assertEqual(raw.post(path,data=dict(data,**extra)).status_code,400)
                write.assert_not_called()
        self.state['permissions']=frozenset()
        for path,data,operation,*_ in cases():
            with patch.object(self.erp,operation) as write:
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_not_called()
        self.state['is_active']=False
        self.assertTrue(self.client.post('/finance/expenses/41/cancel').location.endswith('/login'))
        self.audit.assert_not_called()

    def test_cancel_display_lookup_failure_retains_numeric_identity(self):
        with patch.object(self.erp,'cancel_expense',return_value=True),patch.object(self.erp,'get_expense_by_id',side_effect=RuntimeError('Lookup failed')):
            self.assertEqual(self.client.post('/finance/expenses/41/cancel').status_code,302)
        self.audit.assert_called_once()
        self.assertEqual(self.audit.call_args.kwargs['entity_id'],41)

    def test_existing_approval_payment_events_are_single_and_keep_legacy_identity(self):
        self.state['permissions']=frozenset(['finance.expenses.approve','finance.expenses.pay'])
        for endpoint,operation,action in [('approve','approve_expense','APPROVE'),('paid','mark_expense_as_paid','MARK_PAID')]:
            with patch.object(self.erp,operation,return_value=True) as write:
                self.audit.reset_mock()
                self.assertEqual(self.client.post(f'/finance/expenses/41/{endpoint}').status_code,302)
                self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                self.assertEqual(event['action'],action)
                self.assertEqual(event['entity_id'],'EXP-000041')
                self.assertIn('41',event['description'])
                write.side_effect=ValueError('Already completed')
                self.client.post(f'/finance/expenses/41/{endpoint}')
                self.audit.assert_called_once()

    def test_inactive_department_label_lookup_is_best_effort_after_budget_create(self):
        with patch.object(self.erp,'get_active_departments',return_value=[]), \
             patch.object(self.erp,'create_department_budget',return_value=43), \
             patch.object(self.erp,'get_department_by_id',side_effect=RuntimeError('Lookup failed')):
            response=self.client.post('/finance/budgets/add',data=cases()[-2][1])
        self.assertEqual(response.status_code,302)
        self.audit.assert_called_once()
        event=self.audit.call_args.kwargs
        self.assertEqual(event['entity_id'],43)
        self.assertIn('department 3',event['description'])
        self.assertIn('2026',event['description'])
