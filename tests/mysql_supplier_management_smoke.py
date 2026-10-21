"""Supplier management regression on a verified disposable MySQL server only."""
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
        cursor.execute('CREATE DATABASE erp_supplier_management_test');cursor.execute('USE erp_supplier_management_test')
        for name in ('core','inventory','procurement','finance','budget','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_supplier_management_test'
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
        return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('suppliers','purchase_orders','purchase_order_items','expenses','inventory_stock','stock_movements','audit_logs')]
    def relations():return snapshot()[1:6]
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Supplier test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'supplier.test','synthetic')")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES(1,'SUPPLIER','Supplier test')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-supplier-mysql',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        repo=importlib.import_module('supplier_repository');stack.enter_context(patch.object(repo,'get_connection',side_effect=connect))
        expenses=importlib.import_module('expense_repository');stack.enter_context(patch.object(expenses,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True));stack.enter_context(patch('database.ensure_ready'))
        for code in ('procurement.view','procurement.suppliers.manage','procurement.orders.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,))
            sql('INSERT INTO role_permissions(role_id,permission_id) VALUES(1,%s)',(pid,))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
            return c
        c=client();form=dict(supplier_code='CREATED',supplier_name='PRIVATE supplier',contact_person='PRIVATE contact',email='private@example.test',phone='PRIVATE phone',address='PRIVATE address')
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='SUPPLIER' ORDER BY audit_log_id",fetch=True)
        assert c.post('/procurement/suppliers/add',data=form).status_code==302
        bid=sql("SELECT supplier_id FROM suppliers WHERE supplier_code='CREATED'",fetch=True)[0][0]
        oid=sql("INSERT INTO purchase_orders(po_number,supplier_id,created_by,status) VALUES('SUPPLIER-HISTORY',%s,1,'SENT')",(bid,))
        sql("INSERT INTO expenses(expense_number,expense_date,category_id,supplier_id,purchase_order_id,description,amount,status,created_by) VALUES('SUPPLIER-HISTORY','2026-01-01',1,%s,%s,'Historical',10,'PAID',1)",(bid,oid))
        preserved=relations();path=f'/procurement/suppliers/{bid}/edit';status=f'/procurement/suppliers/{bid}/status'
        before=snapshot();assert c.post(path,data=form).status_code==302;assert snapshot()==before
        assert c.post(path,data=dict(form,address='PRIVATE revised')).status_code==302
        assert c.post(status,data={'is_active':'0'}).status_code==302
        before=snapshot();assert c.post(status,data={'is_active':'0'}).status_code==302;assert snapshot()==before
        assert c.post(status,data={'is_active':'1'}).status_code==302
        assert [e[0] for e in events()]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE']
        assert all('PRIVATE' not in e[2] and 'private@example' not in e[2] for e in events())
        before=snapshot();assert c.post('/procurement/suppliers/add',data=form).status_code==200;assert snapshot()==before
        optional=dict(supplier_code='OPTIONAL',supplier_name='PRIVATE supplier')
        assert c.post('/procurement/suppliers/add',data=optional).status_code==302  # Names are not unique.
        assert sql("SELECT contact_person,email,phone,address FROM suppliers WHERE supplier_code='OPTIONAL'",fetch=True)==[(None,None,None,None)]
        for changes in ({'supplier_code':''},{'supplier_name':''},{'supplier_code':'x'*31},{'supplier_name':'x'*151},{'contact_person':'x'*101},{'email':'x'*151},{'phone':'x'*31},{'address':'x'*256},{'supplier_name':'x\x00'}):
            before=snapshot();assert c.post(path,data=dict(form,**changes)).status_code in (200,400);assert snapshot()==before
        assert relations()==preserved
        print('PASS required code/name, optional contact/email/phone/address, duplicate-code handling with duplicate names allowed, four confirmed audits and preserved PO/expense relationships')
        with mysql.connector.connect(**options) as db:
            cur=db.cursor();cur.executemany("INSERT INTO suppliers(supplier_code,supplier_name,address,is_active) VALUES(%s,'Historical tied name','PRIVATE history',0)",[(f'SUP-HISTORY-{i:04d}',) for i in range(1005)])
            cur.execute("INSERT INTO suppliers(supplier_code,supplier_name) VALUES('LITERAL','Literal %_!')");db.commit()
        before=snapshot()
        for size in (25,50,100):
            seen=[]
            for number in range(1,(1005+size-1)//size+1):
                page=repo.get_supplier_page(dict(search='SUP-HISTORY',status='inactive',page_size=str(size),page=str(number)))
                assert page['total']==1005 and len(page['records'])<=size
                seen.extend(row['supplier_id'] for row in page['records'])
            assert len(seen)==len(set(seen))==1005 and seen==sorted(seen)
        assert repo.get_supplier_page(dict(search='SUP-HISTORY',page='999',page_size='100'))['first']==1001
        assert repo.get_supplier_page(dict(search='%_!'))['total']==1
        assert repo.get_supplier_page(dict(search='PRIVATE history'))['total']==0
        for query in ('page=0','page_size=500','status=bad','search=x&search=y','unknown=x'):
            response=c.get('/procurement/suppliers?'+query);assert response.status_code==400 and 'matching suppliers' not in response.get_data(as_text=True)
        assert snapshot()==before
        inserted=False
        class SnapshotCursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,key):return getattr(self.cur,key)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True;sql("INSERT INTO suppliers(supplier_code,supplier_name,is_active) VALUES('SUP-HISTORY-NEW','Historical tied name',0)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return SnapshotCursor(self.connection.cursor(**kw))
        with patch.object(repo,'get_connection',side_effect=lambda:SnapshotConnection(mysql.connector.connect(**options))):
            page=repo.get_supplier_page(dict(search='SUP-HISTORY',page_size='100',page='11'))
            assert page['total']==1005 and len(page['records'])==5
        assert repo.get_supplier_page(dict(search='SUP-HISTORY'))['total']==1006
        print('PASS 1005 tied-name suppliers reachable in 25/50/100 pages, stable ordering, literal/combined/invalid filters and count/page snapshot during concurrent insert')
        before=snapshot();sql("CREATE TRIGGER supplier_failure BEFORE UPDATE ON suppliers FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic update failure'")
        try:
            assert c.post(path,data=dict(form,supplier_name='SQL fail')).status_code==503
            assert c.post(status,data={'is_active':'0'}).status_code==503
        finally:sql('DROP TRIGGER supplier_failure')
        assert snapshot()==before
        for mode in ('before','after'):
            count=len(events());local.failure=mode
            try:assert c.post(path,data=dict(form,supplier_name='Unconfirmed '+mode)).status_code==503
            finally:local.failure=None
            assert len(events())==count
            if mode=='before':assert snapshot()==before
            else:assert sql('SELECT supplier_name FROM suppliers WHERE supplier_id=%s',(bid,),True)==[('Unconfirmed after',)]
        sql("CREATE TRIGGER supplier_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(path,data=dict(form,supplier_name='Audit unavailable')).status_code==302
        finally:sql('DROP TRIGGER supplier_audit_failure')
        assert len(events())==count and sql('SELECT supplier_name FROM suppliers WHERE supplier_id=%s',(bid,),True)==[('Audit unavailable',)]
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
        for action in (lambda:client().post('/procurement/suppliers/add',data=dict(form,supplier_code='RACE-CODE')),
                       lambda:client().post(path,data=dict(form,supplier_name='Concurrent same')),
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
        assert relations()==preserved
        # Real Finance writes acquire a supplier FOR SHARE until commit.
        repo.set_supplier_active_status(bid,True)
        expense=lambda:expenses.create_expense('2026-01-01',1,None,bid,None,'Supplier concurrency','1.00',None,None,1,None)
        entered=threading.Event();release=threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,expense,entered,release)
            try:
                assert entered.wait(8);second=pool.submit(lambda:repo.set_supplier_active_status(bid,False));wait_for_lock()
            finally:release.set()
            expense_id,_=first.result(12);assert second.result(12) is True
        assert sql('SELECT supplier_id FROM expenses WHERE expense_id=%s',(expense_id,),True)==[(bid,)]
        repo.set_supplier_active_status(bid,True);before=snapshot()
        entered=threading.Event();release=threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,lambda:repo.set_supplier_active_status(bid,False),entered,release)
            try:
                assert entered.wait(8);second=pool.submit(expense);wait_for_lock()
            finally:release.set()
            assert first.result(12) is True
            try:second.result(12)
            except ValueError as error:assert 'supplier' in str(error).lower() and 'inactive' in str(error)
            else:raise AssertionError('Expense accepted inactive supplier')
        assert relations()==before[1:6]
        print('PASS observed duplicate/edit/status lock waits and exactly one audit after changed commit; both real Finance/deactivation lock orders preserve references')
        # Preserve the PO route policy: reject a supplier already inactive on lookup.
        rid=sql("INSERT INTO purchase_requests(request_number,requested_by,status) VALUES('SUPPLIER-PO-CHECK',1,'APPROVED')")
        item=sql("INSERT INTO inventory_items(item_code,item_name) VALUES('SUPPLIER-PO','Synthetic')")
        sql('INSERT INTO purchase_request_items(request_id,item_id,quantity,estimated_unit_cost) VALUES(%s,%s,1,0)',(rid,item))
        before=snapshot()
        response=c.post(f'/procurement/requests/{rid}/create-order',data={'supplier_id':str(bid)})
        assert response.status_code==200 and 'invalid or inactive' in response.get_data(as_text=True)
        for invalid in ('0','-1','999999999999'):
            response=c.post(f'/procurement/requests/{rid}/create-order',data={'supplier_id':invalid})
            assert response.status_code==200
        assert snapshot()==before
        raw=erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert raw.post(path,data=form).status_code==400
        assert c.post('/procurement/suppliers/99999/status',data={'is_active':'0'}).status_code==404
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='procurement.suppliers.manage'")
        for route,data in ((path,form),(status,{'is_active':'0'}),('/procurement/suppliers/add',form)):
            assert c.post(route,data=data).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS existing PO active-supplier and invalid-ID feedback; optional policy, CSRF, missing records and fresh permission revocation; failed requests leave relationships/audits unchanged')
    print('SUCCESS: Supplier management used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
