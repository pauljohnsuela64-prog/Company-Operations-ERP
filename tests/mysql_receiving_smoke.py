"""Disposable MySQL receiving, migration and concurrency regression checks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
import importlib.util
from pathlib import Path
import re
import threading
import time
import uuid
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session
from test_csrf_security import expired_token, form_token


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur=connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_receiving_test')
        cur.execute('USE erp_receiving_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            # Build the pre-upgrade schema to test a real additive migration.
            if name == 'procurement':
                source=re.sub(r'    submission_id CHAR\(36\)[^\n]*\n', '', source)
                source=re.sub(r'    CONSTRAINT uq_goods_receipts_submission UNIQUE \(submission_id\),\n', '', source)
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):
                    cur.execute(statement)
        connection.commit()
    options['database']='erp_receiving_test'
    local=threading.local()

    class ConnectionProxy:
        def __init__(self, connection):
            self.connection=connection
        def __getattr__(self,name):
            return getattr(self.connection,name)
        def commit(self):
            hold=getattr(local,'hold_commit',None)
            if hold:
                entered,release=hold
                entered.set()
                assert release.wait(8), 'Timed out waiting to release commit'
            result = self.connection.commit()
            if getattr(local, 'lose_commit_response', False):
                local.lose_commit_response = False
                raise mysql.connector.InterfaceError('Simulated lost commit response', errno=2013)
            return result
        def __enter__(self):
            return self
        def __exit__(self,*args):
            self.connection.close()
    def connect():
        return ConnectionProxy(mysql.connector.connect(**options))
    def sql(query, params=(), fetch=False):
        with connect() as connection:
            cur=connection.cursor()
            cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            return result
    def fails(action, contains=None):
        try:
            action()
        except ValueError as error:
            if contains:
                assert contains in str(error), str(error)
            return str(error)
        raise AssertionError('Expected validation failure')
    def parallel(*actions):
        barrier=threading.Barrier(len(actions))
        def execute(action):
            barrier.wait(timeout=5)
            try:
                return action()
            except ValueError as error:
                return error
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures=[pool.submit(execute,action) for action in actions]
            return [future.result(timeout=15) for future in futures]
    def wait_for_database_lock():
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits',fetch=True)[0][0]:
                return
            time.sleep(0.01)
        raise AssertionError('Expected an actual overlapping InnoDB lock wait')

    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'test','unused')")
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES (1,'TEST','Test')")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name) VALUES (1,'TEST','Test'),(2,'OTHER','Other')")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES (1,'TEST','Test')")
    legacy_po=sql("INSERT INTO purchase_orders(po_number,supplier_id,created_by,status) VALUES ('LEGACY',1,1,'SENT')")
    legacy=sql("INSERT INTO goods_receipts(receipt_number,purchase_order_id,warehouse_id,received_by,notes) VALUES ('LEGACY',%s,1,1,'preserve')",(legacy_po,))
    spec=importlib.util.spec_from_file_location('receiving_migration',harness.ROOT/'database/migrations/001_goods_receipt_submission.py')
    migration=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with connect() as connection:
        migration.upgrade(connection)
        migration.upgrade(connection)
    assert sql('SELECT receipt_id,notes,submission_id FROM goods_receipts',fetch=True)==[(legacy,'preserve',None)]
    # Exercise interrupted upgrade: column present, index not yet installed.
    sql('ALTER TABLE goods_receipts DROP INDEX uq_goods_receipts_submission')
    with connect() as connection:
        migration.upgrade(connection)
        migration.upgrade(connection)
    assert sql("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='goods_receipts' AND column_name='submission_id' AND non_unique=0",fetch=True)==[(1,)]
    assert all(row[0]=='InnoDB' for row in sql("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE()",fetch=True))
    print('PASS repeatable migration, interrupted upgrade, historical receipt preservation, InnoDB engines')
    with ExitStack() as stack:
        pr=importlib.import_module('purchase_request_repository')
        po=importlib.import_module('purchase_order_repository')
        gr=importlib.import_module('goods_receipt_repository')
        for module in (pr,po,gr):
            stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        def order(quantity='10.00', item=1):
            rid,_=pr.create_purchase_request(1,None,'Isolated receiving test')
            pr.add_purchase_request_item(rid,item,quantity,'2.50')
            assert pr.submit_purchase_request(rid)
            assert pr.approve_purchase_request(rid,1)
            oid,_=po.create_purchase_order_from_request(rid,1,1)
            oi=po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
            assert po.send_purchase_order(oid)
            return rid,oid,oi
        def receipt(oid,oi,qty,token=None,warehouse=1,notes=None):
            return gr.create_goods_receipt(oid,warehouse,1,{oi:qty},notes=notes,submission_id=token or str(uuid.uuid4()))
        def snapshot():
            return [sql('SELECT * FROM '+table+' ORDER BY 1,2',fetch=True) for table in ('goods_receipts','goods_receipt_items','inventory_stock','stock_movements','purchase_orders','purchase_requests','audit_logs')]
        def receipt_count(oid):
            return sql('SELECT COUNT(*) FROM goods_receipts WHERE purchase_order_id=%s',(oid,),True)[0][0]
        def quantity(oid):
            return sql('SELECT COALESCE(SUM(gri.quantity_received),0) FROM goods_receipt_items gri JOIN goods_receipts gr USING(receipt_id) WHERE gr.purchase_order_id=%s',(oid,),True)[0][0]

        rid,oid,oi=order()
        token=str(uuid.uuid4())
        first=receipt(oid,oi,'2.00',token)
        before=snapshot()
        assert receipt(oid,oi,'2.00',token)==first
        assert snapshot()==before
        fails(lambda:receipt(oid,oi,'3.00',token),'different delivery')
        fails(lambda:receipt(oid,oi,'2.00',token,notes='changed'),'different delivery')
        second=receipt(oid,oi,'2.00')
        assert second[0]!=first[0] and receipt_count(oid)==2
        full_token=str(uuid.uuid4())
        full=receipt(oid,oi,'6.00',full_token)
        before=snapshot()
        assert receipt(oid,oi,'6.00',full_token)==full
        assert snapshot()==before
        assert pr.get_purchase_request_by_id(rid)['status']=='COMPLETED'
        assert po.get_purchase_order_by_id(oid)['status']=='RECEIVED'
        assert quantity(oid)==Decimal('10.00')
        assert sql('SELECT quantity FROM inventory_stock WHERE item_id=1 AND warehouse_id=1',fetch=True)==[(Decimal('10.00'),)]
        assert sql('SELECT SUM(quantity),COUNT(*) FROM stock_movements WHERE reference_id IN (%s,%s,%s)',(first[0],second[0],full[0]),True)==[(Decimal('10.00'),3)]
        print('PASS partial/full receiving, sequential replay, conflicting replay, separate identical deliveries, exact stock/movements')

        rid,oid,oi=order()
        token=str(uuid.uuid4())
        results=parallel(*[lambda:receipt(oid,oi,'10',token) for _ in range(4)])
        assert all(result==results[0] for result in results) and not isinstance(results[0],Exception), results
        assert receipt_count(oid)==1 and quantity(oid)==Decimal('10')
        assert sql('SELECT COUNT(*) FROM stock_movements WHERE reference_id=%s',(results[0][0],),True)==[(1,)]
        print('PASS concurrent full-receipt duplicate requests commit exactly once')

        rid,oid,oi=order()
        results=parallel(lambda:receipt(oid,oi,'6'),lambda:receipt(oid,oi,'6'))
        assert sum(isinstance(result,ValueError) for result in results)==1, results
        assert receipt_count(oid)==1 and quantity(oid)==Decimal('6')
        results=parallel(lambda:receipt(oid,oi,'2'),lambda:receipt(oid,oi,'2'))
        assert not any(isinstance(result,Exception) for result in results),results
        assert receipt_count(oid)==3 and quantity(oid)==Decimal('10')
        print('PASS concurrent over-receipt rejection and legitimate concurrent partial deliveries')

        rid,a,ai=order(item=2)
        rid,b,bi=order(item=2)
        assert sql('SELECT * FROM inventory_stock WHERE item_id=2',fetch=True)==[]
        entered,release=threading.Event(),threading.Event()
        def create_missing():
            local.hold_commit=(entered,release)
            try:
                return receipt(a,ai,'2')
            finally:
                local.hold_commit=None
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future=pool.submit(create_missing)
            try:
                assert entered.wait(5)
                second_future=pool.submit(lambda:receipt(b,bi,'3'))
                wait_for_database_lock()
            finally:
                release.set()
            results=[first_future.result(timeout=10),second_future.result(timeout=10)]
        assert not any(isinstance(result,Exception) for result in results),results
        assert sql('SELECT quantity FROM inventory_stock WHERE item_id=2 AND warehouse_id=1',fetch=True)==[(Decimal('5'),)]
        # Same UUID across distinct orders must never bypass the global constraint.
        token=str(uuid.uuid4())
        results=parallel(lambda:receipt(a,ai,'1',token),lambda:receipt(b,bi,'1',token))
        assert sum(isinstance(result,ValueError) for result in results)==1,results
        assert sql('SELECT COUNT(*) FROM goods_receipts WHERE submission_id=%s',(token,),True)==[(1,)]
        print('PASS initially missing stock row concurrency and global token collision protection')

        rid,oid,oi=order()
        before=snapshot()
        for invalid in ('NaN','sNaN','Infinity','-Infinity','-1','0.001','10000000000','junk','11','0'):
            fails(lambda:receipt(oid,oi,invalid))
        fails(lambda:gr.create_goods_receipt(oid,1,1,{oi:'1'}),'submission identifier')
        fails(lambda:gr.create_goods_receipt(oid,1,1,{oi:'1'},submission_id='bad'),'submission identifier')
        fails(lambda:gr.create_goods_receipt(oid,1,1,{oi:'1',str(oi):'1'},submission_id=str(uuid.uuid4())),'Duplicate')
        fails(lambda:receipt(oid,oi,'1',warehouse=999),'warehouse')
        fails(lambda:receipt(oid,oi,'1',notes='x'*255),'references')
        assert snapshot()==before
        sql("UPDATE purchase_orders SET status='DRAFT' WHERE purchase_order_id=%s",(oid,))
        before=snapshot()
        fails(lambda:receipt(oid,oi,'1'),'not available')
        assert snapshot()==before
        sql("UPDATE purchase_orders SET status='SENT' WHERE purchase_order_id=%s",(oid,))
        print('PASS invalid identifiers, quantities, warehouses, notes and statuses leave business data intact')

        # Fail each of the six transactional write stages, including PR completion.
        for table in ('goods_receipts','goods_receipt_items','inventory_stock','stock_movements','purchase_orders','purchase_requests'):
            before=snapshot()
            event='UPDATE' if table in ('purchase_orders','purchase_requests','inventory_stock') else 'INSERT'
            sql(f"CREATE TRIGGER receiving_failure BEFORE {event} ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated failure'")
            token=str(uuid.uuid4())
            try:
                fails(lambda:receipt(oid,oi,'10',token),'could not be')
                assert snapshot()==before, table
                assert sql('SELECT COUNT(*) FROM goods_receipts WHERE submission_id=%s',(token,),True)==[(0,)]
            finally:
                sql('DROP TRIGGER receiving_failure')
        # A failed attempt doesn't burn its token; a subsequent retry can commit.
        receipt(oid,oi,'10',token)
        print('PASS rollback at all six write stages, token rollback and successful retry')

        rid,oid,oi=order()
        token=str(uuid.uuid4())
        local.lose_commit_response=True
        fails(lambda:receipt(oid,oi,'10',token),'could not be confirmed')
        assert receipt_count(oid)==1
        before=snapshot()
        result=receipt(oid,oi,'10',token)
        assert snapshot()==before and quantity(oid)==Decimal('10')
        print('PASS lost commit response resolves by replay without any duplicate writes')

        rid,oid,oi=order()
        before=snapshot()
        fails(lambda:gr.create_goods_receipt(oid,1,999,{oi:'1'},submission_id=str(uuid.uuid4())),'could not be confirmed')
        assert snapshot()==before
        stock_before=sql('SELECT quantity FROM inventory_stock WHERE item_id=1 AND warehouse_id=1',fetch=True)[0][0]
        sql('UPDATE inventory_stock SET quantity=9999999999.99 WHERE item_id=1 AND warehouse_id=1')
        before=snapshot()
        for sql_mode in (None, ''):
            if sql_mode is not None:
                options['sql_mode'] = sql_mode
            try:
                fails(lambda:receipt(oid,oi,'1'),'Warehouse stock quantity')
                assert snapshot()==before
            finally:
                options.pop('sql_mode',None)
        sql('UPDATE inventory_stock SET quantity=%s WHERE item_id=1 AND warehouse_id=1',(stock_before,))
        print('PASS foreign key and stock overflow constraint failures roll back all receiving writes')


        # Hold each actual winner before commit and race its opposite operation.
        for winner in ('receive','cancel'):
            rid,oid,oi=order()
            entered,release=threading.Event(),threading.Event()
            def first():
                local.hold_commit=(entered,release)
                try:
                    return receipt(oid,oi,'1') if winner=='receive' else po.cancel_purchase_order(oid)
                finally:
                    local.hold_commit=None
            def second():
                return fails(lambda:po.cancel_purchase_order(oid)) if winner=='receive' else fails(lambda:receipt(oid,oi,'1'),'not available')
            with ThreadPoolExecutor(max_workers=2) as pool:
                first_future=pool.submit(first)
                assert entered.wait(5)
                second_future=pool.submit(second)
                try:
                    wait_for_database_lock()
                    assert not second_future.done()
                finally:
                    release.set()
                first_future.result(timeout=10)
                second_future.result(timeout=10)
            if winner=='receive':
                assert quantity(oid)==Decimal('1') and po.get_purchase_order_by_id(oid)['status']=='PARTIALLY_RECEIVED'
            else:
                assert receipt_count(oid)==0 and po.get_purchase_order_by_id(oid)['status']=='CANCELLED'
        print('PASS concurrent receiving/cancellation in both lock acquisition orders')

        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-test',ERP_ENV='testing',ERP_DEBUG='false'))
        erp=importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True,SECRET_KEY='isolated-test'))
        client=csrf_client(erp.app)
        for code in ['procurement.view', 'procurement.requests.create', 'procurement.requests.approve', 'procurement.orders.create', 'procurement.orders.manage', 'procurement.receipts.manage']:
            pid=sql("INSERT INTO permissions(permission_code) VALUES (%s)",(code,))
            sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(pid,))
        with client.session_transaction() as session:
            stamp_session(erp.app,session,erp.get_authorization_state(1))
        rid,oid,oi=order()
        path=f'/procurement/receipts/{oid}/receive'
        html=client.get(path).get_data(as_text=True)
        token=re.search(r'name="submission_id" value="([^"]+)"',html).group(1)
        uuid.UUID(token)
        form={'submission_id':token,'warehouse_id':'1',f'quantity_received_{oi}':'5','notes':'route'}
        # Raw HTTP clients prove rejection before any receiving write, then
        # explicitly recover the original UUID using the actual merged route.
        raw=erp.app.test_client()
        cookie=client.get_cookie(erp.app.config['SESSION_COOKIE_NAME'])
        raw.set_cookie(erp.app.config['SESSION_COOKIE_NAME'],cookie.value)
        before=snapshot()
        for extra in ({}, {'csrf_token':'invalid'}):
            assert raw.post(path,data=dict(form,**extra)).status_code==400
            assert snapshot()==before
        expired=dict(form,csrf_token=expired_token(erp.app,raw))
        recovery=raw.post(path,data=expired)
        assert recovery.status_code==400 and snapshot()==before
        assert f'name="submission_id" value="{token}"' in recovery.get_data(as_text=True)
        first=raw.post(path,data=dict(form,csrf_token=form_token(recovery)))
        assert receipt_count(oid)==1 and quantity(oid)==Decimal('5')
        refreshed=raw.get('/auth/csrf-token').json['csrf_token']
        retry=raw.post(path,data=dict(form,csrf_token=refreshed))
        assert retry.status_code==302 and retry.location==first.location
        assert receipt_count(oid)==1 and quantity(oid)==Decimal('5')
        print('PASS real receiving CSRF rejection, expiry recovery and token renewal retain UUID without duplicate stock')
        second=client.post(path,data=form)
        assert first.status_code==302 and first.location==second.location and '/view' not in first.location
        assert receipt_count(oid)==1 and quantity(oid)==Decimal('5')
        audit_rows=sql("SELECT user_id,username,module,action,entity_type,entity_id,description FROM audit_logs",fetch=True)
        assert len(audit_rows)==1 and audit_rows[0][:5]==(1,'test','PROCUREMENT','RECEIVE','GOODS_RECEIPT')
        assert 'GR-' in audit_rows[0][6] and po.get_purchase_order_by_id(oid)['po_number'] in audit_rows[0][6]
        assert sql('SELECT receipt_id FROM goods_receipts WHERE purchase_order_id=%s',(oid,),True)==[(int(audit_rows[0][5]),)]
        # Fresh form, same quantities: a legitimate delivery that completes the PO.
        token2=re.search(r'name="submission_id" value="([^"]+)"',client.get(path).get_data(as_text=True)).group(1)
        assert token2!=token
        form['submission_id']=token2
        third=client.post(path,data=form)
        fourth=client.post(path,data=form)
        assert third.status_code==302 and third.location==fourth.location
        assert receipt_count(oid)==2 and quantity(oid)==Decimal('10')
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE action='RECEIVE'",fetch=True)==[(2,)]
        # Independent clients concurrently replay one UUID through the actual route.
        _,concurrent_oid,concurrent_oi=order()
        concurrent_path=f'/procurement/receipts/{concurrent_oid}/receive'
        concurrent_form={'submission_id':str(uuid.uuid4()),'warehouse_id':'1',f'quantity_received_{concurrent_oi}':'10'}
        clients=[csrf_client(erp.app) for _ in range(2)]
        for other in clients:
            with other.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        before_events=sql('SELECT COUNT(*) FROM audit_logs',fetch=True)[0][0]
        results=parallel(*(lambda c=c:c.post(concurrent_path,data=concurrent_form) for c in clients))
        assert all(response.status_code==302 for response in results)
        assert receipt_count(concurrent_oid)==1 and quantity(concurrent_oid)==Decimal('10')
        assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(before_events+1,)]
        # SQL audit failure leaves receiving committed; replay must not add an event.
        _,failure_oid,failure_oi=order()
        failure_path=f'/procurement/receipts/{failure_oid}/receive'
        failure_form={'submission_id':str(uuid.uuid4()),'warehouse_id':'1',f'quantity_received_{failure_oi}':'1'}
        sql("CREATE TRIGGER receiving_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test audit failure'")
        before_events=sql('SELECT COUNT(*) FROM audit_logs',fetch=True)[0][0]
        try:
            with patch.object(erp.app.logger,'exception'):
                assert client.post(failure_path,data=failure_form).status_code==302
            assert quantity(failure_oid)==Decimal('1') and receipt_count(failure_oid)==1
            assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(before_events,)]
        finally:sql('DROP TRIGGER receiving_audit_failure')
        assert client.post(failure_path,data=failure_form).status_code==302
        assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(before_events,)]
        # Failed stock movement rolls back the receipt and never emits RECEIVE.
        _,rollback_oid,rollback_oi=order()
        rollback_form={'submission_id':str(uuid.uuid4()),'warehouse_id':'1',f'quantity_received_{rollback_oi}':'1'}
        before_rollback=snapshot()
        sql("CREATE TRIGGER receiving_write_failure BEFORE INSERT ON stock_movements FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test rollback'")
        try:
            assert client.post(f'/procurement/receipts/{rollback_oid}/receive',data=rollback_form).status_code==200
            assert snapshot()==before_rollback
        finally:sql('DROP TRIGGER receiving_write_failure')
        print('PASS real RECEIVE audit identity, sequential/concurrent UUID deduplication, distinct deliveries, rollback and audit failure isolation')
        before=snapshot()
        changed=dict(form,notes='changed')
        assert client.post(path,data=changed).status_code==200
        assert snapshot()==before
        sql('DELETE FROM role_permissions WHERE role_id=1')
        assert client.post(path,data=form).status_code==302
        assert snapshot()==before
        print('PASS actual form tokens, POST retry after partial/full delivery, receipt redirects, conflict and permission handling')
    print('SUCCESS: receiving checks passed on disposable MySQL; no company database accessed')


if __name__=='__main__':
    harness.run=run
    harness.main()
