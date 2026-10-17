"""Purchase Order UI routes and permission controls without database access."""
from contextlib import ExitStack
from decimal import Decimal
from html.parser import HTMLParser
import importlib
import os
import unittest
from unittest.mock import patch
from security_helpers import csrf_client, user_state, stamp_session


class DivBalance(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.depth = 0
        self.minimum = 0
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            self.depth += 1
    def handle_endtag(self, tag):
        if tag == 'div':
            self.depth -= 1
            self.minimum = min(self.minimum, self.depth)


class PurchaseOrderUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safety = ExitStack()
        cls.addClassCleanup(cls.safety.close)
        cls.safety.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.safety.enter_context(patch.dict(os.environ, SECRET_KEY='isolated-ui-test'))
        cls.safety.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company database access forbidden')))
        cls.erp = importlib.import_module('app')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.client = csrf_client(self.erp.app)
        self.mock('get_authorization_state', side_effect=lambda _: self.state)
        self.permissions('procurement.view', 'procurement.orders.manage', 'procurement.receipts.manage')
        self.order = dict(purchase_order_id=42, po_number='PO-000042', request_id=7, request_number='PR-000007', status='DRAFT', supplier_id=1, supplier_name='Supplier', supplier_code='SUP', order_date='2026-10-17', expected_delivery_date=None, notes='Delivery notes', created_by_username='test')
        self.items = [dict(purchase_order_item_id=5, item_code='ITEM', item_name='Test item', unit_of_measure='pcs', quantity=Decimal('10.25'), estimated_unit_cost=Decimal('2.50'), unit_cost=Decimal('2.50'), received_quantity=Decimal('4.25'), remaining_quantity=Decimal('6'), notes=None)]
        self.po = self.mock('get_purchase_order_by_id', return_value=self.order)
        self.mock('get_purchase_order_items', side_effect=lambda _:[dict(item) for item in self.items])
        self.mock('get_goods_receipts_by_purchase_order', return_value=[])
        self.mock('get_supplier_by_id', return_value=dict(address='Address', contact_person='Contact', email='supplier@example.test', phone='123'))
        self.request = dict(request_id=7, request_number='PR-000007', status='APPROVED', purpose='Test', requested_by_username='test', department_name=None)
        self.mock('get_purchase_request_by_id', return_value=self.request)
        self.mock('get_purchase_request_items', return_value=self.items)
        self.linked = self.mock('get_purchase_orders_by_request', return_value=[])

    def mock(self, name, **kwargs):
        return self.stack.enter_context(patch.object(self.erp, name, **kwargs))

    def permissions(self, *permissions):
        with self.client.session_transaction() as session:
            self.state = user_state(user_id=1, username='test', permissions=permissions)
            stamp_session(self.erp.app, session, self.state)

    def test_action_visibility_by_status_and_permission(self):
        for status in ('DRAFT', 'SENT', 'PARTIALLY_RECEIVED', 'RECEIVED', 'CANCELLED'):
            for manage, receive in ((False,False),(True,False),(False,True),(True,True)):
                with self.subTest(status=status, manage=manage, receive=receive):
                    self.order['status']=status
                    perms=['procurement.view']
                    if manage: perms.append('procurement.orders.manage')
                    if receive: perms.append('procurement.receipts.manage')
                    self.permissions(*perms)
                    response=self.client.get('/procurement/orders/42')
                    self.assertEqual(response.status_code,200)
                    html=response.get_data(as_text=True)
                    self.assertEqual('/procurement/orders/42/cancel' in html, manage and status in ('DRAFT','SENT'))
                    self.assertEqual('/procurement/orders/42/send' in html, manage and status=='DRAFT')
                    self.assertEqual('/procurement/orders/42/items/5/edit-cost' in html, manage and status=='DRAFT')
                    self.assertEqual('/procurement/receipts/42/receive' in html, receive and status in ('SENT','PARTIALLY_RECEIVED'))
                    self.assertIn('/procurement/orders/42/print',html)
                    self.assertIn('id="erp-navigation"',html)
                    balance=DivBalance(html)
                    self.assertEqual((balance.depth,balance.minimum),(0,0))

    def test_quantities_and_rounded_totals(self):
        html=self.client.get('/procurement/orders/42').get_data(as_text=True)
        self.assertIn('Already Received',html)
        self.assertIn('class="received-quantity">4.25 pcs',html)
        self.assertIn('class="remaining-quantity">6 pcs',html)
        self.assertIn('25.63',html)

    def test_cancel_hidden_when_receipts_exist_even_if_inconsistent_status(self):
        self.order['status']='SENT'
        self.mock('get_goods_receipts_by_purchase_order',return_value=[dict(receipt_id=1,receipt_number='GR-1',total_quantity_received=1)])
        html=self.client.get('/procurement/orders/42').get_data(as_text=True)
        self.assertNotIn('/procurement/orders/42/cancel',html)

    def test_linked_po_and_create_visibility(self):
        for status in ('DRAFT','APPROVED','COMPLETED'):
            for linked_status in (None,'DRAFT','SENT','PARTIALLY_RECEIVED','RECEIVED','CANCELLED'):
                for manage in (False,True):
                    with self.subTest(status=status,linked=linked_status,manage=manage):
                        self.request['status']=status
                        self.linked.return_value=[] if linked_status is None else [dict(purchase_order_id=42,po_number='PO-000042',status=linked_status)]
                        self.permissions('procurement.view',*(['procurement.orders.manage'] if manage else []))
                        html=self.client.get('/procurement/requests/7').get_data(as_text=True)
                        self.assertEqual('/procurement/requests/7/create-order' in html,status=='APPROVED' and manage and linked_status in (None,'CANCELLED'))
                        if linked_status:
                            self.assertIn('PO-000042',html)
                            self.assertIn(linked_status.replace('_',' ').title(),html)
                            self.assertIn('/procurement/orders/42',html)

    def test_create_route_redirects_to_active_order_and_blocks_empty_requests(self):
        operation=self.mock('create_purchase_order_from_request')
        self.linked.return_value=[dict(purchase_order_id=42,po_number='PO-000042',status='SENT')]
        for method in ('get','post'):
            response=getattr(self.client,method)('/procurement/requests/7/create-order')
            self.assertTrue(response.location.endswith('/procurement/orders/42'))
        operation.assert_not_called()
        self.linked.return_value=[]
        self.mock('get_purchase_request_items',return_value=[])
        self.assertTrue(self.client.get('/procurement/requests/7/create-order').location.endswith('/procurement/requests/7'))
        html=self.client.get('/procurement/requests/7').get_data(as_text=True)
        self.assertNotIn('/procurement/requests/7/create-order',html)

    def test_print_layout_content_escaping_and_decimal_accuracy(self):
        self.order['notes']='<script>unsafe</script>'
        self.items=[dict(self.items[0],quantity=Decimal('9999999999.99'),unit_cost=Decimal('9999999999.99'))]
        html=self.client.get('/procurement/orders/42/print').get_data(as_text=True)
        for text in ('PO-000042','Supplier','Address','supplier@example.test','2026-10-17','Test item','99,999,999,999,800,000,000.00','@media print','window.print()','display: table-header-group','DRAFT — Not issued'):
            self.assertIn(text,html)
        self.assertIn('&lt;script&gt;unsafe&lt;/script&gt;',html)
        self.assertNotIn('<script>unsafe</script>',html)
        self.assertNotIn('id="erp-navigation"',html)
        self.assertNotIn('Payment Terms',html)
        self.order['status']='CANCELLED'
        self.assertIn('CANCELLED — Do not fulfil',self.client.get('/procurement/orders/42/print').get_data(as_text=True))

    def test_print_and_po_actions_preserve_permissions(self):
        send=self.mock('send_purchase_order',return_value=True)
        cancel=self.mock('cancel_purchase_order',return_value=True)
        self.permissions('procurement.view')
        self.assertEqual(self.client.post('/procurement/orders/42/send').status_code,302)
        self.assertEqual(self.client.post('/procurement/orders/42/cancel').status_code,302)
        send.assert_not_called()
        cancel.assert_not_called()
        self.permissions()
        self.assertEqual(self.client.get('/procurement/orders/42/print').status_code,302)

    def test_manual_send_labels_and_missing_print_order(self):
        html=self.client.get('/procurement/orders/42').get_data(as_text=True)
        self.assertIn('Mark as Sent',html)
        self.assertIn('manually issued',html)
        self.assertNotIn('Send this purchase order to the supplier?',html)
        self.po.return_value=None
        self.assertTrue(self.client.get('/procurement/orders/42/print').location.endswith('/procurement/orders'))


if __name__=='__main__':
    unittest.main()
