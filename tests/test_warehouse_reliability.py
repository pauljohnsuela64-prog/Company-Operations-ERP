"""Warehouse boundaries, query safety and committed-action audits; no company DB."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from warehouse_validation import WarehouseError,fields,identifier,filters
from security_helpers import csrf_client,stamp_session,user_state


class WarehouseValidationTests(unittest.TestCase):
    def test_schema_limits_normalization_and_optional_location(self):
        self.assertEqual(fields(' w ',' Name ',' '),('W','Name',None))
        self.assertEqual(tuple(map(len,fields('c'*30,'n'*100,'l'*255))),(30,100,255))
        for values in [('', 'N',None),('C','',None),('c'*31,'N',None),('C','n'*101,None),('C','N','l'*256),('C','N','x\n'),('C','\ud800',None),('\u00df'*16,'N',None),(False,'N',None)]:
            with self.subTest(values=values),self.assertRaises(ValueError):fields(*values)

    def test_ids_and_strict_filters(self):
        for value in (0,-1,True,'1 OR 1=1','2147483648','\uff11'):
            with self.assertRaises(ValueError):identifier(value)
        self.assertEqual(identifier('1'),1)
        for values in ({'status':'bad'},{'page':'0'},{'page_size':'500'},{'search':'x'*101},{'search':'x\x00'},{'query':'x'},MultiDict([('status','active'),('status','inactive')])):
            with self.assertRaises(ValueError):filters(values)
        for size in (25,50,100):self.assertEqual(filters({'page_size':str(size)})['page_size'],size)


class WarehouseRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.repo=importlib.import_module('warehouse_repository')
        self.db=MagicMock();self.cursor=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(self.repo,'get_connection',return_value=self.db))

    def test_invalid_operations_precede_connection(self):
        for action in (lambda:self.repo.create_warehouse('','N'),lambda:self.repo.update_warehouse(0,'C','N'),lambda:self.repo.set_warehouse_active_status(1,'0'),lambda:self.repo.get_warehouse_page({'status':'bad'})):
            with self.assertRaises(ValueError):action()
        self.factory.assert_not_called()

    def test_create_returns_identity_only_after_commit(self):
        self.cursor.lastrowid=13
        self.assertEqual(self.repo.create_warehouse(' c ','N'),13)
        self.db.start_transaction.assert_called_once();self.db.commit.assert_called_once()
        self.assertEqual(self.cursor.execute.call_args.args[1],('C','N',None))

    def test_update_changed_and_noop(self):
        self.cursor.fetchone.return_value=('C','Name',None)
        self.assertFalse(self.repo.update_warehouse(1,'c','Name'))
        self.db.commit.assert_not_called();self.assertEqual(self.cursor.execute.call_count,1)
        self.cursor.reset_mock();self.cursor.fetchone.return_value=('OLD','Name',None)
        self.assertTrue(self.repo.update_warehouse(1,'C','Name'))
        self.assertIn('FOR UPDATE',self.cursor.execute.call_args_list[0].args[0]);self.db.commit.assert_called_once()

    def test_missing_edit_status_and_noop_status(self):
        self.cursor.fetchone.return_value=None
        for action in (lambda:self.repo.update_warehouse(1,'C','N'),lambda:self.repo.set_warehouse_active_status(1,False)):
            with self.assertRaises(WarehouseError):action()
        self.cursor.fetchone.return_value=(0,)
        self.assertFalse(self.repo.set_warehouse_active_status(1,False));self.db.commit.assert_not_called()
        self.assertTrue(self.repo.set_warehouse_active_status(1,True))

    def test_sql_and_commit_failures_rollback_and_close(self):
        for stage in ('execute','commit'):
            self.db.reset_mock();self.cursor.reset_mock();self.cursor.fetchone.return_value=('OLD','N',None)
            self.cursor.execute.side_effect=Error('SQL failure') if stage=='execute' else None
            self.db.commit.side_effect=Error('commit failure') if stage=='commit' else None
            with self.assertRaises(Error):self.repo.update_warehouse(1,'C','N')
            self.db.rollback.assert_called_once();self.db.close.assert_called_once()

    def test_cursor_acquisition_failure_closes_every_connection(self):
        for action in (self.repo.get_all_warehouses,lambda:self.repo.get_warehouse_by_id(1),
                       lambda:self.repo.create_warehouse('C','N'),lambda:self.repo.update_warehouse(1,'C','N'),
                       lambda:self.repo.set_warehouse_active_status(1,False),lambda:self.repo.get_warehouse_page({})):
            self.db.reset_mock();self.db.cursor.side_effect=Error('Synthetic cursor failure')
            with self.assertRaises(Error):action()
            self.db.close.assert_called_once();self.db.commit.assert_not_called()

    def test_snapshot_count_binding_order_and_clamp(self):
        self.cursor.fetchone.return_value={'total':101};self.cursor.fetchall.return_value=[dict(warehouse_id=5)]
        result=self.repo.get_warehouse_page(dict(search="%_!' OR 1=1",status='inactive',page='999',page_size='50'))
        self.assertEqual((result['total'],result['pages'],result['first'],result['last'],result['filters']['page']),(101,3,101,101,3))
        sql,params=self.cursor.execute.call_args.args
        self.assertIn('ORDER BY warehouse_name,warehouse_id LIMIT %s OFFSET %s',sql)
        self.assertNotIn("OR 1=1",sql);self.assertEqual(params,("%!%!_!!' OR 1=1%",)*3+(False,50,100))
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()


class WarehouseRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-warehouse-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['inventory.view','inventory.warehouses.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.row=dict(warehouse_id=1,warehouse_code='WH',warehouse_name='Original',location='Original',is_active=True)
        self.lookup=self.stack.enter_context(patch.object(self.erp,'get_warehouse_by_id',return_value=self.row))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.data=dict(warehouse_code='WH',warehouse_name='PRIVATE name',location='PRIVATE <img src=x>')

    def test_retained_validation_and_duplicate_feedback(self):
        for endpoint in ('add','1/edit'):
            response=self.client.post('/inventory/warehouses/'+endpoint,data=dict(self.data,location='x'*256))
            self.assertIn('255 characters',response.get_data(as_text=True));self.assertEqual(response.status_code,400)
            self.assertIn('PRIVATE name',response.get_data(as_text=True))
        with patch.object(self.erp,'create_warehouse',side_effect=Error('PRIVATE SQL',errno=1062)):
            response=self.client.post('/inventory/warehouses/add',data=self.data)
            self.assertIn('already exists',response.get_data(as_text=True));self.assertNotIn('PRIVATE SQL',response.get_data(as_text=True))
            self.assertIn('&lt;img src=x&gt;',response.get_data(as_text=True))
        response=self.client.post('/inventory/warehouses/add',data=MultiDict([('warehouse_code','C'),('warehouse_code','OTHER'),('warehouse_name','N')]))
        self.assertEqual(response.status_code,400)
        self.audit.assert_not_called()

    def test_update_noop_commit_failure_and_safe_audit(self):
        for result in (False,True):
            with patch.object(self.erp,'update_warehouse',return_value=result):
                self.audit.reset_mock();self.assertEqual(self.client.post('/inventory/warehouses/1/edit',data=self.data).status_code,302)
                self.assertEqual(self.audit.call_count,int(result))
                if result:self.assertNotIn('PRIVATE',str(self.audit.call_args))
        with patch.object(self.erp,'update_warehouse',side_effect=Error('PRIVATE connection loss',errno=2013)):
            self.audit.reset_mock();response=self.client.post('/inventory/warehouses/1/edit',data=self.data)
            self.assertEqual(response.status_code,503);self.audit.assert_not_called();self.assertIn('reconcile',response.get_data(as_text=True))

    def test_explicit_status_noop_invalid_and_legacy_forms(self):
        with patch.object(self.erp,'set_warehouse_active_status',return_value=False) as write:
            self.assertEqual(self.client.post('/inventory/warehouses/1/status',data={'is_active':'0'}).status_code,302)
            write.assert_called_once_with(1,False);self.audit.assert_not_called()
        with patch.object(self.erp,'set_warehouse_active_status',return_value=True) as write:
            self.assertEqual(self.client.post('/inventory/warehouses/1/status').status_code,302)
            write.assert_called_once_with(1,False);self.assertEqual(self.audit.call_args.kwargs['action'],'DEACTIVATE')
        with patch.object(self.erp,'set_warehouse_active_status') as write:
            self.assertEqual(self.client.post('/inventory/warehouses/1/status',data={'is_active':'bad'}).status_code,400);write.assert_not_called()

    def test_listing_links_empty_invalid_and_failure(self):
        values=filters(dict(search='A&B',status='inactive',page='2',page_size='25'))
        page=dict(records=[self.row],total=51,pages=3,first=26,last=26,filters=values)
        with patch.object(self.erp,'get_warehouse_page',return_value=page):
            html=self.client.get('/inventory/warehouses').get_data(as_text=True)
            for part in ('of 51 warehouses','page=3','status=inactive','search=A%26B','page_size=25','name="is_active"','name="csrf_token"'):self.assertIn(part,html)
        with patch.object(self.erp,'get_warehouse_page',side_effect=WarehouseError('Invalid warehouse filter.')):
            response=self.client.get('/inventory/warehouses?status=bad');self.assertEqual(response.status_code,400);self.assertIn('were not loaded',response.get_data(as_text=True))
        with patch.object(self.erp,'get_warehouse_page',side_effect=Error('PRIVATE SQL')):
            response=self.client.get('/inventory/warehouses');self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE SQL',response.get_data(as_text=True))

    def test_missing_permissions_csrf_and_schema_guard(self):
        self.lookup.return_value=None
        self.assertEqual(self.client.get('/inventory/warehouses/9/edit').status_code,302)
        self.state['permissions']=frozenset(['inventory.view'])
        with patch.object(self.erp,'create_warehouse') as write:
            self.assertEqual(self.client.post('/inventory/warehouses/add',data=self.data).status_code,302);write.assert_not_called()
        raw=self.erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(self.erp.app,session,self.state)
        self.assertEqual(raw.post('/inventory/warehouses/add',data=self.data).status_code,400)
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE')):
            self.assertEqual(self.client.get('/inventory/warehouses').status_code,503)
        self.audit.assert_not_called()
