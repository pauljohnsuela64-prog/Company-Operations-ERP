"""Items listing, transaction and route regressions; company DB access forbidden."""
from contextlib import ExitStack
from decimal import Decimal
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from inventory_item_management import ItemError,filters,submitted_values
from inventory_validation import item_fields
import inventory_item_repository as repo
from security_helpers import csrf_client,stamp_session,user_state
from test_finance_functional import FormValues


class ItemInputTests(unittest.TestCase):
    def test_filter_bounds_duplicates_and_literal_unicode(self):
        self.assertEqual(filters({}),dict(search='',category_id='',status='',page=1,page_size=25))
        for size in (25,50,100):self.assertEqual(filters(dict(page_size=str(size),category_id='none',search=' %_! Caf? '))['search'],'%_! Caf?')
        for args in ({'category_id':'bad'},{'category_id':'0'},{'status':'deleted'},{'page':'0'},{'page_size':'10'},{'page':'2147483648'},{'search':'x'*101},{'search':'x\x00'},{'search':'\ud800'},{'unknown':'x'},MultiDict([('status','active'),('status','inactive')])):
            with self.subTest(args=args),self.assertRaises(ValueError):filters(args)

    def test_text_validation_duplicate_fields_and_existing_quantity_bounds(self):
        for index in (0,1,3,4):
            for bad in ('x\x00','\ud800'):
                args=['I','Item',None,None,'pcs','0'];args[index]=bad
                with self.assertRaises(ValueError):item_fields(*args)
        self.assertEqual(item_fields(' i ',' Item ',None,' line1\nline2 ','pcs','0.10'),('I','Item',None,'line1\nline2','pcs',Decimal('0.10')))
        for name in ('item_code','item_name','category_id','description','unit_of_measure','reorder_level'):
            with self.assertRaises(ItemError):submitted_values(MultiDict([(name,'1'),(name,'2')]))


class ItemRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(repo,'get_connection',return_value=self.db))
        self.category=self.stack.enter_context(patch.object(repo,'lock_assignment_category'))

    def test_invalid_identifiers_precede_connection(self):
        for action in (lambda:repo.get_inventory_item_by_id(0),lambda:repo.set_inventory_item_active_status(1,'yes'),lambda:repo.update_inventory_item(False,'I','Item',None,None,'pcs','0'),lambda:repo.get_inventory_item_page({'page':'NaN'})):
            with self.assertRaises(ValueError):action()
        self.factory.assert_not_called()

    def test_snapshot_count_filters_binding_and_page_clamping(self):
        self.cur.fetchone.return_value={'total':101};self.cur.fetchall.return_value=[{'item_id':7}]
        result=repo.get_inventory_item_page(dict(search="%_!' OR 1=1",category_id='3',status='inactive',page='999',page_size='50'))
        self.assertEqual((result['total'],result['first'],result['last'],result['filters']['page']),(101,101,101,3))
        count,params=self.cur.execute.call_args_list[0].args
        query,page_params=self.cur.execute.call_args_list[1].args
        self.assertNotIn('LIMIT',count);self.assertNotIn('OR 1=1',query)
        self.assertEqual(params,("%!%!_!!' OR 1=1%","%!%!_!!' OR 1=1%",3,False))
        self.assertEqual(page_params,(*params,50,100));self.assertIn('i.item_name ASC,i.item_id ASC',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.rollback.assert_called_once();self.db.commit.assert_not_called()

    def test_update_missing_noop_changed_and_category_lock(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(ItemError) as error:repo.update_inventory_item(1,'I','Item',2,None,'pcs','0')
        self.assertEqual(error.exception.status_code,404)
        self.cur.fetchone.return_value=(2,'I','Item',None,'pcs',Decimal('0'))
        self.assertFalse(repo.update_inventory_item(1,'I','Item',2,None,'pcs','0'))
        self.db.commit.assert_not_called()
        self.assertTrue(repo.update_inventory_item(1,'I','Changed',2,None,'box','1'))
        self.db.commit.assert_called_once();self.category.assert_called_with(self.cur,2,2)
        self.assertIn('FOR UPDATE',self.cur.execute.call_args_list[-2].args[0])

    def test_status_missing_noop_changed(self):
        self.cur.fetchone.return_value=None
        with self.assertRaises(ItemError):repo.set_inventory_item_active_status(1,False)
        self.cur.fetchone.return_value=(False,)
        self.assertFalse(repo.set_inventory_item_active_status(1,False));self.db.commit.assert_not_called()
        self.assertTrue(repo.set_inventory_item_active_status(1,True));self.db.commit.assert_called_once()

    def test_duplicate_deadlock_and_commit_error_roll_back(self):
        for errno,message in ((1062,'already exists'),(1213,'concurrently')):
            self.cur.execute.side_effect=Error('PRIVATE SQL',errno=errno)
            with self.assertRaisesRegex(ValueError,message):repo.create_inventory_item('I','Item',None,None,'pcs','0')
        self.cur.execute.side_effect=None;self.db.commit.side_effect=Error('lost ack',errno=2013)
        with self.assertRaises(Error):repo.create_inventory_item('I','Item',None,None,'pcs','0')
        self.assertEqual(self.db.rollback.call_count,3);self.assertEqual(self.db.close.call_count,3)

    def test_cursor_failure_closes_all_connections(self):
        self.db.cursor.side_effect=Error('cursor unavailable')
        for action in (repo.get_all_inventory_items,repo.get_active_inventory_items,lambda:repo.get_inventory_item_by_id(1),lambda:repo.create_inventory_item('I','Item',None,None,'pcs','0'),lambda:repo.update_inventory_item(1,'I','Item',None,None,'pcs','0'),lambda:repo.set_inventory_item_active_status(1,False),lambda:repo.get_inventory_item_page({})):
            self.db.reset_mock()
            with self.assertRaises(Error):action()
            self.db.close.assert_called_once()


class ItemRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-items-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['inventory.view','inventory.items.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.row=dict(item_id=1,item_code='I',item_name='Item',category_id=None,description=None,unit_of_measure='pcs',reorder_level=Decimal('0'),is_active=True)
        self.stack.enter_context(patch.object(self.erp,'get_inventory_item_by_id',return_value=self.row))
        for name in ('get_all_inventory_categories','get_active_inventory_categories'):self.stack.enter_context(patch.object(self.erp,name,return_value=[]))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.form=dict(item_code='I',item_name='PRIVATE <img src=x>',category_id='999',description='PRIVATE <script>',unit_of_measure='custom',reorder_level='NaN')

    def test_retained_raw_values_unknown_category_unit_and_escaping(self):
        for path in ('add','1/edit'):
            response=self.client.post('/inventory/items/'+path,data=self.form)
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True);values=FormValues(html)
            self.assertEqual(values.values['reorder_level'],'NaN');self.assertEqual(values.selected('category_id'),'999')
            self.assertEqual(values.selected('unit_of_measure') if path=='add' else values.values['unit_of_measure'],'custom')
            self.assertIn('PRIVATE &lt;img',html);self.assertNotIn('PRIVATE <img',html)
        self.audit.assert_not_called()

    def test_listing_links_count_errors_and_viewer_controls(self):
        selected=filters(dict(search='A&B',category_id='999',status='inactive',page='2'))
        page=dict(records=[],total=51,pages=3,first=26,last=50,filters=selected)
        with patch.object(self.erp,'get_inventory_item_page',return_value=page):
            html=self.client.get('/inventory/items').get_data(as_text=True)
            for text in ('of 51 items','search=A%26B','category_id=999','status=inactive','page_size=25','page=3'):self.assertIn(text,html)
        for error,code in ((ItemError('Invalid item filter'),400),(Error('PRIVATE SQL'),503)):
            with patch.object(self.erp,'get_inventory_item_page',side_effect=error):
                response=self.client.get('/inventory/items');self.assertEqual(response.status_code,code)
                self.assertIn('Inventory items were not loaded.',response.get_data(as_text=True));self.assertNotIn('matching items',response.get_data(as_text=True))
        page['records']=[self.row];self.state['permissions']=frozenset(['inventory.view'])
        with patch.object(self.erp,'get_inventory_item_page',return_value=page):
            html=self.client.get('/inventory/items').get_data(as_text=True)
            self.assertNotIn('/inventory/items/add',html);self.assertNotIn('/inventory/items/1/status',html)

    def test_changed_noop_uncertain_writes_and_postcommit_audit(self):
        form=dict(self.form,reorder_level='0',category_id='')
        for result,expected in ((False,0),(True,1)):
            self.audit.reset_mock()
            with patch.object(self.erp,'update_inventory_item',return_value=result):
                self.assertEqual(self.client.post('/inventory/items/1/edit',data=form).status_code,302)
            self.assertEqual(self.audit.call_count,expected)
            if expected:self.assertNotIn('PRIVATE',str(self.audit.call_args))
        for operation,path in (('create_inventory_item','add'),('update_inventory_item','1/edit')):
            self.audit.reset_mock()
            with patch.object(self.erp,operation,side_effect=Error('PRIVATE lost ack',errno=2013)):
                response=self.client.post('/inventory/items/'+path,data=form)
                self.assertEqual(response.status_code,503);self.assertIn('reconcile',response.get_data(as_text=True));self.audit.assert_not_called()

    def test_explicit_status_target_noop_and_invalid_duplicate_rejected(self):
        with patch.object(self.erp,'set_inventory_item_active_status',return_value=False) as write:
            self.assertEqual(self.client.post('/inventory/items/1/status',data={'is_active':'0'}).status_code,302)
            write.assert_called_once_with(1,False);self.audit.assert_not_called()
        for data in ({'is_active':'bad'},MultiDict([('is_active','0'),('is_active','1')])):
            with patch.object(self.erp,'set_inventory_item_active_status') as write:
                self.assertEqual(self.client.post('/inventory/items/1/status',data=data).status_code,400);write.assert_not_called()

    def test_missing_duplicate_fields_and_security_gates(self):
        with patch.object(self.erp,'get_inventory_item_by_id',return_value=None):
            self.assertEqual(self.client.get('/inventory/items/99/edit').status_code,302)
            self.assertEqual(self.client.post('/inventory/items/99/status').status_code,404)
        for error,code in ((ItemError('Select a valid inventory item.'),400),(Error('PRIVATE connection'),503)):
            with patch.object(self.erp,'get_inventory_item_by_id',side_effect=error):
                response=self.client.get('/inventory/items/2147483648/edit')
                self.assertEqual(response.status_code,code);self.assertNotIn('PRIVATE',response.get_data(as_text=True))
        with patch.object(self.erp,'create_inventory_item') as write:
            self.assertEqual(self.client.post('/inventory/items/add',data=MultiDict([('item_code','I'),('item_code','J')])).status_code,400)
            raw=self.erp.app.test_client()
            with raw.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
            self.assertEqual(raw.post('/inventory/items/add',data=self.form).status_code,400)
            self.state['permissions']=frozenset(['inventory.view'])
            self.assertEqual(self.client.post('/inventory/items/add',data=self.form).status_code,302);write.assert_not_called()
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE')):
            self.assertEqual(self.client.get('/inventory/items').status_code,503)
        self.audit.assert_not_called()
