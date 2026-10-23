"""Supplier management regressions; no company database access."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from supplier_management import SupplierError,filters,submitted_values
from supplier_management import fields as supplier_fields
import supplier_repository as repo
from security_helpers import csrf_client,stamp_session,user_state
from test_finance_functional import FormValues


class SupplierInputTests(unittest.TestCase):
    def test_filters_bounds_duplicate_keys_and_unicode(self):
        self.assertEqual(filters({}),dict(search='',status='',page=1,page_size=25))
        for size in (25,50,100):self.assertEqual(filters(dict(page_size=str(size),search=' %_! Caf\u00e9 '))['search'],'%_! Caf\u00e9')
        for args in ({'status':'bad'},{'page':'0'},{'page_size':'10'},{'page':'2147483648'},{'search':'x'*101},{'search':'x\x00'},{'search':'\ud800'},{'unknown':'x'},MultiDict([('status','active'),('status','inactive')])):
            with self.subTest(args=args),self.assertRaises(ValueError):filters(args)

    def test_fields_required_policy_optional_values_and_boundaries(self):
        from procurement_validation import validate_supplier,SUPPLIER_LIMITS
        self.assertEqual(supplier_fields(' c ',' Name ',' ',' ',' ',' '),('C','Name',None,None,None,None))
        # Historical nonempty email text remains accepted; no format policy.
        validate_supplier('C','Name',email='not-an-email')
        self.assertEqual(supplier_fields('C','Name',address=' Line1\nLine2 ')[-1],'Line1\nLine2')
        for index,(name,limit) in enumerate(SUPPLIER_LIMITS.items()):
            for bad in ('x'*(limit+1),'x\x00','\ud800',False):
                args=['C','Name',None,None,None,None];args[index]=bad
                with self.assertRaises(ValueError):supplier_fields(*args)
            values=['C','Name',None,None,None,None];values[index]='x'*limit
            supplier_fields(*values)
            with self.assertRaises(SupplierError):submitted_values(MultiDict([(name,'1'),(name,'2')]))
        for index in (0,1):
            args=['C','Name',None,None,None,None];args[index]=' '
            with self.assertRaises(ValueError):supplier_fields(*args)


class SupplierRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(repo,'get_connection',return_value=self.db))

    def test_invalid_inputs_precede_connection(self):
        for action in (lambda:repo.set_supplier_active_status(1,'yes'),lambda:repo.update_supplier(False,'C','Name'),lambda:repo.create_supplier('C','x'*151),lambda:repo.get_supplier_page({'page':'NaN'})):
            with self.assertRaises(ValueError):action()
        self.factory.assert_not_called()

    def test_lookup_keeps_legacy_missing_identifier_contract(self):
        self.cur.fetchone.return_value=None
        for value in (0,-1,'999999999999'):
            self.assertIsNone(repo.get_supplier_by_id(value))
            self.assertEqual(self.cur.execute.call_args.args[1],(value,))

    def test_snapshot_binding_counts_empty_and_clamping(self):
        self.cur.fetchone.return_value={'total':101};self.cur.fetchall.return_value=[{'supplier_id':7}]
        result=repo.get_supplier_page(dict(search="%_!' OR 1=1",status='inactive',page='999',page_size='50'))
        self.assertEqual((result['total'],result['first'],result['last'],result['filters']['page']),(101,101,101,3))
        count,params=self.cur.execute.call_args_list[0].args;query,page_params=self.cur.execute.call_args_list[1].args
        self.assertNotIn('LIMIT',count);self.assertNotIn('OR 1=1',query)
        self.assertEqual(params,("%!%!_!!' OR 1=1%","%!%!_!!' OR 1=1%",False));self.assertEqual(page_params,(*params,50,100))
        self.assertIn('supplier_name ASC,supplier_id ASC',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()
        self.cur.fetchone.return_value={'total':0};self.cur.fetchall.return_value=[]
        page=repo.get_supplier_page({});self.assertEqual((page['first'],page['last'],page['pages']),(0,0,1))

    def test_update_missing_noop_and_changed_commit(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(SupplierError) as error:repo.update_supplier(1,'C','Name')
        self.assertEqual(error.exception.status_code,404)
        self.cur.fetchone.return_value=('C','Name',None,None,None,None)
        self.assertFalse(repo.update_supplier(1,' c ',' Name ',' '));self.db.commit.assert_not_called()
        self.assertTrue(repo.update_supplier(1,'C','Changed'))
        self.db.commit.assert_called_once();self.assertIn('FOR UPDATE',self.cur.execute.call_args_list[-2].args[0])

    def test_status_missing_noop_changed(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(SupplierError):repo.set_supplier_active_status(1,False)
        self.cur.fetchone.return_value=(False,)
        self.assertFalse(repo.set_supplier_active_status(1,False));self.db.commit.assert_not_called()
        self.assertTrue(repo.set_supplier_active_status(1,True));self.db.commit.assert_called_once()

    def test_duplicate_deadlock_commit_errors_and_cursor_cleanup(self):
        for errno,message in ((1062,'code already exists'),(1213,'concurrently')):
            self.cur.execute.side_effect=Error('PRIVATE SQL',errno=errno)
            with self.assertRaisesRegex(ValueError,message):repo.create_supplier('C','Name')
        self.cur.execute.side_effect=None;self.db.commit.side_effect=Error('lost ack',errno=2013)
        with self.assertRaises(Error):repo.create_supplier('C','Name')
        self.assertEqual(self.db.rollback.call_count,3)
        self.db.cursor.side_effect=Error('cursor unavailable')
        for action in (repo.get_all_suppliers,repo.get_active_suppliers,lambda:repo.get_supplier_by_id(1),lambda:repo.create_supplier('C','Name'),lambda:repo.update_supplier(1,'C','Name'),lambda:repo.set_supplier_active_status(1,False),lambda:repo.get_supplier_page({})):
            self.db.reset_mock()
            with self.assertRaises(Error):action()
            self.db.close.assert_called_once()


class SupplierRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-suppliers-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True));self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['procurement.view','procurement.suppliers.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.row=dict(supplier_id=1,supplier_code='C',supplier_name='Name',contact_person=None,email=None,phone=None,address=None,is_active=True)
        self.stack.enter_context(patch.object(self.erp,'get_supplier_by_id',return_value=self.row))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.form=dict(supplier_code='C',supplier_name='PRIVATE <img src=x>',contact_person='PRIVATE contact',email='private@example.test',phone='PRIVATE phone',address='PRIVATE <script>')

    def test_retained_raw_values_escaping_and_duplicate_errors(self):
        for path,operation in (('add','create_supplier'),('1/edit','update_supplier')):
            response=self.client.post('/procurement/suppliers/'+path,data=dict(self.form,address='x'*256))
            self.assertEqual(response.status_code,200);html=response.get_data(as_text=True)
            self.assertEqual(FormValues(html).values['supplier_name'],self.form['supplier_name'])
            self.assertIn('PRIVATE &lt;img',html);self.assertNotIn('PRIVATE <img',html);self.assertIn('x'*256,html)
            with patch.object(self.erp,operation,side_effect=ValueError('Supplier code already exists.')):
                self.assertEqual(self.client.post('/procurement/suppliers/'+path,data=self.form).status_code,200)
        self.audit.assert_not_called()

    def test_required_field_policy_matches_forms_and_optional_create(self):
        from html.parser import HTMLParser
        class Inputs(HTMLParser):
            def __init__(self,html):
                super().__init__();self.required=set();self.feed(html)
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag in ('input','textarea') and 'required' in attrs:self.required.add(attrs.get('name'))
        for path in ('add','1/edit'):
            response=self.client.get('/procurement/suppliers/'+path)
            self.assertEqual(Inputs(response.get_data(as_text=True)).required,{'supplier_code','supplier_name'})
        with patch.object(self.erp,'create_supplier',return_value=2) as write:
            self.assertEqual(self.client.post('/procurement/suppliers/add',data={'supplier_code':'OPTIONAL','supplier_name':'Name'}).status_code,302)
            write.assert_called_once_with('OPTIONAL','Name',None,None,None,None)

    def test_legacy_email_text_is_editable_and_retained_without_native_email_gate(self):
        from html.parser import HTMLParser
        class Email(HTMLParser):
            def __init__(self, html):
                super().__init__(); self.attrs = None; self.feed(html)
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'input' and attrs.get('name') == 'email': self.attrs = attrs
        legacy = 'Legacy <billing> contact'
        self.row['email'] = legacy
        for path, operation in (('add', 'create_supplier'), ('1/edit', 'update_supplier')):
            response = self.client.get('/procurement/suppliers/' + path)
            attrs = Email(response.get_data(as_text=True)).attrs
            self.assertEqual(attrs['type'], 'text')
            self.assertEqual(attrs['maxlength'], '150')
            self.assertNotIn('required', attrs)
            self.assertNotIn('pattern', attrs)
            if path != 'add': self.assertEqual(attrs['value'], legacy)
            with patch.object(self.erp, operation, return_value=2) as write:
                response = self.client.post('/procurement/suppliers/' + path, data=dict(self.form, email=legacy))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(write.call_args.args[-3], legacy)
            response = self.client.post('/procurement/suppliers/' + path, data=dict(self.form, email=legacy, supplier_code=''))
            html = response.get_data(as_text=True)
            self.assertEqual(Email(html).attrs['value'], legacy)
            self.assertNotIn('Legacy <billing>', html)

    def test_listing_links_counts_errors_and_viewer_controls(self):
        selected=filters(dict(search='A&B',status='inactive',page='2'));page=dict(records=[],total=51,pages=3,first=26,last=50,filters=selected)
        with patch.object(self.erp,'get_supplier_page',return_value=page):
            html=self.client.get('/procurement/suppliers').get_data(as_text=True)
            for text in ('of 51 suppliers','search=A%26B','status=inactive','page_size=25','page=3'):self.assertIn(text,html)
        for error,code in ((SupplierError('Invalid supplier filter'),400),(Error('PRIVATE SQL'),503)):
            with patch.object(self.erp,'get_supplier_page',side_effect=error):
                response=self.client.get('/procurement/suppliers');self.assertEqual(response.status_code,code)
                self.assertIn('Suppliers were not loaded.',response.get_data(as_text=True));self.assertNotIn('matching suppliers',response.get_data(as_text=True))
        page['records']=[self.row];self.state['permissions']=frozenset(['procurement.view'])
        with patch.object(self.erp,'get_supplier_page',return_value=page):
            html=self.client.get('/procurement/suppliers').get_data(as_text=True)
            self.assertNotIn('/procurement/suppliers/add',html);self.assertNotIn('/procurement/suppliers/1/status',html)

    def test_changed_noop_uncertain_writes_and_audit_failure(self):
        for result,expected in ((False,0),(True,1)):
            self.audit.reset_mock()
            with patch.object(self.erp,'update_supplier',return_value=result):
                self.assertEqual(self.client.post('/procurement/suppliers/1/edit',data=self.form).status_code,302)
            self.assertEqual(self.audit.call_count,expected)
            if expected:self.assertNotIn('PRIVATE',str(self.audit.call_args))
        for operation,path in (('create_supplier','add'),('update_supplier','1/edit')):
            self.audit.reset_mock()
            with patch.object(self.erp,operation,side_effect=Error('PRIVATE lost ack',errno=2013)):
                response=self.client.post('/procurement/suppliers/'+path,data=self.form)
                self.assertEqual(response.status_code,503);self.assertIn('reconcile',response.get_data(as_text=True));self.audit.assert_not_called()
        with patch.object(self.erp,'update_supplier',return_value=True),patch.object(self.erp.app.logger,'exception'):
            self.audit.side_effect=RuntimeError('Synthetic audit failure')
            self.assertEqual(self.client.post('/procurement/suppliers/1/edit',data=self.form).status_code,302)

    def test_explicit_status_targets_noops_and_legacy_toggle(self):
        for data in ({'is_active':'0'},{}):
            with patch.object(self.erp,'set_supplier_active_status',return_value=False) as write:
                self.assertEqual(self.client.post('/procurement/suppliers/1/status',data=data).status_code,302)
                write.assert_called_once_with(1,False);self.audit.assert_not_called()
        for data in ({'is_active':'bad'},MultiDict([('is_active','0'),('is_active','1')])):
            with patch.object(self.erp,'set_supplier_active_status') as write:
                self.assertEqual(self.client.post('/procurement/suppliers/1/status',data=data).status_code,400);write.assert_not_called()

    def test_missing_duplicate_fields_and_security(self):
        with patch.object(self.erp,'get_supplier_by_id',return_value=None):
            self.assertEqual(self.client.get('/procurement/suppliers/99/edit').status_code,302)
            self.assertEqual(self.client.post('/procurement/suppliers/99/status').status_code,404)
        with patch.object(self.erp,'update_supplier',side_effect=SupplierError('Supplier no longer exists.',404)):
            self.assertEqual(self.client.post('/procurement/suppliers/1/edit',data=self.form).status_code,404)
        with patch.object(self.erp,'create_supplier') as write:
            self.assertEqual(self.client.post('/procurement/suppliers/add',data=MultiDict([('supplier_code','C'),('supplier_code','D')])).status_code,400)
            raw=self.erp.app.test_client()
            with raw.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
            self.assertEqual(raw.post('/procurement/suppliers/add',data=self.form).status_code,400)
            # Order managers do not inherit supplier management rights.
            self.state['permissions']=frozenset(['procurement.view','procurement.orders.manage'])
            self.assertEqual(self.client.post('/procurement/suppliers/add',data=self.form).status_code,302);write.assert_not_called()
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE')):
            self.assertEqual(self.client.get('/procurement/suppliers').status_code,503)
        self.audit.assert_not_called()
