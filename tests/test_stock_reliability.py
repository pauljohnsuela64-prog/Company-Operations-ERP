import uuid
"""Manual stock validation, route security and safe retry boundaries; no database."""
import importlib
from contextlib import ExitStack
from decimal import Decimal
import unittest
from unittest.mock import patch, MagicMock
import mysql.connector
import stock_repository as stock
from security_helpers import user_state, stamp_session, csrf_client


class StockReliabilityTests(unittest.TestCase):
    def test_invalid_inputs_never_open_connection(self):
        for operation in (stock.stock_in,stock.stock_out):
            for value in ('0','-1','NaN','sNaN','Infinity','-Infinity','bad','0.001','9999999999.999','10000000000',None):
                with self.subTest(operation=operation.__name__,quantity=value),patch.object(stock,'get_connection') as connect:
                    with self.assertRaises(ValueError):operation(1,1,value,None,1, submission_id=str(uuid.uuid4()))
                    connect.assert_not_called()
            for item,warehouse in ((0,1),(1,0),('bad',1),(1.5,1),(True,1)):
                with patch.object(stock,'get_connection') as connect:
                    with self.assertRaises(ValueError):operation(item,warehouse,'1',None,1, submission_id=str(uuid.uuid4()))
                    connect.assert_not_called()
            with patch.object(stock,'get_connection') as connect:
                with self.assertRaisesRegex(ValueError,'255'):operation(1,1,'1','x'*256,1, submission_id=str(uuid.uuid4()))
                connect.assert_not_called()

    def test_confirmed_lock_rollbacks_retry_boundedly_with_same_decimal(self):
        with patch.object(stock,'_stock_transaction',side_effect=[stock._RetryableStockError(),None]) as transaction:
            stock.stock_in(1,1,'0.10',None,1, submission_id=str(uuid.uuid4()))
            self.assertEqual(transaction.call_count,2)
            self.assertEqual(transaction.call_args_list[0],transaction.call_args_list[1])
            self.assertIsInstance(transaction.call_args.args[2],Decimal)
        with patch.object(stock,'_stock_transaction',side_effect=stock._RetryableStockError()) as transaction:
            with self.assertRaisesRegex(ValueError,'No changes were saved'):stock.stock_out(1,1,'1',None,1, submission_id=str(uuid.uuid4()))
            self.assertEqual(transaction.call_count,3)

    def test_uncertain_database_errors_never_retry(self):
        with patch.object(stock,'_stock_transaction',side_effect=mysql.connector.InterfaceError('lost',errno=2013)) as transaction:
            with self.assertRaisesRegex(ValueError,'same submission identifier'):stock.stock_in(1,1,'1',None,1, submission_id=str(uuid.uuid4()))
            transaction.assert_called_once()

    def test_commit_error_is_not_classified_as_retryable(self):
        connection=MagicMock();cursor=connection.cursor.return_value
        cursor.fetchone.side_effect=[None,{'is_active':True},{'is_active':True},{'quantity':Decimal('1')},None]
        connection.commit.side_effect=mysql.connector.DatabaseError('commit failed',errno=1213)
        with patch.object(stock,'get_connection',return_value=connection):
            with self.assertRaisesRegex(ValueError,'could not be confirmed'):stock.stock_in(1,1,'1',None,1, submission_id=str(uuid.uuid4()))
        connection.commit.assert_called_once();connection.rollback.assert_called_once()

    def test_lock_error_retries_only_after_successful_rollback(self):
        for errno in (1205,1213):
            connection=MagicMock();connection.cursor.return_value.execute.side_effect=mysql.connector.DatabaseError('lock',errno=errno)
            with patch.object(stock,'get_connection',return_value=connection):
                with self.assertRaises(stock._RetryableStockError):
                    stock._stock_transaction(1,1,Decimal('1'),None,1,incoming=True, submission_id=str(uuid.uuid4()))
            connection.rollback.assert_called_once();connection.commit.assert_not_called()
        connection.rollback.side_effect=mysql.connector.InterfaceError('rollback failed',errno=2013)
        with patch.object(stock,'get_connection',return_value=connection) as connect:
            with self.assertRaisesRegex(ValueError,'could not be confirmed'):stock.stock_in(1,1,'1',None,1, submission_id=str(uuid.uuid4()))
            connect.assert_called_once()


class StockRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',ERP_ENV='testing',SECRET_KEY='stock-tests-only',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.state=user_state(permissions=['inventory.view','inventory.stock.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        for name in ('get_all_inventory_items','get_all_warehouses'):
            self.stack.enter_context(patch.object(self.erp,name,return_value=[]))
        self.stack.enter_context(patch.object(self.erp,'render_template',return_value='form'))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)

    def test_valid_routes_pass_decimal_and_invalid_quantities_do_not_write(self):
        for direction in ('in','out'):
            with patch.object(self.erp,'stock_'+direction) as write:
                path='/inventory/stock/'+direction
                self.assertEqual(self.client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':'0.10','submission_id':str(uuid.uuid4())}).status_code,302)
                self.assertEqual(write.call_args.args[2],Decimal('0.10'))
                self.assertIsInstance(write.call_args.args[2],Decimal)
                write.reset_mock()
                for value in ('NaN','Infinity','0','-1','0.001','10000000000'):
                    self.assertEqual(self.client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':value,'submission_id':str(uuid.uuid4())}).status_code,200)
                write.assert_not_called();self.audit.assert_not_called()

    def test_csrf_permissions_and_repository_errors(self):
        for direction in ('in','out'):
            path='/inventory/stock/'+direction
            with patch.object(self.erp,'stock_'+direction) as write:
                raw=self.erp.app.test_client()
                with raw.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
                for form in ({},{'csrf_token':'invalid'}):self.assertEqual(raw.post(path,data=form).status_code,400)
                write.assert_not_called()
                write.side_effect=ValueError('Warehouse does not exist or is inactive.')
                self.assertEqual(self.client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':'1','submission_id':str(uuid.uuid4())}).status_code,200)
                write.reset_mock();self.state['permissions']=frozenset()
                self.assertEqual(self.client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':'1','submission_id':str(uuid.uuid4())}).status_code,302)
                write.assert_not_called();self.audit.assert_not_called()
                self.state['permissions']=frozenset(['inventory.stock.manage'])


class StockIdempotencyTests(unittest.TestCase):
    def test_missing_or_invalid_uuid_never_opens_database(self):
        for operation in (stock.stock_in,stock.stock_out):
            for token in (None,'','invalid'):
                with patch.object(stock,'get_connection') as connect:
                    with self.assertRaisesRegex(ValueError,'submission identifier'):
                        operation(1,1,'1',None,1,submission_id=token)
                    connect.assert_not_called()

    def test_replay_payload_includes_actor_direction_and_all_business_fields(self):
        cursor=MagicMock()
        row=dict(movement_id=9,item_id=1,warehouse_id=2,movement_type='IN',quantity=Decimal('0.10'),notes=None,created_by=7,reference_type='MANUAL_STOCK_IN')
        cursor.fetchone.return_value=row
        result=stock._existing_submission(cursor,'uuid',1,2,Decimal('0.10'),'',7,True)
        self.assertEqual(result.movement_id,9);self.assertFalse(result.created)
        for changes in ({'item_id':3},{'warehouse_id':3},{'quantity':Decimal('0.11')},{'notes':'changed'},{'created_by':8},{'movement_type':'OUT'},{'reference_type':'GOODS_RECEIPT'}):
            cursor.fetchone.return_value=dict(row,**changes)
            with self.assertRaisesRegex(ValueError,'different stock transaction'):
                stock._existing_submission(cursor,'uuid',1,2,Decimal('0.10'),None,7,True)

    def test_missing_migration_reports_clear_error(self):
        for errno in (1054,1146):
            with patch.object(stock,'_stock_transaction',side_effect=mysql.connector.ProgrammingError('schema',errno=errno)):
                with self.assertRaisesRegex(ValueError,'migration'):
                    stock.stock_in(1,1,'1',None,1,submission_id=str(uuid.uuid4()))

    def test_uuid_collision_lookup_outage_is_graceful_and_never_replays(self):
        with patch.object(stock,'_stock_transaction',side_effect=mysql.connector.IntegrityError('collision',errno=1062)) as transaction:
            with patch.object(stock,'get_connection',side_effect=mysql.connector.InterfaceError('outage',errno=2013)):
                with self.assertRaisesRegex(ValueError,'same submission identifier'):
                    stock.stock_in(1,1,'1',None,1,submission_id=str(uuid.uuid4()))
            transaction.assert_called_once()
