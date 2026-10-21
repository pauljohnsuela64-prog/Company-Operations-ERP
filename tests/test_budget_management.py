"""Budget listing and committed edits; no company DB access or calculation policy."""
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from budget_management import BudgetError,listing_values,submitted_values
from finance_validation import budget_values
from security_helpers import csrf_client,stamp_session,user_state
from test_finance_functional import FormValues


class BudgetInputTests(unittest.TestCase):
    def test_filters_dates_ids_sizes_duplicates_and_controls(self):
        self.assertEqual(listing_values({},2026),dict(year=2026,department_id=None,search='',page=1,page_size=25))
        for size in (25,50,100):self.assertEqual(listing_values({'year':'1000','page_size':str(size)},2026)['page_size'],size)
        for values in ({'year':''},{'year':'NaN'},{'year':'999'},{'department_id':'bad'},{'page':'0'},{'page_size':'500'},{'search':'x'*101},{'search':'\x00'},{'search':'\ud800'},{'unknown':'value'},MultiDict([('year','2026'),('year','2027')])):
            with self.assertRaises(ValueError):listing_values(values,2026)
        self.assertEqual(listing_values({'department_id':'none'},2026)['department_id'],'none')

    def test_financial_bounds_preserved_notes_utf8_and_duplicates(self):
        self.assertEqual(budget_values(1,'9999','999,999,999,999.99',' a\r\nb '),(1,9999,Decimal('999999999999.99'),'a\r\nb'))
        for notes in ('x'*256,'x\x00','\ud800',False):
            with self.assertRaises(ValueError):budget_values(1,2026,'1',notes)
        for name in ('department_id','budget_year','budget_amount','notes'):
            with self.assertRaises(ValueError):submitted_values(MultiDict([(name,'1'),(name,'2')]))


class BudgetRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.repo=importlib.import_module('budget_repository')
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(self.repo,'get_connection',return_value=self.db))
        self.department=self.stack.enter_context(patch.object(self.repo,'lock_department'))
        self.real_storage=self.repo._require_budget_storage
        self.stack.enter_context(patch.object(self.repo,'_require_budget_storage'))

    def test_invalid_input_precedes_connection(self):
        for action in (lambda:self.repo.create_department_budget('bad',2026,'1',None,1),lambda:self.repo.update_department_budget(0,1,2026,'1',None),lambda:self.repo.get_department_budget_page({'year':'bad'},2026)):
            with self.assertRaises(ValueError):action()
        self.factory.assert_not_called()

    def test_create_identity_and_commit_boundary(self):
        self.cur.lastrowid=17
        self.assertEqual(self.repo.create_department_budget(1,2026,'1.00','PRIVATE',1),17)
        self.department.assert_called_once_with(self.cur,1)
        self.db.commit.assert_called_once()
        self.db.commit.side_effect=Error('Commit failure')
        with self.assertRaises(Error):self.repo.create_department_budget(1,2027,'1',None,1)
        self.db.rollback.assert_called_once()

    def test_update_lock_missing_noop_and_changed(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(BudgetError):self.repo.update_department_budget(1,1,2026,'1',None)
        self.cur.fetchone.return_value=(1,1,2026,Decimal('1'),None)
        self.assertFalse(self.repo.update_department_budget(1,1,2026,'1',None));self.db.commit.assert_not_called()
        self.assertTrue(self.repo.update_department_budget(1,1,2026,'2',None));self.db.commit.assert_called_once()
        self.assertIn('FOR UPDATE',self.cur.execute.call_args_list[-2].args[0])
        self.assertTrue(all(call.args==(self.cur,1) and not call.kwargs for call in self.department.call_args_list))

    def test_duplicate_and_commit_errors_close_and_rollback(self):
        self.cur.fetchone.return_value=(1,1,2026,Decimal('1'),None)
        self.db.commit.side_effect=Error('connection loss',errno=2013)
        with self.assertRaises(Error):self.repo.update_department_budget(1,1,2026,'2',None)
        self.db.rollback.assert_called_once();self.db.close.assert_called_once()
        self.db.commit.side_effect=None;self.cur.execute.side_effect=Error('PRIVATE SQL',errno=1062)
        with self.assertRaisesRegex(ValueError,'already has a budget'):self.repo.create_department_budget(1,2026,'2',None,1)

    def test_snapshot_summaries_full_filters_binding_and_stable_order(self):
        self.cur.fetchone.return_value=dict(department_count=101,total_budget=Decimal('101'),total_spent=Decimal('1'),total_remaining=Decimal('100'))
        self.cur.fetchall.return_value=[dict(budget_id=1)]
        page=self.repo.get_department_budget_page(dict(year='2026',department_id='2',search="%_!' OR 1=1",page_size='50',page='999'),2026)
        self.assertEqual((page['total'],page['first'],page['last'],page['filters']['page']),(101,101,101,3))
        count,count_params=self.cur.execute.call_args_list[0].args
        query,params=self.cur.execute.call_args_list[1].args
        self.assertIn("status = 'PAID'",count);self.assertIn('COALESCE(SUM(remaining_amount),0)',count)
        self.assertNotIn('LIMIT',count);self.assertNotIn('OR 1=1',query)
        self.assertEqual(count_params,(2026,2,"%!%!_!!' OR 1=1%","%!%!_!!' OR 1=1%"));self.assertEqual(params,(*count_params,50,100))
        self.assertIn('b.budget_year DESC,d.department_name ASC,b.budget_id ASC',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()

    def test_storage_requires_real_transactional_tables_without_repair(self):
        cur=MagicMock();cur.fetchall.return_value=[('department_budgets','InnoDB'),('expenses','InnoDB')]
        self.real_storage(cur,include_expenses=True)
        cur.fetchall.return_value=[{'TABLE_NAME':'department_budgets','ENGINE':'InnoDB'}]
        self.real_storage(cur)
        with self.assertRaises(BudgetError):self.real_storage(cur,include_expenses=True)
        for rows in ([],[('department_budgets','MyISAM')],[('expenses','InnoDB')]):
            cur.fetchall.return_value=rows
            with self.assertRaises(BudgetError) as error:self.real_storage(cur)
            self.assertEqual(error.exception.status_code,503)
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list))

    def test_cursor_failure_closes_management_connections(self):
        self.db.cursor.side_effect=Error('cursor unavailable')
        for action in (lambda:self.repo.get_department_budget_by_id(1),lambda:self.repo.create_department_budget(1,2026,'1',None,1),lambda:self.repo.update_department_budget(1,1,2026,'1',None),lambda:self.repo.get_department_budget_page({},2026)):
            self.db.reset_mock()
            with self.assertRaises(Error):action()
            self.db.close.assert_called_once()


class BudgetRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-budget-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['finance.view','finance.expenses.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.departments=[dict(department_id=1,department_code='D1',department_name='One',is_active=True)]
        for name in ('get_active_departments','get_all_departments'):self.stack.enter_context(patch.object(self.erp,name,return_value=self.departments))
        self.row=dict(budget_id=1,department_id=1,budget_year=2026,budget_amount=Decimal('1'),notes='Old')
        self.stack.enter_context(patch.object(self.erp,'get_department_budget_by_id',return_value=self.row))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.form=dict(department_id='1',budget_year='2026',budget_amount='1',notes='PRIVATE <img src=x>')

    def test_retained_create_edit_values_and_unlisted_department(self):
        for endpoint in ('add','1/edit'):
            with patch.object(self.erp,'create_department_budget',side_effect=ValueError('Invalid amount')),patch.object(self.erp,'update_department_budget',side_effect=ValueError('Invalid amount')):
                response=self.client.post('/finance/budgets/'+endpoint,data=dict(self.form,department_id='999',budget_amount='NaN',budget_year='10000'))
                self.assertEqual(response.status_code,200)
                values=FormValues(response.get_data(as_text=True))
                self.assertEqual(values.selected('department_id'),'999');self.assertEqual(values.values['budget_amount'],'NaN');self.assertEqual(values.values['budget_year'],'10000')
                self.assertIn('PRIVATE &lt;img',response.get_data(as_text=True))
        self.audit.assert_not_called()

    def test_noop_success_and_generic_unconfirmed_commit(self):
        with patch.object(self.erp,'update_department_budget',return_value=False):
            self.assertEqual(self.client.post('/finance/budgets/1/edit',data=self.form).status_code,302);self.audit.assert_not_called()
        with patch.object(self.erp,'update_department_budget',return_value=True):
            self.assertEqual(self.client.post('/finance/budgets/1/edit',data=self.form).status_code,302)
            self.assertEqual(self.audit.call_args.kwargs['entity_id'],1);self.assertNotIn('PRIVATE',str(self.audit.call_args))
        with patch.object(self.erp,'update_department_budget',side_effect=Error('PRIVATE connection loss',errno=2013)):
            self.audit.reset_mock();response=self.client.post('/finance/budgets/1/edit',data=self.form)
            self.assertEqual(response.status_code,503);self.audit.assert_not_called();self.assertIn('reconcile',response.get_data(as_text=True));self.assertNotIn('connection loss',response.get_data(as_text=True))

    def test_filters_links_summary_and_load_errors(self):
        selected=listing_values(dict(year='2026',search='A&B',department_id='1',page='2'),2026)
        page=dict(records=[],summary=dict(department_count=51,total_budget=Decimal('100'),total_spent=Decimal('10'),total_remaining=Decimal('90')),total=51,pages=3,first=26,last=50,filters=selected)
        with patch.object(self.erp,'get_department_budget_page',return_value=page):
            html=self.client.get('/finance/budgets').get_data(as_text=True)
            for text in ('of 51 budgets','search=A%26B','department_id=1','year=2026','page_size=25','page=3'):self.assertIn(text,html)
        with patch.object(self.erp,'get_department_budget_page',side_effect=BudgetError('Invalid Budget filter')):
            response=self.client.get('/finance/budgets');self.assertEqual(response.status_code,400);self.assertNotIn('Total Budget',response.get_data(as_text=True))
        with patch.object(self.erp,'get_department_budget_page',side_effect=Error('PRIVATE SQL')):
            self.assertEqual(self.client.get('/finance/budgets').status_code,503)

    def test_rendered_currency_normal_filtered_and_empty_listings(self):
        from html.parser import HTMLParser

        class VisibleText(HTMLParser):
            def __init__(self, html):
                super().__init__(); self.parts=[]; self.feed(html)
            def handle_data(self, data):
                self.parts.append(data)

        selected=listing_values({},2026)
        row=dict(self.row,department_name='One <script> & Co',
                 budget_amount=Decimal('1234567.89'),spent_amount=Decimal('234567.80'),
                 remaining_amount=Decimal('1000000.09'))
        for query,records in (('',[row]),('?year=2026&department_id=1&search=One',[row]),
                              ('?year=2026&search=missing',[])):
            with self.subTest(query=query):
                summary=dict(department_count=len(records),total_budget=row['budget_amount'] if records else Decimal('0'),
                             total_spent=row['spent_amount'] if records else Decimal('0'),
                             total_remaining=row['remaining_amount'] if records else Decimal('0'))
                page=dict(records=records,summary=summary,total=len(records),pages=1,first=1 if records else 0,
                          last=len(records),filters=dict(selected,search='missing' if not records else ''))
                with patch.object(self.erp,'get_department_budget_page',return_value=page):
                    response=self.client.get('/finance/budgets'+query)
                self.assertEqual(response.status_code,200)
                self.assertIn('charset=utf-8',response.content_type)
                html=response.data.decode('utf-8',errors='strict')
                text=' '.join(' '.join(VisibleText(html).parts).split())
                self.assertEqual(text.count('\u20b1'),6 if records else 3)
                for corrupt in ('\u00c3','\u00c2','\ufffd'):
                    self.assertNotIn(corrupt,text)
                if records:
                    for amount in ('1,234,567.89','234,567.80','1,000,000.09'):
                        self.assertEqual(text.count('\u20b1'+amount),2)
                    self.assertIn('One &lt;script&gt; &amp; Co',html)
                    self.assertNotIn('One <script>',html)
                else:
                    self.assertEqual(text.count('\u20b10.00'),3)
                    self.assertIn('No department budgets match these filters.',text)

    def test_missing_record_duplicate_form_and_permission_denial(self):
        with patch.object(self.erp,'get_department_budget_by_id',return_value=None):self.assertEqual(self.client.get('/finance/budgets/9/edit').status_code,302)
        with patch.object(self.erp,'create_department_budget') as write:
            self.assertEqual(self.client.post('/finance/budgets/add',data=MultiDict([('department_id','1'),('department_id','2')])).status_code,400);write.assert_not_called()
            self.state['permissions']=frozenset(['finance.view'])
            self.assertEqual(self.client.post('/finance/budgets/add',data=self.form).status_code,302);write.assert_not_called()
        self.audit.assert_not_called()

    def test_csrf_and_schema_gate_remain_authoritative(self):
        raw=self.erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.assertEqual(raw.post('/finance/budgets/add',data=self.form).status_code,400)
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE')):
            self.assertEqual(self.client.get('/finance/budgets').status_code,503)
        self.audit.assert_not_called()
