"""Inventory Items management regression on a verified disposable MySQL server only."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cursor=connection.cursor();cursor.execute('SELECT @@datadir')
        assert Path(cursor.fetchone()[0]).resolve()==data_dir.resolve()
        cursor.execute('CREATE DATABASE erp_inventory_items_test');cursor.execute('USE erp_inventory_items_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_inventory_items_test'
    local=threading.local()
    class Proxy:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            if getattr(local,'hold',None):
                entered,release=local.hold;entered.set();assert release.wait(10)
            mode=getattr(local,'failure',None)
            if mode=='before':raise mysql.connector.Error('Synthetic unconfirmed commit',errno=2013)
            result=self.connection.commit()
            if mode=='after':raise mysql.connector.Error('Synthetic lost acknowledgment',errno=2013)
            return result
        def __enter__(self):return self
        def __exit__(self,*args):self.connection.close()
    def connect():return Proxy(mysql.connector.connect(**options))
    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as connection:
            cur=connection.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit();return result
    def snapshot():
        return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('inventory_categories','warehouses','inventory_items','inventory_stock','stock_movements','audit_logs')]
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
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        stack.enter_context(patch('database.ensure_ready'))
        for code in ('inventory.view','inventory.items.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,))
            sql('INSERT INTO role_permissions(role_id,permission_id) VALUES(1,%s)',(pid,))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
            return c
        c=client();form=dict(item_code='CREATED',item_name='PRIVATE item',category_id='1',description='PRIVATE notes',unit_of_measure='pcs',reorder_level='0.10')
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='INVENTORY_ITEM' ORDER BY audit_log_id",fetch=True)
        assert c.post('/inventory/items/add',data=form).status_code==302
        bid=sql("SELECT item_id FROM inventory_items WHERE item_code='CREATED'",fetch=True)[0][0]
        path=f'/inventory/items/{bid}/edit';status=f'/inventory/items/{bid}/status'
        before=snapshot();assert c.post(path,data=form).status_code==302;assert snapshot()==before
        assert c.post(path,data=dict(form,item_name='PRIVATE revised',unit_of_measure='box')).status_code==302
        assert c.post(status,data={'is_active':'0'}).status_code==302
        before=snapshot();assert c.post(status,data={'is_active':'0'}).status_code==302;assert snapshot()==before
        assert c.post(status,data={'is_active':'1'}).status_code==302
        assert [e[0] for e in events()]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE']
        assert all('PRIVATE' not in e[2] for e in events())
        before=snapshot();assert c.post('/inventory/items/add',data=form).status_code==200;assert snapshot()==before
        for changes in ({'category_id':'99999'},{'category_id':'2'},{'reorder_level':'NaN'},{'item_code':'x'*51},{'description':'x'*256}):
            before=snapshot();assert c.post(path,data=dict(form,**changes)).status_code==200;assert snapshot()==before
        assert items.update_inventory_item(1,'ITEM','Renamed item',1,'New label','box','3.25') is True
        assert (sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True))==historical
        assert items.update_inventory_item(2,'OLD','Historical assignment',2,None,'pcs','0') is False
        print('PASS exact Decimal fields, allowed unit/code/name/category edits, inactive category retention, stock/history preservation and four post-commit audit actions; failed/no-op writes emit none')
        with mysql.connector.connect(**options) as db:
            cur=db.cursor();cur.executemany("INSERT INTO inventory_items(item_code,item_name,category_id,is_active,unit_of_measure) VALUES(%s,'Historical tied name',2,0,'pcs')",[(f'ITEM-HISTORY-{i:04d}',) for i in range(1005)])
            db.commit()
        before=snapshot()
        for size in (25,50,100):
            seen=[]
            for number in range(1,(1005+size-1)//size+1):
                page=items.get_inventory_item_page(dict(search='ITEM-HISTORY',category_id='2',status='inactive',page_size=str(size),page=str(number)))
                assert page['total']==1005 and len(page['records'])<=size
                seen.extend(row['item_id'] for row in page['records'])
            assert len(seen)==len(set(seen))==1005 and seen==sorted(seen)
        assert items.get_inventory_item_page(dict(search='ITEM-HISTORY',page='999',page_size='100'))['first']==1001
        assert items.get_inventory_item_page(dict(search='ITEM%_!'))['total']==0
        assert items.get_inventory_item_page(dict(category_id='none'))['total']==0
        assert items.get_inventory_item_page(dict(category_id='99999'))['total']==0
        for query in ('page=0','page_size=500','status=bad','category_id=bad','search=x&search=y','unknown=x'):
            response=c.get('/inventory/items?'+query);assert response.status_code==400 and 'matching items' not in response.get_data(as_text=True)
        assert snapshot()==before
        inserted=False
        class SnapshotCursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,key):return getattr(self.cur,key)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True;sql("INSERT INTO inventory_items(item_code,item_name,category_id,is_active) VALUES('ITEM-HISTORY-NEW','Historical tied name',2,0)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return SnapshotCursor(self.connection.cursor(**kw))
        with patch.object(items,'get_connection',side_effect=lambda:SnapshotConnection(mysql.connector.connect(**options))):
            page=items.get_inventory_item_page(dict(search='ITEM-HISTORY',page_size='100',page='11'))
            assert page['total']==1005 and len(page['records'])==5
        assert items.get_inventory_item_page(dict(search='ITEM-HISTORY'))['total']==1006
        print('PASS 1005 tied-name records reachable in 25/50/100 pages, category/status/search filters, count/page snapshot under concurrent insert, invalid filters fail closed')
        before=snapshot();sql("CREATE TRIGGER item_failure BEFORE UPDATE ON inventory_items FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic update failure'")
        try:assert c.post(path,data=dict(form,item_name='SQL fail')).status_code==503
        finally:sql('DROP TRIGGER item_failure')
        assert snapshot()==before
        for mode in ('before','after'):
            count=len(events());local.failure=mode
            try:assert c.post(path,data=dict(form,item_name='Unconfirmed '+mode)).status_code==503
            finally:local.failure=None
            assert len(events())==count
            if mode=='before':assert snapshot()==before
            else:assert sql('SELECT item_name FROM inventory_items WHERE item_id=%s',(bid,),True)==[('Unconfirmed after',)]
        sql("CREATE TRIGGER item_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(path,data=dict(form,item_name='Audit unavailable')).status_code==302
        finally:sql('DROP TRIGGER item_audit_failure')
        assert len(events())==count
        assert sql('SELECT item_name FROM inventory_items WHERE item_id=%s',(bid,),True)==[('Audit unavailable',)]
        print('PASS SQL/commit rollback, uncertain committed write reconciliation and audit failure isolation')
        def wait_for_lock():
            import time
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits',fetch=True)[0][0]:return
                time.sleep(.03)
            raise AssertionError('Expected InnoDB lock wait not observed')
        def hold(action,entered,release):
            local.hold=(entered,release)
            try:return action()
            finally:local.hold=None
        # Observe unique-key duplicate race and identical edit/status serialization.
        for action in (lambda:client().post('/inventory/items/add',data=dict(form,item_code='RACE')),
                       lambda:client().post(path,data=dict(form,item_name='Concurrent same')),
                       lambda:client().post(status,data={'is_active':'0'})):
            count=len(events());entered=threading.Event();release=threading.Event()
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(hold,action,entered,release)
                try:
                    assert entered.wait(8);second=pool.submit(action);wait_for_lock();assert len(events())==count
                finally:release.set()
                codes=[first.result(12).status_code,second.result(12).status_code]
                assert codes in ([302,200],[302,302]),codes
            assert len(events())==count+1
        # Eligibility readers take the same shared item lock as manual stock and Procurement.
        blocker=mysql.connector.connect(**options);cur=blocker.cursor();blocker.start_transaction()
        cur.execute('SELECT is_active FROM inventory_items WHERE item_id=%s FOR SHARE',(bid,));cur.fetchone()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(lambda:items.set_inventory_item_active_status(bid,True))
                try:wait_for_lock()
                finally:blocker.commit()
                assert future.result(12) is True
        finally:blocker.close()
        assert (sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True))==historical
        print('PASS observed duplicate/edit/status lock waits, one audit after changed commit, concurrent no-ops and serialization with manual stock/Procurement eligibility locks')
        # Existing receiving policy intentionally differs from new manual stock:
        # a sent PO may receive an item deactivated after ordering.
        import uuid
        stock=importlib.import_module('stock_repository');gr=importlib.import_module('goods_receipt_repository')
        for module in (stock,gr):stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        supplier=sql("INSERT INTO suppliers(supplier_code,supplier_name) VALUES('ITEM-TEST','Synthetic')")
        oid=sql("INSERT INTO purchase_orders(po_number,supplier_id,created_by,status) VALUES('ITEM-RECEIVE',%s,1,'SENT')",(supplier,))
        oi=sql('INSERT INTO purchase_order_items(purchase_order_id,item_id,quantity,unit_cost) VALUES(%s,%s,1,0)',(oid,bid))
        items.set_inventory_item_active_status(bid,False)
        before=snapshot()
        try:stock.stock_in(bid,1,'1',None,1,submission_id=str(uuid.uuid4()))
        except ValueError as error:assert 'inactive' in str(error)
        else:raise AssertionError('Manual stock accepted inactive item')
        assert snapshot()==before
        gr.create_goods_receipt(oid,1,1,{oi:'0.50'},submission_id=str(uuid.uuid4()))
        assert sql('SELECT quantity FROM inventory_stock WHERE item_id=%s AND warehouse_id=1',(bid,),True)==[(Decimal('0.50'),)]
        sql('UPDATE warehouses SET is_active=0 WHERE warehouse_id=1');before=snapshot()
        try:gr.create_goods_receipt(oid,1,1,{oi:'0.50'},submission_id=str(uuid.uuid4()))
        except ValueError as error:assert 'warehouse' in str(error).lower()
        else:raise AssertionError('Receiving accepted inactive warehouse')
        assert snapshot()==before
        print('PASS unchanged inactive-item sent-PO receiving, manual stock denial and inactive warehouse receiving denial')
        before=snapshot();raw=erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert raw.post(path,data=form).status_code==400
        assert c.post('/inventory/items/99999/status',data={'is_active':'0'}).status_code==404
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='inventory.items.manage'")
        for route,data in ((path,form),(status,{'is_active':'0'}),('/inventory/items/add',form)):
            assert c.post(route,data=data).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS CSRF, missing records and fresh permission revocation prevent item writes/audits')
    print('SUCCESS: Inventory Items used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
