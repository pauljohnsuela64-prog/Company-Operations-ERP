"""Inventory action audit boundaries using real Flask security and audit helper."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch
import mysql.connector
from stock_repository import StockResult
from security_helpers import csrf_client, stamp_session, user_state


class InventoryAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='inventory-audit-tests-only',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state=user_state(permissions=['inventory.view','inventory.categories.manage','inventory.warehouses.manage','inventory.items.manage','inventory.stock.manage'])
        self.mock('get_authorization_state',side_effect=lambda _:self.state)
        self.audit=self.mock('create_audit_log')
        self.mock('render_template',return_value='form')
        self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.records={'inventory_category':dict(category_id=1,category_code='CAT',category_name='private-name',is_active=True),
                      'warehouse':dict(warehouse_id=2,warehouse_code='WH',warehouse_name='private-name',is_active=True),
                      'inventory_item':dict(item_id=3,item_code='ITEM',item_name='private-name',category_id=1,is_active=True)}
        for kind,row in self.records.items():self.mock('get_'+kind+'_by_id',return_value=row)
        self.mock('get_all_inventory_categories',return_value=[self.records['inventory_category']])
        self.mock('get_active_inventory_categories',return_value=[self.records['inventory_category']])
        self.mock('get_all_inventory_items',return_value=[self.records['inventory_item']])
        self.mock('get_all_warehouses',return_value=[self.records['warehouse']])
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)

    def mock(self,name,**kwargs):return self.stack.enter_context(patch.object(self.erp,name,**kwargs))

    def cases(self):
        result=[]
        for section,kind,identifier,code,data in [
                ('categories','inventory_category',1,'CAT',dict(category_code='CAT',category_name='private-name',description='private-description')),
                ('warehouses','warehouse',2,'WH',dict(warehouse_code='WH',warehouse_name='private-name',location='private-location')),
                ('items','inventory_item',3,'ITEM',dict(item_code='ITEM',item_name='private-name',category_id='1',unit_of_measure='pcs',reorder_level='0',description='private-description'))]:
            result.extend([(f'/inventory/{section}/add',data,'create_'+kind,identifier,'CREATE',kind.upper(),identifier,code),
                           (f'/inventory/{section}/{identifier}/edit',data,'update_'+kind,None,'UPDATE',kind.upper(),identifier,code),
                           (f'/inventory/{section}/{identifier}/status',{},'set_'+kind+'_active_status',True,'DEACTIVATE',kind.upper(),identifier,code)])
        for direction in ('in','out'):
            result.append((f'/inventory/stock/{direction}',dict(item_id='3',warehouse_id='2',quantity='0.10',notes='private-notes',submission_id='private-uuid'),'stock_'+direction,StockResult(9,True),'STOCK_'+direction.upper(),'STOCK_MOVEMENT',9,'ITEM'))
        return result

    def test_success_actor_numeric_id_readable_description_and_no_sensitive_contents(self):
        for path,data,operation,result,action,entity,identifier,code in self.cases():
            with self.subTest(path=path),patch.object(self.erp,operation,return_value=result) as write:
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                for key,value in dict(user_id=7,username='acting.user',module='INVENTORY',action=action,entity_type=entity,entity_id=identifier).items():self.assertEqual(event[key],value)
                self.assertIn(code,event['description']);self.assertIn(str(identifier),event['description'])
                if entity=='STOCK_MOVEMENT':self.assertIn('WH',event['description'])
                for secret in ('private-name','private-description','private-location','private-notes','private-uuid'):self.assertNotIn(secret,str(event))
        for kind,row in self.records.items():
            row['is_active']=False
            section={'inventory_category':'categories','warehouse':'warehouses','inventory_item':'items'}[kind]
            identifier=row[{'inventory_category':'category_id','warehouse':'warehouse_id','inventory_item':'item_id'}[kind]]
            with patch.object(self.erp,'set_'+kind+'_active_status',return_value=True):
                self.audit.reset_mock();self.assertEqual(self.client.post(f'/inventory/{section}/{identifier}/status').status_code,302)
                self.audit.assert_called_once();self.assertEqual(self.audit.call_args.kwargs['action'],'ACTIVATE')

    def test_failed_business_actions_and_commit_errors_never_emit_success(self):
        for error in (ValueError('failed or rolled back'),mysql.connector.InterfaceError('commit failed',errno=2013)):
            for path,data,operation,*_ in self.cases():
                with self.subTest(path=path,error=type(error).__name__),patch.object(self.erp,operation,side_effect=error):
                    self.audit.reset_mock()
                    try:self.client.post(path,data=data)
                    except (ValueError,mysql.connector.Error):pass
                    self.audit.assert_not_called()

    def test_noop_or_failed_status_transition_never_emits_success(self):
        for path,data,operation,*_ in self.cases():
            if not path.endswith('/status'):continue
            with patch.object(self.erp,operation,return_value=False):
                self.assertEqual(self.client.post(path).status_code,302);self.audit.assert_not_called()

    def test_missing_invalid_csrf_and_revoked_permissions_prevent_writes(self):
        raw=self.erp.app.test_client()
        with raw.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        for path,data,operation,*_ in self.cases():
            with patch.object(self.erp,operation) as write:
                for extra in ({},{'csrf_token':'invalid'}):
                    self.assertEqual(raw.post(path,data=dict(data,**extra)).status_code,400)
                write.assert_not_called();self.audit.assert_not_called()
        self.state['permissions']=frozenset()
        for path,data,operation,*_ in self.cases():
            with patch.object(self.erp,operation) as write:
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_not_called();self.audit.assert_not_called()

    def test_audit_insert_failure_keeps_business_success(self):
        self.audit.side_effect=RuntimeError('audit unavailable')
        for path,data,operation,result,*_ in self.cases():
            with self.subTest(path=path),patch.object(self.erp,operation,return_value=result) as write:
                self.assertEqual(self.client.post(path,data=data).status_code,302);write.assert_called_once()

    def test_saved_uuid_replays_do_not_log_and_separate_new_movements_do(self):
        for direction in ('in','out'):
            self.audit.reset_mock()
            results=[StockResult(9,True),StockResult(9,False),StockResult(10,True),StockResult(10,False)]
            with patch.object(self.erp,'stock_'+direction,side_effect=results):
                for _ in results:
                    self.assertEqual(self.client.post('/inventory/stock/'+direction,data=dict(item_id='3',warehouse_id='2',quantity='0.10',submission_id='opaque')).status_code,302)
            self.assertEqual(self.audit.call_count,2)
            self.assertEqual([call.kwargs['entity_id'] for call in self.audit.call_args_list],[9,10])
