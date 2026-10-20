"""Warehouse regression on verified disposable MySQL; no company data."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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
        cursor=connection.cursor();cursor.execute('SELECT @@datadir')
        assert Path(cursor.fetchone()[0]).resolve()==data_dir.resolve()
        cursor.execute('CREATE DATABASE erp_warehouse_synthetic');cursor.execute('USE erp_warehouse_synthetic')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_warehouse_synthetic'
    local=threading.local()
    class Proxy:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            mode=getattr(local,'commit_mode',None)
            if mode=='before':raise mysql.connector.Error('Synthetic commit failure',errno=2013)
            if mode=='after':
                self.connection.commit()
                raise mysql.connector.Error('Synthetic uncertain acknowledgment',errno=2013)
            if getattr(local,'hold',None):
                entered,release=local.hold;entered.set();assert release.wait(10)
            return self.connection.commit()
        def __enter__(self):return self
        def __exit__(self,*args):self.connection.close()
    def connect():return Proxy(mysql.connector.connect(**options))
    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as connection:
            cur=connection.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit();return result
    def snapshot():
        return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('inventory_categories','warehouses','inventory_items','inventory_stock','stock_movements','audit_logs','goods_receipts','goods_receipt_items','purchase_orders','purchase_order_items')]
    def rejected(action,exception=ValueError):
        before=snapshot()
        try:action()
        except exception:pass
        else:raise AssertionError('Invalid operation succeeded')
        assert snapshot()==before
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Inventory test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'inventory.test','synthetic')")
    sql("INSERT INTO inventory_categories(category_id,category_code,category_name,is_active) VALUES (1,'ACTIVE','Active',TRUE),(2,'OFF','Inactive',FALSE),(3,'RACE','Concurrent',TRUE)")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES (1,'W','Warehouse')")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name,category_id,unit_of_measure) VALUES (1,'ITEM','Item',1,'pcs'),(2,'OLD','Historical assignment',2,'pcs')")
    sql('INSERT INTO inventory_stock(item_id,warehouse_id,quantity) VALUES (1,1,1)')
    sql("INSERT INTO stock_movements(item_id,warehouse_id,movement_type,quantity,reference_type,created_by) VALUES (1,1,'IN',1,'SYNTHETIC_HISTORY',1)")
    historical=sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True)
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='inventory-master-mysql-only',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        modules=[importlib.import_module(name) for name in ('inventory_category_repository','warehouse_repository','inventory_item_repository')]
        for module in modules:stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        categories,warehouses,items=modules

        # Inspect real unique keys/schema limits, including non-strict MySQL.
        assert sql("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='warehouses' AND NON_UNIQUE=0",fetch=True)==[(3,)]
        erp=importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        stack.enter_context(patch('database.ensure_ready'))
        for code in ('inventory.view','inventory.warehouses.manage','inventory.stock.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,))
            sql('INSERT INTO role_permissions VALUES(1,%s)',(pid,))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
            return c
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='WAREHOUSE' ORDER BY audit_log_id",fetch=True)
        form=dict(warehouse_code='NEW',warehouse_name='New warehouse',location='PRIVATE location')
        c=client()
        assert c.post('/inventory/warehouses/add',data=form).status_code==302
        wid=sql("SELECT warehouse_id FROM warehouses WHERE warehouse_code='NEW'",fetch=True)[0][0]
        assert events()==[('CREATE',str(wid),f'Warehouse NEW (ID {wid}) created.')]
        before=snapshot()
        assert c.post(f'/inventory/warehouses/{wid}/edit',data=form).status_code==302
        assert snapshot()==before
        # Required/exact/overlong/Unicode/control validation before any truncation.
        warehouses.create_warehouse('c'*30,'n'*100,'l'*255)
        for bad in (dict(form,warehouse_code='x'*31),dict(form,warehouse_name='x'*101),dict(form,location='x'*256),dict(form,warehouse_name=''),dict(form,location='bad\x00')):
            before=snapshot()
            response=c.post('/inventory/warehouses/add',data=bad)
            assert response.status_code==400 and snapshot()==before
        for field in ('warehouse_code','warehouse_name'):
            before=snapshot()
            assert c.post('/inventory/warehouses/add',data=dict(form,**{field:form[field]})).status_code==200
            assert snapshot()==before
        form.update(warehouse_name='Updated warehouse')
        assert c.post(f'/inventory/warehouses/{wid}/edit',data=form).status_code==302
        assert events()[-1][0]=='UPDATE' and all('PRIVATE' not in row[2] for row in events())
        for active,action in ((False,'DEACTIVATE'),(True,'ACTIVATE')):
            count=len(events())
            for _ in range(2):assert c.post(f'/inventory/warehouses/{wid}/status',data={'is_active':str(int(active))}).status_code==302
            assert len(events())==count+1 and events()[-1][0]==action
        # A real missing record differs from a no-op and never emits success.
        for action in (lambda:warehouses.update_warehouse(99999,'MISSING','Missing'),lambda:warehouses.set_warehouse_active_status(99999,False)):rejected(action)
        assert c.get('/inventory/warehouses/99999/edit').status_code==302
        # Actual statement/commit failures, including lost acknowledgment after commit.
        before=snapshot()
        sql("CREATE TRIGGER warehouse_failure BEFORE UPDATE ON warehouses FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        try:assert c.post(f'/inventory/warehouses/{wid}/edit',data=dict(form,warehouse_name='SQL rollback')).status_code==503
        finally:sql('DROP TRIGGER warehouse_failure')
        assert snapshot()==before
        local.commit_mode='before'
        try:assert c.post(f'/inventory/warehouses/{wid}/edit',data=dict(form,warehouse_name='Commit rollback')).status_code==503
        finally:local.commit_mode=None
        assert snapshot()==before
        count=len(events());local.commit_mode='after'
        try:assert c.post(f'/inventory/warehouses/{wid}/edit',data=dict(form,warehouse_name='Committed uncertain')).status_code==503
        finally:local.commit_mode=None
        assert sql('SELECT warehouse_name FROM warehouses WHERE warehouse_id=%s',(wid,),True)==[('Committed uncertain',)] and len(events())==count
        # Best-effort audit failure cannot undo a confirmed Warehouse write.
        sql("CREATE TRIGGER warehouse_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(f'/inventory/warehouses/{wid}/edit',data=dict(form,warehouse_name='Audit unavailable')).status_code==302
        finally:sql('DROP TRIGGER warehouse_audit_failure')
        assert sql('SELECT warehouse_name FROM warehouses WHERE warehouse_id=%s',(wid,),True)==[('Audit unavailable',)] and len(events())==count
        print('PASS validation/uniqueness, retained forms, post-commit CREATE/UPDATE/status audits, no-op/missing records, real rollback and uncertain commit/audit failure isolation')
        for action in (lambda:c.post('/inventory/warehouses/add',data=dict(form,warehouse_code='COMMIT-FAIL',warehouse_name='Commit failure create')),
                       lambda:c.post(f'/inventory/warehouses/{wid}/status',data={'is_active':'0'})):
            before=snapshot();local.commit_mode='before'
            try:assert action().status_code==503
            finally:local.commit_mode=None
            assert snapshot()==before
        # Large historical list, inactive and literal wildcard searches, complete traversal.
        with connect() as db:
            cur=db.cursor()
            cur.executemany("INSERT INTO warehouses(warehouse_code,warehouse_name,location,is_active) VALUES(%s,%s,'Historical location',0)",[(f'HIST-{i:04d}',f'Historical {i:04d}') for i in range(1005)])
            cur.execute("INSERT INTO warehouses(warehouse_code,warehouse_name,location) VALUES('LITERAL','Literal %_!','Literal location')")
            db.commit()
        before=snapshot();ids=[]
        for size in (25,50,100):
            page=warehouses.get_warehouse_page(dict(search='Historical',status='inactive',page_size=str(size)))
            assert page['total']==1005 and len(page['records'])==size
        for page in range(1,12):
            data=warehouses.get_warehouse_page(dict(search='Historical',status='inactive',page_size='100',page=str(page)))
            ids.extend(row['warehouse_id'] for row in data['records'])
        assert len(ids)==len(set(ids))==1005 and ids==sorted(ids)
        last=warehouses.get_warehouse_page(dict(search='Historical',status='inactive',page_size='100',page='999'))
        assert (last['first'],last['last'],last['filters']['page'])==(1001,1005,11)
        for needle,total in (('%_!',1),('Historical%',0),("' OR 1=1 --",0)):
            assert warehouses.get_warehouse_page(dict(search=needle))['total']==total
        assert snapshot()==before
        for query in ('status=wrong','page_size=500','page=0','status=active&status=inactive','query=typo'):
            assert c.get('/inventory/warehouses?'+query).status_code==400
        html=c.get('/inventory/warehouses?search=Historical&status=inactive&page_size=100&page=11').get_data(as_text=True)
        assert 'Showing 1001-1005 of 1005 warehouses' in html and 'HIST-1004' in html
        assert snapshot()==before
        # Count and rows see the same snapshot during a committed concurrent insert.
        inserted=False
        class SnapshotCursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,name):return getattr(self.cur,name)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True;sql("INSERT INTO warehouses(warehouse_code,warehouse_name,is_active) VALUES('SNAPSHOT','Historical concurrent',0)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return SnapshotCursor(self.connection.cursor(**kw))
        with patch.object(warehouses,'get_connection',side_effect=lambda:SnapshotConnection(mysql.connector.connect(**options))):
            page=warehouses.get_warehouse_page(dict(search='Historical',page_size='100',page='11'))
            assert page['total']==1005 and len(page['records'])==5
        assert warehouses.get_warehouse_page(dict(search='Historical'))['total']==1006
        print('PASS complete 1005-row historical pagination, counts/snapshot under concurrent insert, 25/50/100 pages, literal filters and no writes from listing')
        # Observe actual InnoDB lock waits, not timing-only guesses.
        def wait_for_lock():
            import time
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits',fetch=True)[0][0]:return
                time.sleep(.03)
            raise AssertionError('Expected InnoDB lock wait was not observed')
        stock=importlib.import_module('stock_repository');stack.enter_context(patch.object(stock,'get_connection',side_effect=connect))
        def held(action,entered,release):
            local.hold=(entered,release)
            try:return action()
            finally:local.hold=None
        # Warehouse 1 holds stock: deactivation is still permitted; history unchanged.
        old_history=historical
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:warehouses.set_warehouse_active_status(1,False),entered,release)
            assert entered.wait(8)
            second=pool.submit(stock.stock_in,1,1,'1',None,1,submission_id=str(uuid.uuid4()))
            try:wait_for_lock()
            finally:release.set()
            assert first.result(10) is True
            try:second.result(10)
            except ValueError as error:assert 'inactive' in str(error)
            else:raise AssertionError('Post-deactivation stock write succeeded')
        assert (sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True))==old_history
        assert warehouses.set_warehouse_active_status(1,True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:stock.stock_in(1,1,'1',None,1,submission_id=str(uuid.uuid4())),entered,release)
            assert entered.wait(8)
            second=pool.submit(warehouses.set_warehouse_active_status,1,False)
            try:wait_for_lock()
            finally:release.set()
            first.result(10);assert second.result(10) is True
        assert sql('SELECT quantity FROM inventory_stock WHERE item_id=1 AND warehouse_id=1',fetch=True)==[(Decimal('2.00'),)]
        assert warehouses.set_warehouse_active_status(1,True)
        # Two competing status targets yield one real change; no-op emits no audit.
        count=len(events())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:client().post('/inventory/warehouses/1/status',data={'is_active':'0'}).status_code,range(2)))
        assert results==[302,302] and len(events())==count+1
        # Duplicate create races serialize through existing unique keys.
        race=dict(warehouse_code='RACE-WAREHOUSE',warehouse_name='Race warehouse',location='PRIVATE')
        count=len(events())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:client().post('/inventory/warehouses/add',data=race).status_code,range(2)))
        assert sorted(results)==[200,302] and len(events())==count+1
        print('PASS observed Warehouse/stock lock waits in both orders, stock-holding deactivation, unchanged historical records, concurrent status no-op and duplicate creation with one audit')
        # Identical concurrent edits serialize and produce one committed UPDATE.
        count=len(events());update=dict(form,warehouse_name='Concurrent identical update')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:client().post(f'/inventory/warehouses/{wid}/edit',data=update).status_code,range(2)))
        assert results==[302,302] and len(events())==count+1 and events()[-1][0]=='UPDATE'
        # Goods Receiving also holds a shared eligibility lock through commit.
        warehouses.set_warehouse_active_status(1,True)
        pr=importlib.import_module('purchase_request_repository');po=importlib.import_module('purchase_order_repository');gr=importlib.import_module('goods_receipt_repository')
        for module in (pr,po,gr):stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES(1,'SYNTHETIC','Synthetic supplier')")
        def order():
            rid,_=pr.create_purchase_request(1,None,'Synthetic request')
            pr.add_purchase_request_item(rid,1,'2','1');pr.submit_purchase_request(rid);pr.approve_purchase_request(rid,1)
            oid,_=po.create_purchase_order_from_request(rid,1,1);po.send_purchase_order(oid)
            return oid,sql('SELECT purchase_order_item_id FROM purchase_order_items WHERE purchase_order_id=%s',(oid,),True)[0][0]
        oid,oi=order()
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:gr.create_goods_receipt(oid,1,1,{oi:'1'},submission_id=str(uuid.uuid4())),entered,release)
            assert entered.wait(8)
            second=pool.submit(warehouses.set_warehouse_active_status,1,False)
            try:wait_for_lock()
            finally:release.set()
            first.result(10);assert second.result(10) is True
        before=snapshot()
        try:gr.create_goods_receipt(oid,1,1,{oi:'1'},submission_id=str(uuid.uuid4()))
        except ValueError as error:assert 'inactive' in str(error)
        else:raise AssertionError('Receipt accepted inactive warehouse')
        assert snapshot()==before
        print('PASS Goods Receiving eligibility lock holds through commit, deactivation waits, later inactive receipt rejected with unchanged stock/history')
        # Deactivation first: an already-admitted receipt waits on the row, then
        # observes inactivity and leaves receipt/order/stock history unchanged.
        assert warehouses.set_warehouse_active_status(1,True)
        before=snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:warehouses.set_warehouse_active_status(1,False),entered,release)
            assert entered.wait(8)
            second=pool.submit(gr.create_goods_receipt,oid,1,1,{oi:'1'},submission_id=str(uuid.uuid4()))
            try:wait_for_lock()
            finally:release.set()
            assert first.result(10) is True
            try:second.result(10)
            except ValueError as error:assert 'inactive' in str(error)
            else:raise AssertionError('Waiting receipt ignored deactivation')
        after=snapshot()
        assert after[0]==before[0] and after[2:]==before[2:]
        assert sql('SELECT is_active FROM warehouses WHERE warehouse_id=1',fetch=True)==[(0,)]
        print('PASS observed reverse Goods Receiving/deactivation lock wait: no receipt/order/stock side effects after inactivity')
        # Real fresh authorization and CSRF remain authoritative.
        before=snapshot()
        raw=erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert raw.post('/inventory/warehouses/1/status',data={'is_active':'1'}).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='inventory.warehouses.manage'")
        assert c.post('/inventory/warehouses/1/status',data={'is_active':'1'}).location.endswith('/dashboard')
        assert snapshot()==before
        print('SUCCESS: Warehouse regression used only disposable synthetic MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
