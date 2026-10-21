"""Expense Categories management regression on a verified disposable MySQL server only."""
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
        cursor.execute('CREATE DATABASE erp_expense_categories_test');cursor.execute('USE erp_expense_categories_test')
        for name in ('core','inventory','procurement','finance','budget','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_expense_categories_test'
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
    def snapshot():return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('expense_categories','expenses','department_budgets','audit_logs')]
    def finance_history():return snapshot()[1:3]
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Finance category test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'category.test','synthetic')")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name,is_active) VALUES(1,'BASE','Base',1),(2,'INACTIVE','Inactive',0)")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-expense-category-mysql',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        repo=importlib.import_module('expense_category_repository');stack.enter_context(patch.object(repo,'get_connection',side_effect=connect))
        expenses=importlib.import_module('expense_repository');stack.enter_context(patch.object(expenses,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True));stack.enter_context(patch('database.ensure_ready'))
        for code in ('finance.view','finance.categories.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,));sql('INSERT INTO role_permissions(role_id,permission_id) VALUES(1,%s)',(pid,))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
            return c
        c=client();form=dict(category_code='CREATED',category_name='PRIVATE category',description='PRIVATE notes')
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='EXPENSE_CATEGORY' ORDER BY audit_log_id",fetch=True)
        assert c.post('/finance/expense-categories/add',data=form).status_code==302
        bid=sql("SELECT category_id FROM expense_categories WHERE category_code='CREATED'",fetch=True)[0][0]
        for number,state in enumerate(('DRAFT','APPROVED','PAID','CANCELLED'),1):
            sql("INSERT INTO expenses(expense_number,expense_date,category_id,description,amount,status,created_by) VALUES(%s,'2026-01-01',%s,'Historical',%s,%s,1)",('HISTORY-'+state,bid,Decimal(number)+Decimal('0.01'),state))
        preserved=finance_history();path=f'/finance/expense-categories/{bid}/edit';status=f'/finance/expense-categories/{bid}/status'
        before=snapshot();assert c.post(path,data=form).status_code==302;assert snapshot()==before
        assert c.post(path,data=dict(form,description='PRIVATE revised')).status_code==302
        assert c.post(status,data={'is_active':'0'}).status_code==302
        before=snapshot();assert c.post(status,data={'is_active':'0'}).status_code==302;assert snapshot()==before
        assert c.post(status,data={'is_active':'1'}).status_code==302
        assert [e[0] for e in events()]==['CREATE','UPDATE','DEACTIVATE','ACTIVATE']
        assert all('PRIVATE' not in e[2] for e in events())
        before=snapshot();assert c.post('/finance/expense-categories/add',data=form).status_code==200;assert snapshot()==before
        assert repo.create_expense_category('lower','PRIVATE category')>0  # Names remain non-unique and repository code casing remains intact.
        assert sql("SELECT category_code FROM expense_categories WHERE category_code='lower'",fetch=True)==[('lower',)]
        for changes in ({'category_code':''},{'category_name':''},{'category_code':'x'*31},{'category_name':'x'*101},{'description':'x'*256},{'category_name':'x\x00'}):
            before=snapshot();assert c.post(path,data=dict(form,**changes)).status_code in (200,400);assert snapshot()==before
        assert finance_history()==preserved
        print('PASS field bounds, duplicate code with non-unique names, legacy casing/read contracts, four confirmed audits and preserved DRAFT/APPROVED/PAID/CANCELLED history')
        with mysql.connector.connect(**options) as db:
            cur=db.cursor();cur.executemany("INSERT INTO expense_categories(category_code,category_name,description,is_active) VALUES(%s,'Historical tied name','PRIVATE history',0)",[(f'EXP-HISTORY-{i:04d}',) for i in range(1005)])
            cur.execute("INSERT INTO expense_categories(category_code,category_name) VALUES('LITERAL','Literal %_!')");db.commit()
        before=snapshot()
        for size in (25,50,100):
            seen=[]
            for number in range(1,(1005+size-1)//size+1):
                page=repo.get_expense_category_page(dict(search='EXP-HISTORY',status='inactive',page_size=str(size),page=str(number)))
                assert page['total']==1005 and len(page['records'])<=size
                seen.extend(row['category_id'] for row in page['records'])
            assert len(seen)==len(set(seen))==1005 and seen==sorted(seen)
        assert repo.get_expense_category_page(dict(search='EXP-HISTORY',page='999',page_size='100'))['first']==1001
        assert repo.get_expense_category_page(dict(search='%_!'))['total']==1
        assert repo.get_expense_category_page(dict(search='PRIVATE history'))['total']==0
        for query in ('page=0','page_size=500','status=bad','search=x&search=y','unknown=x'):
            response=c.get('/finance/expense-categories?'+query);assert response.status_code==400 and 'matching categories' not in response.get_data(as_text=True)
        assert snapshot()==before
        inserted=False
        class SnapshotCursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,key):return getattr(self.cur,key)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True;sql("INSERT INTO expense_categories(category_code,category_name,is_active) VALUES('EXP-HISTORY-NEW','Historical tied name',0)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return SnapshotCursor(self.connection.cursor(**kw))
        with patch.object(repo,'get_connection',side_effect=lambda:SnapshotConnection(mysql.connector.connect(**options))):
            page=repo.get_expense_category_page(dict(search='EXP-HISTORY',page_size='100',page='11'));assert page['total']==1005 and len(page['records'])==5
        assert repo.get_expense_category_page(dict(search='EXP-HISTORY'))['total']==1006
        print('PASS 1005 tied-name categories reachable in 25/50/100 pages, stable ordering, literal/combined/invalid filters and count/page snapshot under concurrent insert')
        before=snapshot();sql("CREATE TRIGGER category_failure BEFORE UPDATE ON expense_categories FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic update failure'")
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
            else:assert sql('SELECT category_name FROM expense_categories WHERE category_id=%s',(bid,),True)==[('Unconfirmed after',)]
        sql("CREATE TRIGGER category_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(path,data=dict(form,category_name='Audit unavailable')).status_code==302
        finally:sql('DROP TRIGGER category_audit_failure')
        assert len(events())==count
        print('PASS edit/status SQL rollback, commit failure rollback, uncertain committed write reconciliation and audit failure isolation')
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
        for action in (lambda:client().post('/finance/expense-categories/add',data=dict(form,category_code='RACE-CODE')),
                       lambda:client().post(path,data=dict(form,category_name='Concurrent same')),
                       lambda:client().post(status,data={'is_active':'0'})):
            count=len(events());entered=threading.Event();release=threading.Event()
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(hold,action,entered,release)
                try:
                    assert entered.wait(8);second=pool.submit(action);wait_for_lock();assert len(events())==count
                finally:release.set()
                codes=[first.result(12).status_code,second.result(12).status_code];assert codes in ([302,200],[302,302]),codes
            assert len(events())==count+1
        assert finance_history()==preserved
        # Expense reference commits first: category deactivation waits and preserves it.
        repo.set_expense_category_active_status(bid,True)
        expense=lambda:expenses.create_expense('2026-01-01',bid,None,None,None,'Category concurrency','1.00',None,None,1,None)
        entered=threading.Event();release=threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,expense,entered,release)
            try:
                assert entered.wait(8);second=pool.submit(lambda:repo.set_expense_category_active_status(bid,False));wait_for_lock()
            finally:release.set()
            eid,_=first.result(12);assert second.result(12) is True
        assert sql('SELECT category_id FROM expenses WHERE expense_id=%s',(eid,),True)==[(bid,)]
        # Current active-only rules also apply to edits retaining an inactive category.
        before=snapshot()
        try:expenses.update_expense(eid,'2026-01-01',bid,None,None,None,'Changed','1',None,None,None)
        except ValueError as error:assert 'inactive' in str(error)
        else:raise AssertionError('Expense edit bypassed inactive category eligibility')
        assert snapshot()==before
        repo.set_expense_category_active_status(bid,True);before=snapshot()
        entered=threading.Event();release=threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(hold,lambda:repo.set_expense_category_active_status(bid,False),entered,release)
            try:
                assert entered.wait(8);second=pool.submit(expense);wait_for_lock()
            finally:release.set()
            assert first.result(12) is True
            try:second.result(12)
            except ValueError as error:assert 'inactive' in str(error)
            else:raise AssertionError('Expense accepted inactive category')
        assert finance_history()==before[1:3]
        print('PASS observed duplicate/edit/status locks, one post-commit audit per change, both real expense/deactivation orders and unchanged inactive-category eligibility/history')
        # Fail closed on actual unsupported Finance category storage without repair.
        before=snapshot();sql('CREATE TABLE unsupported_category LIKE expense_categories');sql('ALTER TABLE unsupported_category ENGINE=MyISAM')
        sql('RENAME TABLE expense_categories TO saved_category,unsupported_category TO expense_categories')
        try:
            assert c.get('/finance/expense-categories').status_code==503
            assert c.post('/finance/expense-categories/add',data=dict(form,category_code='STORAGE')).status_code==503
            try:repo.set_expense_category_active_status(bid,True)
            except ValueError as error:assert getattr(error,'status_code',None)==503
            else:raise AssertionError('Nontransactional category write accepted')
            assert sql('SELECT COUNT(*) FROM expense_categories',fetch=True)==[(0,)]
        finally:
            sql('RENAME TABLE expense_categories TO unsupported_category,saved_category TO expense_categories');sql('DROP TABLE unsupported_category')
        assert snapshot()==before
        raw=erp.app.test_client()
        with raw.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert raw.post(path,data=form).status_code==400
        assert c.post('/finance/expense-categories/99999/status',data={'is_active':'0'}).status_code==404
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='finance.categories.manage'")
        for route,data in ((path,form),(status,{'is_active':'0'}),('/finance/expense-categories/add',form)):
            assert c.post(route,data=data).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS real MyISAM storage rejection without repair, CSRF, missing records and fresh permission revocation; no failed request success audits')
    print('SUCCESS: Expense Category management used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
