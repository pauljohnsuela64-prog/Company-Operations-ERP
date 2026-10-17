"""Inventory reporting input, source-link permissions and read-only report behavior."""
from contextlib import ExitStack
from datetime import datetime
from decimal import Decimal
import importlib
import unittest
from unittest.mock import patch, MagicMock
import inventory_reporting as reports
from security_helpers import csrf_client, stamp_session, user_state


class ReportingValidationTests(unittest.TestCase):
    def test_invalid_filters_rejected_before_database_connection(self):
        for values in ({'item_id':'bad'},{'warehouse_id':'0'},{'page':'-1'},{'page_size':'101'},
                       {'movement_type':'DELETE'},{'date_from':'2026-02-30'},{'date_to':'20261018'},
                       {'date_from':'2026-10-19','date_to':'2026-10-18'},{'q':'x'*201}):
            with self.subTest(values=values),patch.object(reports,'get_connection') as connect:
                with self.assertRaises(ValueError):reports.get_movement_page(**values)
                connect.assert_not_called()
        self.assertEqual(reports.report_filters({'page_size':'100'})['page_size'],100)

    def test_search_literal_and_dates_are_bound_not_interpolated(self):
        with patch.object(reports,'_page',return_value={}) as page:
            reports.get_movement_page(item_id='1',warehouse_id='2',movement_type='IN',q="%' OR 1=1 --_",date_from='2026-10-01',date_to='2026-10-18')
        args=page.call_args.args
        self.assertNotIn("OR 1=1 --",args[2]);self.assertIn('sm.item_id=%s',args[2])
        self.assertEqual(args[3][0:3],[1,2,'IN'])
        self.assertEqual(args[3][3],datetime(2026,10,1))
        self.assertEqual(args[3][4],datetime(2026,10,18,23,59,59,999999))
        self.assertIn('=%',args[3][5]);self.assertIn('=_',args[3][5])

    def test_pagination_uses_readonly_snapshot_and_clamps_missing_page(self):
        connection=MagicMock();cursor=connection.cursor.return_value
        cursor.fetchone.return_value={'total':3};cursor.fetchall.return_value=[{'movement_id':1}]
        with patch.object(reports,'get_connection',return_value=connection):
            page=reports.get_movement_page(page=999,page_size=2)
        self.assertEqual((page['page'],page['pages'],page['total']),(2,2,3))
        connection.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',consistent_snapshot=True,readonly=True)
        self.assertEqual(cursor.execute.call_args.args[1],(2,2))
        connection.commit.assert_not_called();connection.rollback.assert_called_once()
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_reconciliation_does_not_claim_history_completeness(self):
        base=dict(item_code='I',warehouse_code='W',has_balance=True,quantity=Decimal('10'),movement_count=1,movement_balance=Decimal('10'),unsupported_count=0)
        rows=[dict(base),dict(base,quantity=Decimal('12')),dict(base,movement_count=0,movement_balance=None),dict(base,has_balance=False,quantity=None),dict(base,unsupported_count=1),dict(base,quantity=Decimal('-1'))]
        with patch.object(reports,'_page',return_value={'rows':rows}):reports.get_reconciliation_page()
        self.assertEqual(rows[0]['difference'],Decimal('0'));self.assertIn('coverage unverified',rows[0]['comparison'])
        self.assertEqual(rows[1]['difference'],Decimal('2'));self.assertIn('coverage unverified',rows[1]['comparison'])
        for row in rows[2:]:self.assertIsNone(row['difference'])
        self.assertIn('opening balance unknown',rows[2]['comparison'])


class ReportingRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='reporting-tests-only',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.state=user_state(permissions=['inventory.view'])
        self.mock('get_authorization_state',side_effect=lambda _:self.state)
        self.audit=self.mock('create_audit_log')
        self.mock('get_all_inventory_items',return_value=[]);self.mock('get_all_warehouses',return_value=[])
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)

    def mock(self,name,**kwargs):return self.stack.enter_context(patch.object(self.erp,name,**kwargs))

    def test_receipt_links_require_procurement_permission_and_supported_source(self):
        row=dict(movement_id=1,item_id=1,warehouse_id=1,movement_type='IN',quantity=Decimal('1'),reference_type='GOODS_RECEIPT',reference_id=7,notes='<private>',created_at=datetime(2026,10,18),item_code='I',item_name='Item',unit_of_measure='pcs',warehouse_code='W',warehouse_name='Warehouse',created_by_username='user',source_receipt_id=7,receipt_number='GR-000007')
        self.mock('get_movement_page',return_value=dict(rows=[row],total=1,page=1,pages=1,page_size=50))
        html=self.client.get('/inventory/stock/movements').get_data(as_text=True)
        self.assertIn('GR-000007',html);self.assertNotIn('href="/procurement/receipts/history/7"',html);self.assertIn('&lt;private&gt;',html)
        self.state['permissions']=frozenset(['inventory.view','procurement.view'])
        html=self.client.get('/inventory/stock/movements').get_data(as_text=True)
        self.assertIn('href="/procurement/receipts/history/7"',html)
        row['source_receipt_id']=None;row['receipt_number']=None
        html=self.client.get('/inventory/stock/movements').get_data(as_text=True)
        self.assertIn('source unavailable',html);self.assertNotIn('href="/procurement/receipts/history/7"',html)
        self.audit.assert_not_called()

    def test_filter_errors_and_permission_denial_do_not_run_report(self):
        for path,name in (('/inventory/stock/movements','get_movement_page'),('/inventory/stock/reconciliation','get_reconciliation_page')):
            with patch.object(self.erp,name) as reader:
                self.assertEqual(self.client.get(path+'?page_size=100000').status_code,400);reader.assert_not_called()
                self.state['permissions']=frozenset()
                self.assertEqual(self.client.get(path).status_code,302);reader.assert_not_called()
                self.state['permissions']=frozenset(['inventory.view'])
        self.audit.assert_not_called()
