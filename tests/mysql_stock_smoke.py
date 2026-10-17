"""Disposable MySQL manual stock/receiving reliability; synthetic records only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
import uuid
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur=connection.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_stock_test');cur.execute('USE erp_stock_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        connection.commit()
    options['database']='erp_stock_test'
    local=threading.local()
    class Proxy:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            if getattr(local,'hold',None):
                entered,release=local.hold;entered.set();assert release.wait(10)
            self.connection.commit()
            if getattr(local,'lost',False):
                local.lost=False
                raise mysql.connector.InterfaceError('lost commit response',errno=2013)
        def __enter__(self):return self
        def __exit__(self,*args):self.connection.close()
    def connect():return Proxy(mysql.connector.connect(**options))
    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as connection:
            cur=connection.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit();return result
    def snapshot():
        return [sql('SELECT * FROM '+table+' ORDER BY 1,2',fetch=True) for table in ('inventory_stock','stock_movements','goods_receipts','goods_receipt_items','purchase_requests','purchase_orders','audit_logs')]
    def fails(action,text=None):
        try:action()
        except ValueError as error:
            if text:assert text in str(error),str(error)
            return error
        raise AssertionError('Invalid operation succeeded')
    def parallel(*actions):
        barrier=threading.Barrier(len(actions))
        def execute(action):
            barrier.wait(5)
            try:return action()
            except ValueError as error:return error
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures=[pool.submit(execute,action) for action in actions]
            return [future.result(timeout=20) for future in futures]
    def balance(item=1):return sql('SELECT quantity FROM inventory_stock WHERE item_id=%s AND warehouse_id=1',(item,),True)[0][0]
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Stock test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'stock.test','synthetic')")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name,is_active) VALUES (1,'W1','Warehouse',TRUE),(2,'OFF','Inactive',FALSE)")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name,is_active) VALUES (1,'I1','Item',TRUE),(2,'OFF','Inactive',FALSE),(3,'I3','Concurrent',TRUE),(4,'I4','Mixed receiving',TRUE),(5,'I5','Rollback reservation',TRUE)")
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES (1,'TEST','Synthetic')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',ERP_ENV='testing',SECRET_KEY='stock-mysql-tests-only',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        modules=[importlib.import_module(name) for name in ('stock_repository','purchase_request_repository','purchase_order_repository','goods_receipt_repository')]
        for module in modules:stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        stock,pr,po,gr=modules
        assert all(row[0]=='InnoDB' for row in sql("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE()",fetch=True))
        for table,column in (('inventory_stock','quantity'),('stock_movements','quantity')):
            assert sql('SELECT NUMERIC_PRECISION,NUMERIC_SCALE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s',(table,column),True)==[(12,2)]
        print('Database compatibility:',sql('SELECT VERSION()',fetch=True)[0][0], 'InnoDB / DECIMAL(12,2) verified')
        stock.stock_in(1,1,'0.10','decimal',1);stock.stock_out(1,1,'0.10','exact',1)
        assert balance()==Decimal('0.00')
        assert sql('SELECT movement_type,quantity,reference_type,reference_id,created_by FROM stock_movements ORDER BY movement_id',fetch=True)==[('IN',Decimal('0.10'),'MANUAL_STOCK_IN',None,1),('OUT',Decimal('0.10'),'MANUAL_STOCK_OUT',None,1)]
        before=snapshot()
        for operation in (stock.stock_in,stock.stock_out):
            for value in ('0','-1','NaN','Infinity','sNaN','bad','0.001','10000000000'):
                fails(lambda:operation(1,1,value,None,1));assert snapshot()==before
            for item,warehouse in ((2,1),(99999,1),(1,2),(1,99999)):
                fails(lambda:operation(item,warehouse,'1',None,1),'does not exist or is inactive');assert snapshot()==before
            fails(lambda:operation(1,1,'1','x'*256,1),'255');assert snapshot()==before
        fails(lambda:stock.stock_out(1,1,'0.01',None,1),'Insufficient');assert snapshot()==before
        fails(lambda:stock.stock_out(3,1,'1',None,1),'No stock');assert snapshot()==before
        stock.stock_in(1,1,'9999999999.99',None,1)
        before=snapshot()
        fails(lambda:stock.stock_in(1,1,'0.01',None,1),'Resulting');assert snapshot()==before
        # Explicitly prove overflow validation without strict SQL mode.
        def permissive():
            connection=connect();cur=connection.cursor();cur.execute("SET SESSION sql_mode=''");cur.close();return connection
        with patch.object(stock,'get_connection',side_effect=permissive):fails(lambda:stock.stock_in(1,1,'0.01',None,1),'Resulting')
        assert snapshot()==before
        stock.stock_out(1,1,'9999999999.99',None,1)
        print('PASS Decimal exact withdrawal, limits, inactive/missing masters, insufficient stock and non-strict overflow safety')
        # Atomic first-row creation, existing-row contention and excessive withdrawals.
        assert parallel(lambda:stock.stock_in(3,1,'1.25',None,1),lambda:stock.stock_in(3,1,'2.75',None,1))==[None,None]
        assert balance(3)==Decimal('4')
        results=parallel(lambda:stock.stock_out(3,1,'3',None,1),lambda:stock.stock_out(3,1,'3',None,1))
        assert sum(isinstance(result,ValueError) for result in results)==1 and balance(3)==Decimal('1')
        assert parallel(lambda:stock.stock_in(3,1,'2',None,1),lambda:stock.stock_out(3,1,'1',None,1))==[None,None]
        assert balance(3)==Decimal('2')
        rid,_=pr.create_purchase_request(1,None,'Synthetic mixed test');pr.add_purchase_request_item(rid,4,'5','2.50')
        assert pr.submit_purchase_request(rid);assert pr.approve_purchase_request(rid,1)
        oid,_=po.create_purchase_order_from_request(rid,1,1);assert po.send_purchase_order(oid)
        oi=po.get_purchase_order_items(oid)[0]['purchase_order_item_id'];token=str(uuid.uuid4())
        results=parallel(lambda:stock.stock_in(4,1,'2',None,1),lambda:gr.create_goods_receipt(oid,1,1,{oi:'5'},submission_id=token))
        assert not any(isinstance(result,ValueError) for result in results) and balance(4)==Decimal('7')
        gr.create_goods_receipt(oid,1,1,{oi:'5'},submission_id=token);assert balance(4)==Decimal('7')
        assert sql("SELECT quantity,reference_id FROM stock_movements WHERE item_id=4 AND reference_type='GOODS_RECEIPT'",fetch=True)==[(Decimal('5'),results[1][0])]
        # Across all items every persisted balance equals its signed movement sum.
        assert sql("SELECT s.item_id FROM inventory_stock s LEFT JOIN stock_movements m ON m.item_id=s.item_id AND m.warehouse_id=s.warehouse_id GROUP BY s.item_id,s.warehouse_id,s.quantity HAVING s.quantity <> COALESCE(SUM(CASE WHEN m.movement_type IN ('IN','ADJUSTMENT_IN') THEN m.quantity ELSE -m.quantity END),0)",fetch=True)==[]
        print('PASS first-row/update races, competing withdrawals, manual IN/OUT and Goods Receipt integration with exact movement reconciliation')
        for operation in (stock.stock_in,stock.stock_out):
            before=snapshot()
            sql("CREATE TRIGGER stock_failure BEFORE INSERT ON stock_movements FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic rollback'")
            try:
                fails(lambda:operation(3,1,'1',None,1),'could not be confirmed');assert snapshot()==before
            finally:sql('DROP TRIGGER stock_failure')
        # A failed first IN must remove the zero-balance reservation too.
        before=snapshot()
        sql("CREATE TRIGGER first_stock_failure BEFORE INSERT ON stock_movements FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='first row rollback'")
        try:
            fails(lambda:stock.stock_in(5,1,'1',None,1),'could not be confirmed')
            assert snapshot()==before and sql('SELECT * FROM inventory_stock WHERE item_id=5',fetch=True)==[]
        finally:sql('DROP TRIGGER first_stock_failure')
        # A master deactivation waits for the transaction's shared lock.
        for table,key in (('inventory_items','item_id'),('warehouses','warehouse_id')):
            entered,release=threading.Event(),threading.Event()
            def held_write():
                local.hold=(entered,release)
                try:stock.stock_in(1,1,'1',None,1)
                finally:del local.hold
            started=threading.Event()
            def deactivate():
                started.set();sql(f'UPDATE {table} SET is_active=FALSE WHERE {key}=1')
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(held_write);assert entered.wait(5)
                second=pool.submit(deactivate);assert started.wait(5)
                try:
                    try:second.result(timeout=0.3);raise AssertionError('Deactivation bypassed active master lock')
                    except TimeoutError:pass
                finally:release.set()
                first.result(timeout=10);second.result(timeout=10)
            before=snapshot();fails(lambda:stock.stock_in(1,1,'1',None,1),'inactive');assert snapshot()==before
            sql(f'UPDATE {table} SET is_active=TRUE WHERE {key}=1')
        # Simulated commit response loss: one transaction, one movement, no automatic replay.
        count=sql('SELECT COUNT(*) FROM stock_movements',fetch=True)[0][0];previous=balance(3)
        local.lost=True
        fails(lambda:stock.stock_in(3,1,'1',None,1),'Check movement history')
        assert balance(3)==previous+1 and sql('SELECT COUNT(*) FROM stock_movements',fetch=True)==[(count+1,)]
        print('PASS movement-failure rollback, master deactivation locking, and uncertain commit never automatically replayed')
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        pid=sql("INSERT INTO permissions(permission_code) VALUES ('inventory.stock.manage')")
        sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(pid,))
        client=csrf_client(erp.app)
        with client.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        assert client.post('/inventory/stock/in',data={'item_id':'1','warehouse_id':'1','quantity':'0.10'}).status_code==302
        assert client.post('/inventory/stock/out',data={'item_id':'1','warehouse_id':'1','quantity':'0.10'}).status_code==302
        before=snapshot()
        for path in ('/inventory/stock/in','/inventory/stock/out'):
            for value in ('NaN','Infinity','0','0.001','10000000000'):
                assert client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':value}).status_code==200
                assert snapshot()==before
        raw=erp.app.test_client()
        with raw.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        for path in ('/inventory/stock/in','/inventory/stock/out'):
            for form in ({},{'csrf_token':'invalid'}):assert raw.post(path,data=form).status_code==400
        assert snapshot()==before
        sql('DELETE FROM role_permissions WHERE role_id=1')
        for path in ('/inventory/stock/in','/inventory/stock/out'):
            assert client.post(path,data={'item_id':'1','warehouse_id':'1','quantity':'1'}).status_code==302
        assert snapshot()==before
        print('PASS real Decimal routes, rejected form messages, CSRF and fresh permission revocation; rejected requests leave business/audit records unchanged')
    print('SUCCESS: manual stock reliability passed with disposable MySQL only')


if __name__=='__main__':
    harness.run=run
    harness.main()
