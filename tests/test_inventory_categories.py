"""Category management regressions; no company database access."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from inventory_category_management import CategoryError,filters,submitted_values
from inventory_validation import category_fields
import inventory_category_repository as repo
from security_helpers import csrf_client,stamp_session,user_state
from test_finance_functional import FormValues


class CategoryInputTests(unittest.TestCase):
    def test_filters_bounds_duplicate_keys_and_unicode(self):
        self.assertEqual(filters({}),dict(search='',status='',page=1,page_size=25))
        for size in (25,50,100):self.assertEqual(filters(dict(page_size=str(size),search=' %_! Caf? '))['search'],'%_! Caf?')
        for args in ({'status':'bad'},{'page':'0'},{'page_size':'10'},{'page':'2147483648'},{'search':'x'*101},{'search':'x\x00'},{'search':'\ud800'},{'unknown':'x'},MultiDict([('status','active'),('status','inactive')])):
            with self.subTest(args=args),self.assertRaises(ValueError):filters(args)

    def test_fields_normalization_boundaries_controls_and_duplicate_fields(self):
        self.assertEqual(category_fields(' c ',' Name ',' Line1\nLine2 '),('C','Name','Line1\nLine2'))
        self.assertEqual(category_fields('c'*30,'n'*100,'d'*255),('C'*30,'n'*100,'d'*255))
        for index,limit in enumerate((30,100,255)):
            for bad in ('x'*(limit+1),'x\x00','\ud800',False):
                args=['C','Name',None];args[index]=bad
                with self.assertRaises(ValueError):category_fields(*args)
        for name in ('category_code','category_name','description'):
            with self.assertRaises(CategoryError):submitted_values(MultiDict([(name,'1'),(name,'2')]))


class CategoryRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(repo,'get_connection',return_value=self.db))

    def test_invalid_inputs_precede_connection(self):
        for action in (lambda:repo.get_inventory_category_by_id(0),lambda:repo.set_inventory_category_active_status(1,'yes'),lambda:repo.update_inventory_category(False,'C','Name'),lambda:repo.create_inventory_category('C','x'*101),lambda:repo.get_inventory_category_page({'page':'NaN'})):
            with self.assertRaises(ValueError):action()
        self.factory.assert_not_called()

    def test_snapshot_binding_counts_empty_and_clamping(self):
        self.cur.fetchone.return_value={'total':101};self.cur.fetchall.return_value=[{'category_id':7}]
        result=repo.get_inventory_category_page(dict(search="%_!' OR 1=1",status='inactive',page='999',page_size='50'))
        self.assertEqual((result['total'],result['first'],result['last'],result['filters']['page']),(101,101,101,3))
        count,params=self.cur.execute.call_args_list[0].args;query,page_params=self.cur.execute.call_args_list[1].args
        self.assertNotIn('LIMIT',count);self.assertNotIn('OR 1=1',query)
        self.assertEqual(params,("%!%!_!!' OR 1=1%","%!%!_!!' OR 1=1%",False));self.assertEqual(page_params,(*params,50,100))
        self.assertIn('category_name ASC,category_id ASC',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()
        self.cur.fetchone.return_value={'total':0};self.cur.fetchall.return_value=[]
        page=repo.get_inventory_category_page({});self.assertEqual((page['first'],page['last'],page['pages']),(0,0,1))

    def test_update_missing_noop_and_changed_commit(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(CategoryError) as error:repo.update_inventory_category(1,'C','Name')
        self.assertEqual(error.exception.status_code,404)
        self.cur.fetchone.return_value=('C','Name',None)
        self.assertFalse(repo.update_inventory_category(1,' c ',' Name ',' '));self.db.commit.assert_not_called()
        self.assertTrue(repo.update_inventory_category(1,'C','Changed'))
        self.db.commit.assert_called_once();self.assertIn('FOR UPDATE',self.cur.execute.call_args_list[-2].args[0])

    def test_status_missing_noop_changed(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(CategoryError):repo.set_inventory_category_active_status(1,False)
        self.cur.fetchone.return_value=(False,)
        self.assertFalse(repo.set_inventory_category_active_status(1,False));self.db.commit.assert_not_called()
        self.assertTrue(repo.set_inventory_category_active_status(1,True));self.db.commit.assert_called_once()

    def test_duplicate_deadlock_commit_errors_and_cursor_cleanup(self):
        for errno,message in ((1062,'code or category name already exists'),(1213,'concurrently')):
            self.cur.execute.side_effect=Error('PRIVATE SQL',errno=errno)
            with self.assertRaisesRegex(ValueError,message):repo.create_inventory_category('C','Name')
        self.cur.execute.side_effect=None;self.db.commit.side_effect=Error('lost ack',errno=2013)
        with self.assertRaises(Error):repo.create_inventory_category('C','Name')
        self.assertEqual(self.db.rollback.call_count,3)
        self.db.cursor.side_effect=Error('cursor unavailable')
        for action in (repo.get_all_inventory_categories,repo.get_active_inventory_categories,lambda:repo.get_inventory_category_by_id(1),lambda:repo.create_inventory_category('C','Name'),lambda:repo.update_inventory_category(1,'C','Name'),lambda:repo.set_inventory_category_active_status(1,False),lambda:repo.get_inventory_category_page({})):
            self.db.reset_mock()
            with self.assertRaises(Error):action()
            self.db.close.assert_called_once()


class CategoryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-categories-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True));self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['inventory.view','inventory.categories.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.row=dict(category_id=1,category_code='C',category_name='Name',description=None,is_active=True)
        self.stack.enter_context(patch.object(self.erp,'get_inventory_category_by_id',return_value=self.row))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.form=dict(category_code='C',category_name='PRIVATE <img src=x>',description='PRIVATE <script>')

    def test_retained_raw_values_escaping_and_duplicate_errors(self):
        for path,operation in (('add','create_inventory_category'),('1/edit','update_inventory_category')):
            response=self.client.post('/inventory/categories/'+path,data=dict(self.form,description='x'*256))
            self.assertEqual(response.status_code,200);html=response.get_data(as_text=True)
            self.assertEqual(FormValues(html).values['category_name'],self.form['category_name'])
            self.assertIn('PRIVATE &lt;img',html);self.assertNotIn('PRIVATE <img',html);self.assertIn('x'*256,html)
            with patch.object(self.erp,operation,side_effect=ValueError('Category code or category name already exists.')):
                self.assertEqual(self.client.post('/inventory/categories/'+path,data=self.form).status_code,200)
        self.audit.assert_not_called()

    def test_listing_links_counts_errors_and_viewer_controls(self):
        selected=filters(dict(search='A&B',status='inactive',page='2'));page=dict(records=[],total=51,pages=3,first=26,last=50,filters=selected)
        with patch.object(self.erp,'get_inventory_category_page',return_value=page):
            html=self.client.get('/inventory/categories').get_data(as_text=True)
            for text in ('of 51 categories','search=A%26B','status=inactive','page_size=25','page=3'):self.assertIn(text,html)
        for error,code in ((CategoryError('Invalid category filter'),400),(Error('PRIVATE SQL'),503)):
            with patch.object(self.erp,'get_inventory_category_page',side_effect=error):
                response=self.client.get('/inventory/categories');self.assertEqual(response.status_code,code)
                self.assertIn('Inventory categories were not loaded.',response.get_data(as_text=True));self.assertNotIn('matching categories',response.get_data(as_text=True))
        page['records']=[self.row];self.state['permissions']=frozenset(['inventory.view'])
        with patch.object(self.erp,'get_inventory_category_page',return_value=page):
            html=self.client.get('/inventory/categories').get_data(as_text=True)
            self.assertNotIn('/inventory/categories/add',html);self.assertNotIn('/inventory/categories/1/status',html)

    def test_changed_noop_uncertain_writes_and_audit_failure(self):
        for result,expected in ((False,0),(True,1)):
            self.audit.reset_mock()
            with patch.object(self.erp,'update_inventory_category',return_value=result):
                self.assertEqual(self.client.post('/inventory/categories/1/edit',data=self.form).status_code,302)
            self.assertEqual(self.audit.call_count,expected)
            if expected:self.assertNotIn('PRIVATE',str(self.audit.call_args))
        for operation,path in (('create_inventory_category','add'),('update_inventory_category','1/edit')):
            self.audit.reset_mock()
            with patch.object(self.erp,operation,side_effect=Error('PRIVATE lost ack',errno=2013)):
                response=self.client.post('/inventory/categories/'+path,data=self.form)
                self.assertEqual(response.status_code,503);self.assertIn('reconcile',response.get_data(as_text=True));self.audit.assert_not_called()
        with patch.object(self.erp,'update_inventory_category',return_value=True),patch.object(self.erp.app.logger,'exception'):
            self.audit.side_effect=RuntimeError('Synthetic audit failure')
            self.assertEqual(self.client.post('/inventory/categories/1/edit',data=self.form).status_code,302)

    def test_explicit_status_targets_noops_and_legacy_toggle(self):
        for data in ({'is_active':'0'},{}):
            with patch.object(self.erp,'set_inventory_category_active_status',return_value=False) as write:
                self.assertEqual(self.client.post('/inventory/categories/1/status',data=data).status_code,302)
                write.assert_called_once_with(1,False);self.audit.assert_not_called()
        for data in ({'is_active':'bad'},MultiDict([('is_active','0'),('is_active','1')])):
            with patch.object(self.erp,'set_inventory_category_active_status') as write:
                self.assertEqual(self.client.post('/inventory/categories/1/status',data=data).status_code,400);write.assert_not_called()

    def test_missing_duplicate_fields_and_security(self):
        with patch.object(self.erp,'get_inventory_category_by_id',return_value=None):
            self.assertEqual(self.client.get('/inventory/categories/99/edit').status_code,302)
            self.assertEqual(self.client.post('/inventory/categories/99/status').status_code,404)
        with patch.object(self.erp,'update_inventory_category',side_effect=CategoryError('Inventory category no longer exists.',404)):
            self.assertEqual(self.client.post('/inventory/categories/1/edit',data=self.form).status_code,404)
        with patch.object(self.erp,'create_inventory_category') as write:
            self.assertEqual(self.client.post('/inventory/categories/add',data=MultiDict([('category_code','C'),('category_code','D')])).status_code,400)
            raw=self.erp.app.test_client()
            with raw.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
            self.assertEqual(raw.post('/inventory/categories/add',data=self.form).status_code,400)
            # Item managers do not inherit category management rights.
            self.state['permissions']=frozenset(['inventory.view','inventory.items.manage'])
            self.assertEqual(self.client.post('/inventory/categories/add',data=self.form).status_code,302);write.assert_not_called()
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE')):
            self.assertEqual(self.client.get('/inventory/categories').status_code,503)
        self.audit.assert_not_called()
