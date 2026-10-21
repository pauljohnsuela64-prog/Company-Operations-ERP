"""Inventory Categories management regression on a verified disposable MySQL server only."""
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
        cursor.execute('CREATE DATABASE erp_inventory_categories_test');cursor.execute('USE erp_inventory_categories_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_inventory_categories_test'
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
        for code in ('inventory.view','inventory.categories.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,))
            sql('INSERT INTO role_permissions(role_id,permission_id) VALUES(1,%s)',(pid,))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
            return c
        c=client();form=dict(category_code='CREATED',category_name='PRIVATE category',description='PRIVATE notes')
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='INVENTORY_CATEGORY' ORDER BY audit_log_id",fetch=True)
        def inventory_history():return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('inventory_items','inventory_stock','stock_movements')]
        preserved=inventory_history()
        assert c.post('/inventory/categories/add',data=form).status_code==302
        bid=sql("SELECT category_id FROM inventory_categories WHERE category_code='CREATED'",fetch=True)[0][0]
        path=f'/inventory/categories/{bid}/edit';status=f'/inventory/categories/{bid}/status'
        before=snapshot();assert c.post(path,data=form).status_code==302;assert snapshot()==before
        assert c.post(path,data=dict(form,description='PRIVATE revised')).status_code==302
        assert c.post(status,data={'is_active':'0'}).status_code==302
        before=snapshot();assert c.post(status,data={'is_active':'0'}).status_code==302;assert snapshot()==before
        assert c.post(status,data={'is_active':'1'}).status_code==302
        assert [e[0] for e in events()]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE']
        assert all('PRIVATE' not in e[2] for e in events())
        for changes in ({},{'category_code':'OTHER-CODE'},{'category_name':'Other name'}):
            before=snapshot();assert c.post('/inventory/categories/add',data=dict(form,**changes)).status_code==200;assert snapshot()==before
        for changes in ({'category_code':'x'*31},{'category_name':'x'*101},{'description':'x'*256},{'category_name':'x\x00'}):
            before=snapshot();assert c.post(path,data=dict(form,**changes)).status_code in (200,400);assert snapshot()==before
        assert inventory_history()==preserved
        print('PASS exact text bounds, duplicate code/name handling, retained forms, four post-commit audits, unchanged writes produce no updates/audits or inventory/history changes')
        with mysql.connector.connect(**options) as db:
            cur=db.cursor();cur.executemany("INSERT INTO inventory_categories(category_code,category_name,description,is_active) VALUES(%s,%s,'PRIVATE history',0)",[(f'CAT-HISTORY-{i:04d}',f'Historical {i:04d}') for i in range(1005)])
            cur.execute("INSERT INTO inventory_categories(category_code,category_name) VALUES('LITERAL','Literal %_!')");db.commit()
        before=snapshot()
        for size in (25,50,100):
            seen=[]
            for number in range(1,(1005+size-1)//size+1):
                page=categories.get_inventory_category_page(dict(search='CAT-HISTORY',status='inactive',page_size=str(size),page=str(number)))
                assert page['total']==1005 and len(page['records'])<=size
                seen.extend(row['category_id'] for row in page['records'])
            assert len(seen)==len(set(seen))==1005 and seen==sorted(seen)
        assert categories.get_inventory_category_page(dict(search='CAT-HISTORY',page='999',page_size='100'))['first']==1001
        assert categories.get_inventory_category_page(dict(search='%_!'))['total']==1
        assert categories.get_inventory_category_page(dict(search='PRIVATE'))['total']==1  # Name only; private descriptions excluded.
        for query in ('page=0','page_size=500','status=bad','search=x&search=y','unknown=x'):
            response=c.get('/inventory/categories?'+query);assert response.status_code==400 and 'matching categories' not in response.get_data(as_text=True)
        assert snapshot()==before
        inserted=False
        class SnapshotCursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,key):return getattr(self.cur,key)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True;sql("INSERT INTO inventory_categories(category_code,category_name,is_active) VALUES('CAT-HISTORY-NEW','Historical concurrent',0)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return SnapshotCursor(self.connection.cursor(**kw))
        with patch.object(categories,'get_connection',side_effect=lambda:SnapshotConnection(mysql.connector.connect(**options))):
            page=categories.get_inventory_category_page(dict(search='CAT-HISTORY',page_size='100',page='11'))
            assert page['total']==1005 and len(page['records'])==5
        assert categories.get_inventory_category_page(dict(search='CAT-HISTORY'))['total']==1006
        print('PASS 1005 categories reachable in 25/50/100 pages, stable ordering, active filters, literal search, invalid filters and snapshot count/rows during concurrent insert')
        before=snapshot();sql("CREATE TRIGGER category_failure BEFORE UPDATE ON inventory_categories FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic update failure'")
        try:
            assert c.post(path,data=dict(form,category_name='SQL fail')).status_code==503
            assert c.post(status,data={'is_active':'0'}).status_code==503
        finally:sql('DROP TRIGGER category_failure')
        assert snapshot()==before
        for mode in ('before','after'):
            count=len(events());local.failure=mode
            try:assert c.post(path,data=dict(form,category_name='Unconfirmed '+mode)).status_code==503
            finally:local.failure=None
            assert len(events())==count
            if mode=='before':assert snapshot()==before
            else:assert sql('SELECT category_name FROM inventory_categories WHERE category_id=%s',(bid,),True)==[('Unconfirmed after',)]
        sql("CREATE TRIGGER category_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(path,data=dict(form,category_name='Audit unavailable')).status_code==302
        finally:sql('DROP TRIGGER category_audit_failure')
        assert len(events())==count
        assert sql('SELECT category_name FROM inventory_categories WHERE category_id=%s',(bid,),True)==[('Audit unavailable',)]
        print('PASS SQL rollback for edit/status, commit failure rollback, uncertain committed write reconciliation and audit failure isolation')
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
        for action in (lambda:client().post('/inventory/categories/add',data=dict(form,category_code='RACE-CODE',category_name='Race name')),
                       lambda:client().post(path,data=dict(form,category_name='Concurrent same')),
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
        assert inventory_history()==preserved
        # Item assignment commits first: deactivation waits, then preserves assignment.
        categories.set_inventory_category_active_status(bid,True)
        entered=threading.Event();release=threading.Event()
        assign=lambda:items.create_inventory_item('ASSIGN-FIRST','Synthetic',bid,None,'pcs','0')
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,assign,entered,release)
            try:
                assert entered.wait(8);second=pool.submit(lambda:categories.set_inventory_category_active_status(bid,False));wait_for_lock()
            finally:release.set()
            item_id=first.result(12);assert second.result(12) is True
        preserved=inventory_history()
        assert categories.set_inventory_category_active_status(bid,False) is False
        assert inventory_history()==preserved
        assert items.update_inventory_item(item_id,'ASSIGN-FIRST','Synthetic',bid,None,'pcs','0') is False
        assert items.update_inventory_item(item_id,'ASSIGN-FIRST','Allowed retention',bid,None,'pcs','0') is True
        # Deactivation commits first: a blocked NEW assignment is rejected.
        categories.set_inventory_category_active_status(bid,True)
        entered=threading.Event();release=threading.Event();before=snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,lambda:categories.set_inventory_category_active_status(bid,False),entered,release)
            try:
                assert entered.wait(8)
                second=pool.submit(lambda:items.create_inventory_item('ASSIGN-AFTER','Synthetic',bid,None,'pcs','0'));wait_for_lock()
            finally:release.set()
            assert first.result(12) is True
            try:second.result(12)
            except ValueError as error:assert 'new assignments' in str(error)
            else:raise AssertionError('New assignment accepted inactive category')
        assert sql("SELECT COUNT(*) FROM inventory_items WHERE item_code='ASSIGN-AFTER'",fetch=True)==[(0,)]
        assert inventory_history()==before[2:5]
        print('PASS observed duplicate/edit/status lock waits and one audit per changed commit; both item assignment/deactivation orders, inactive retention and unchanged history')
        before=snapshot();raw=erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert raw.post(path,data=form).status_code==400
        assert c.post('/inventory/categories/99999/status',data={'is_active':'0'}).status_code==404
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='inventory.categories.manage'")
        for route,data in ((path,form),(status,{'is_active':'0'}),('/inventory/categories/add',form)):
            assert c.post(route,data=data).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS CSRF, missing records and fresh permission revocation prevent category writes/audits')
    print('SUCCESS: Inventory Categories used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
