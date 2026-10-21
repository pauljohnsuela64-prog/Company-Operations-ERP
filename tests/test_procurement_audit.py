"""Procurement action audit boundaries with real guards, CSRF and audit helper."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch
from goods_receipt_repository import ReceiptResult
from security_helpers import user_state, stamp_session, csrf_client


class ProcurementAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='audit-test-only',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state=user_state(permissions=['procurement.view','procurement.suppliers.manage','procurement.orders.create','procurement.orders.manage','procurement.receipts.manage'])
        self.mock('get_authorization_state',side_effect=lambda _:self.state)
        self.audit=self.mock('create_audit_log')
        self.mock('render_template',return_value='form')
        self.mock('get_supplier_by_id',return_value=dict(supplier_id=1,supplier_code='SUP-1',is_active=True))
        self.mock('get_purchase_request_by_id',return_value=dict(status='APPROVED'))
        self.mock('get_purchase_orders_by_request',return_value=[])
        self.mock('get_purchase_request_items',return_value=[{}])
        self.mock('get_active_suppliers',return_value=[])
        self.mock('get_purchase_order_by_id',return_value=dict(status='DRAFT',po_number='PO-42'))
        self.mock('get_purchase_order_item_by_id',return_value=dict(purchase_order_id=42))
        self.mock('get_receivable_purchase_order_items',return_value=[])
        self.mock('get_all_warehouses',return_value=[])
        self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)

    def mock(self,name,**kwargs):return self.stack.enter_context(patch.object(self.erp,name,**kwargs))

    def cases(self):
        return [
          ('/procurement/suppliers/add',dict(supplier_code='SUP-1',supplier_name='private-name',address='private-address'),'create_supplier',1,'CREATE','SUPPLIER',1,'SUP-1'),
          ('/procurement/suppliers/1/edit',dict(supplier_code='SUP-1',supplier_name='private-name'),'update_supplier',True,'UPDATE','SUPPLIER',1,'SUP-1'),
          ('/procurement/suppliers/1/status',{},'set_supplier_active_status',True,'DEACTIVATE','SUPPLIER',1,'SUP-1'),
          ('/procurement/requests/7/create-order',dict(supplier_id='1',notes='private-notes'),'create_purchase_order_from_request',(42,'PO-42'),'CREATE','PURCHASE_ORDER',42,'PO-42'),
          ('/procurement/orders/42/items/5/edit-cost',dict(unit_cost='2.50'),'update_purchase_order_item_cost',None,'UPDATE_COST','PURCHASE_ORDER',42,'PO-42'),
          ('/procurement/orders/42/send',{},'send_purchase_order',True,'MARK_SENT','PURCHASE_ORDER',42,'PO-42'),
          ('/procurement/orders/42/cancel',{},'cancel_purchase_order',True,'CANCEL','PURCHASE_ORDER',42,'PO-42'),
          ('/procurement/receipts/42/receive',dict(warehouse_id='1',submission_id='opaque-uuid',quantity_received_5='1',notes='private-notes'),'create_goods_receipt',ReceiptResult(9,'GR-9','RECEIVED',created=True),'RECEIVE','GOODS_RECEIPT',9,'GR-9'),
        ]

    def test_all_success_events_actor_identifiers_and_sensitive_data(self):
        for path,data,operation,result,action,entity,identifier,readable in self.cases():
            with self.subTest(action=action,entity=entity),patch.object(self.erp,operation,return_value=result) as write:
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                for key,value in dict(user_id=7,username='acting.user',module='PROCUREMENT',action=action,entity_type=entity,entity_id=identifier).items():self.assertEqual(event[key],value)
                self.assertIn(readable,event['description']);self.assertIn(str(identifier),event['description'])
                for secret in ('private-name','private-address','private-notes','opaque-uuid'):self.assertNotIn(secret,str(event))
        self.mock('get_supplier_by_id',return_value=dict(supplier_id=1,supplier_code='SUP-1',is_active=False))
        self.mock('set_supplier_active_status')
        self.audit.reset_mock();self.client.post('/procurement/suppliers/1/status')
        self.assertEqual(self.audit.call_args.kwargs['action'],'ACTIVATE')

    def test_business_failures_and_denied_permissions_never_log_success(self):
        for path,data,operation,*_ in self.cases():
            with self.subTest(path=path),patch.object(self.erp,operation,side_effect=ValueError('failed or rolled back')):
                self.audit.reset_mock()
                try:self.client.post(path,data=data)
                except ValueError:pass  # Existing unhandled failures still cannot log success.
                self.audit.assert_not_called()
        self.state['permissions']=frozenset()
        for path,data,operation,*_ in self.cases():
            with patch.object(self.erp,operation) as write:
                self.audit.reset_mock();self.assertEqual(self.client.post(path,data=data).status_code,302)
                write.assert_not_called();self.audit.assert_not_called()

    def test_csrf_rejection_precedes_writes_and_audit(self):
        raw=self.erp.app.test_client()
        with raw.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        for path,data,operation,*_ in self.cases():
            for token in (None,'invalid'):
                with patch.object(self.erp,operation) as write:
                    self.audit.reset_mock()
                    form=dict(data)
                    if token:form['csrf_token']=token
                    self.assertEqual(raw.post(path,data=form).status_code,400)
                    write.assert_not_called();self.audit.assert_not_called()

    def test_audit_failure_does_not_undo_success(self):
        self.audit.side_effect=RuntimeError('audit unavailable')
        for path,data,operation,result,*_ in self.cases():
            with self.subTest(path=path),patch.object(self.erp,operation,return_value=result) as write:
                self.assertEqual(self.client.post(path,data=data).status_code,302);write.assert_called_once()

    def test_receiving_replays_do_not_audit_again_and_separate_deliveries_do(self):
        path,data,operation,*_=self.cases()[-1]
        results=[ReceiptResult(9,'GR-9','PARTIALLY_RECEIVED',created=True),ReceiptResult(9,'GR-9','PARTIALLY_RECEIVED'),ReceiptResult(10,'GR-10','RECEIVED',created=True),ReceiptResult(10,'GR-10','RECEIVED')]
        with patch.object(self.erp,operation,side_effect=results):
            for _ in results:self.assertEqual(self.client.post(path,data=data).status_code,302)
        self.assertEqual(self.audit.call_count,2)
        self.assertEqual([call.kwargs['entity_id'] for call in self.audit.call_args_list],[9,10])

    def test_false_send_does_not_log(self):
        self.mock('send_purchase_order',return_value=False)
        self.client.post('/procurement/orders/42/send');self.audit.assert_not_called()

    def test_cancel_identifier_lookup_failure_does_not_fail_committed_action(self):
        self.mock('cancel_purchase_order',return_value=True)
        self.mock('get_purchase_order_by_id',side_effect=RuntimeError('lookup unavailable'))
        self.assertEqual(self.client.post('/procurement/orders/42/cancel').status_code,302)
        self.audit.assert_called_once()
        self.assertEqual(self.audit.call_args.kwargs['entity_id'],42)
        self.assertIn('42',self.audit.call_args.kwargs['description'])
