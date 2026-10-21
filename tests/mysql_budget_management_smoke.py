"""Budget management on a verified disposable MySQL server; never company data."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client,stamp_session


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir');assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_budget_management');cur.execute('USE erp_budget_management')
        for name in ('core','inventory','procurement','finance','budget','audit_logs'):
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        db.commit()
    options['database']='erp_budget_management';local=threading.local()
    def raw():
        db=mysql.connector.connect(**options);cur=db.cursor();cur.execute("SET SESSION sql_mode=''");cur.close();return db
    class Proxy:
        def __init__(self,db):self.db=db
        def __getattr__(self,key):return getattr(self.db,key)
        def commit(self):
            hold=getattr(local,'hold',None)
            if hold:
                local.hold=None;hold[0].set();assert hold[1].wait(12)
            mode=getattr(local,'failure',None)
            if mode=='before':raise mysql.connector.Error('Synthetic commit failure',errno=2013)
            self.db.commit()
            if mode=='after':raise mysql.connector.Error('Synthetic lost acknowledgment',errno=2013)
        def __enter__(self):return self
        def __exit__(self,*args):self.db.close()
    def connect():return Proxy(raw())
    def sql(query,params=(),fetch=False):
        with raw() as db:
            cur=db.cursor();cur.execute(query,params);result=cur.fetchall() if fetch else cur.lastrowid;db.commit();return result
    def snapshot():return tuple(sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('department_budgets','expenses','audit_logs','departments','users'))
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic Finance'),(2,'Synthetic viewer')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'budget-manager','synthetic'),(2,2,'budget-viewer','synthetic')")
    for code in ('finance.view','finance.expenses.manage'):
        pid=sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,));sql('INSERT INTO role_permissions VALUES(1,%s)',(pid,))
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='finance.view'")
    sql("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'BUD1','Budget one',1),(2,'BUD2','Historical inactive',0),(3,'BUD3','Budget race',1)")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES(1,'SYN','Synthetic')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-budget-mysql',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        budgets=importlib.import_module('budget_repository');stack.enter_context(patch.object(budgets,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True));stack.enter_context(patch('database.ensure_ready'))
        def client(uid=1):
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(uid))
            return c
        c=client()
        def events():return sql("SELECT action,entity_id,description FROM audit_logs WHERE entity_type='DEPARTMENT_BUDGET' ORDER BY audit_log_id",fetch=True)
        form=dict(department_id='1',budget_year='2026',budget_amount='100.00',notes='PRIVATE notes')
        assert c.post('/finance/budgets/add',data=form).status_code==302
        bid=sql('SELECT budget_id FROM department_budgets WHERE department_id=1 AND budget_year=2026',fetch=True)[0][0]
        assert events()[0][0:2]==('CREATE',str(bid))
        before=snapshot();assert c.post(f'/finance/budgets/{bid}/edit',data=form).status_code==302;assert snapshot()==before
        assert c.post('/finance/budgets/add',data=dict(form,department_id='2',budget_amount='200')).status_code==302
        assert len(events())==2  # Inactive Department eligibility is deliberately unchanged.
        for changes in ({'department_id':'bad'},{'department_id':'99999'},{'budget_year':'999'},{'budget_year':'10000'},{'budget_amount':'NaN'},{'budget_amount':'0'},{'budget_amount':'1.001'},{'budget_amount':'1000000000000'},{'notes':'x'*256},{'notes':'x\x00'}):
            for path in ('/finance/budgets/add',f'/finance/budgets/{bid}/edit'):
                before=snapshot();response=c.post(path,data=dict(form,**changes));assert response.status_code==200 and 'alert-danger' in response.get_data(as_text=True);assert snapshot()==before
        before=snapshot();assert c.post('/finance/budgets/add',data=form).status_code==200;assert snapshot()==before
        # Exact paid-only/year/Department semantics, including unbudgeted exclusions.
        for name,did,status,amount,when in [('P1',1,'PAID','10.10','2026-01-01'),('P2',1,'PAID','5.05','2026-12-31'),('A',1,'APPROVED','900','2026-01-01'),('D',1,'DRAFT','900','2026-01-01'),('C',1,'CANCELLED','900','2026-01-01'),('OLD',1,'PAID','600','2025-01-01'),('NO-DEPT',None,'PAID','9000','2026-01-01'),('NO-BUDGET',3,'PAID','99','2026-01-01')]:
            sql("INSERT INTO expenses(expense_number,expense_date,category_id,department_id,description,amount,status,created_by) VALUES(%s,%s,1,%s,'Synthetic',%s,%s,1)",(name,when,did,amount,status))
        page=budgets.get_department_budget_page({'year':'2026'},2026)
        assert page['summary']==dict(department_count=2,total_budget=Decimal('300'),total_spent=Decimal('15.15'),total_remaining=Decimal('284.85'))
        assert page['summary']==budgets.get_budget_summary(2026)
        old=budgets.get_all_department_budgets(2026)
        assert page['records']==old
        assert budgets.get_department_budget_page({'year':'2026','department_id':'2'},2026)['total']==1
        assert budgets.get_department_budget_page({'year':'2026','department_id':'none'},2026)['total']==0
        assert budgets.get_department_budget_page({'year':'2026','department_id':'99999'},2026)['total']==0
        print('PASS exact legacy Decimal paid/year/Department totals and summary equivalence; inactive Department budgets, validation, duplicates and unchanged no-op/history')
        # Large historical list and full sums remain independent of page bounds.
        with raw() as db:
            cur=db.cursor();cur.executemany("INSERT INTO departments(department_code,department_name,is_active) VALUES(%s,%s,0)",[(f'BUD-ARCH-{i:04d}',f'Archive {i:04d}') for i in range(1005)])
            cur.execute("SELECT department_id FROM departments WHERE department_code LIKE 'BUD-ARCH-%' ORDER BY department_id");ids=[r[0] for r in cur.fetchall()]
            cur.executemany("INSERT INTO department_budgets(department_id,budget_year,budget_amount,notes,created_by) VALUES(%s,2010,1,'PRIVATE history',1)",[(did,) for did in ids]);db.commit()
        before=snapshot();seen=[]
        for size in (25,50,100):
            page=budgets.get_department_budget_page(dict(year='2010',search='BUD-ARCH',page_size=str(size)),2026)
            assert page['total']==1005 and len(page['records'])==size and page['summary']['total_budget']==Decimal('1005.00')
        for number in range(1,12):
            page=budgets.get_department_budget_page(dict(year='2010',search='BUD-ARCH',page_size='100',page=str(number)),2026)
            seen.extend(r['budget_id'] for r in page['records']);assert page['summary']['total_remaining']==Decimal('1005')
        assert len(seen)==len(set(seen))==1005 and seen==sorted(seen)
        page=budgets.get_department_budget_page(dict(year='2010',search='BUD-ARCH',page_size='100',page='999'),2026)
        assert (page['first'],page['last'],page['filters']['page'])==(1001,1005,11)
        for query in ('year=NaN','year=','department_id=bad','page_size=500','page=0','year=2026&year=2027','search='+('x'*101),'status=PAID'):
            response=c.get('/finance/budgets?'+query);assert response.status_code==400 and 'Total Budget' not in response.get_data(as_text=True)
        for needle in ('BUD-ARCH%',"' OR 1=1 --",'PRIVATE'):
            assert budgets.get_department_budget_page(dict(year='2010',search=needle),2026)['total']==0
        assert snapshot()==before
        did=sql("INSERT INTO departments(department_code,department_name) VALUES('LITERAL%_!','Literal search')")
        budgets.create_department_budget(did,2010,'1',None,1)
        assert budgets.get_department_budget_page(dict(year='2010',search='%_!'),2026)['total']==1
        print('PASS 1005 historical rows reachable, 25/50/100 pages, all-match totals, stable ordering, literal search, invalid filters and private notes excluded from search')
        # Real paid insert between aggregate and page queries stays outside snapshot.
        inserted=False
        class Cursor:
            def __init__(self,cur):self.cur=cur
            def __getattr__(self,name):return getattr(self.cur,name)
            def execute(self,query,params=()):
                nonlocal inserted
                result=self.cur.execute(query,params)
                if query.startswith('SELECT COUNT(*) AS department_count') and not inserted:
                    inserted=True;sql("INSERT INTO expenses(expense_number,expense_date,category_id,department_id,description,amount,status,created_by) VALUES('SNAPSHOT','2026-01-01',1,1,'Synthetic',0.01,'PAID',1)")
                return result
        class SnapshotConnection(Proxy):
            def cursor(self,**kw):return Cursor(self.db.cursor(**kw))
        with patch.object(budgets,'get_connection',side_effect=lambda:SnapshotConnection(raw())):
            page=budgets.get_department_budget_page(dict(year='2026',department_id='1'),2026)
            assert page['summary']['total_spent']==page['records'][0]['spent_amount']==Decimal('15.15')
        assert budgets.get_department_budget_page(dict(year='2026',department_id='1'),2026)['summary']['total_spent']==Decimal('15.16')
        # Late SQL failure and uncertain acknowledgment must never emit success.
        before=snapshot();sql("CREATE TRIGGER budget_failure BEFORE UPDATE ON department_budgets FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        try:assert c.post(f'/finance/budgets/{bid}/edit',data=dict(form,budget_amount='110')).status_code==503
        finally:sql('DROP TRIGGER budget_failure')
        assert snapshot()==before
        for action in (lambda:c.post(f'/finance/budgets/{bid}/edit',data=dict(form,budget_amount='110')),
                       lambda:c.post('/finance/budgets/add',data=dict(form,budget_year='2030'))):
            local.failure='before'
            try:assert action().status_code==503
            finally:local.failure=None
            assert snapshot()==before
        count=len(events());local.failure='after'
        try:assert c.post(f'/finance/budgets/{bid}/edit',data=dict(form,budget_amount='111')).status_code==503
        finally:local.failure=None
        assert sql('SELECT budget_amount FROM department_budgets WHERE budget_id=%s',(bid,),True)==[(Decimal('111'),)] and len(events())==count
        sql("CREATE TRIGGER budget_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        try:
            with patch.object(erp.app.logger,'exception'):
                assert c.post(f'/finance/budgets/{bid}/edit',data=dict(form,budget_amount='112')).status_code==302
        finally:sql('DROP TRIGGER budget_audit_failure')
        assert sql('SELECT budget_amount FROM department_budgets WHERE budget_id=%s',(bid,),True)==[(Decimal('112'),)] and len(events())==count
        print('PASS aggregate/page financial snapshot during real paid insert; SQL/commit rollback, uncertain commit reconciliation and audit failure leave confirmed financial data intact')
        def wait_for_lock():
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits',fetch=True)[0][0]:return
                time.sleep(.03)
            raise AssertionError('Expected InnoDB lock wait not observed')
        def held(action,entered,release):
            local.hold=(entered,release)
            try:return action()
            finally:local.hold=None
        # Observe unique pair and edit lock waits, with no audit before commit.
        count=len(events());race=dict(form,department_id='3',budget_year='2027')
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:client().post('/finance/budgets/add',data=race),entered,release)
            assert entered.wait(8);second=pool.submit(lambda:client().post('/finance/budgets/add',data=race))
            try:wait_for_lock();assert len(events())==count
            finally:release.set()
            assert first.result(10).status_code==302 and second.result(10).status_code==200
        assert len(events())==count+1
        count=len(events());edit=dict(form,budget_amount='113')
        with ThreadPoolExecutor(max_workers=2) as pool:
            entered,release=threading.Event(),threading.Event()
            first=pool.submit(held,lambda:client().post(f'/finance/budgets/{bid}/edit',data=edit),entered,release)
            assert entered.wait(8);second=pool.submit(lambda:client().post(f'/finance/budgets/{bid}/edit',data=edit))
            try:wait_for_lock();assert len(events())==count
            finally:release.set()
            assert first.result(10).status_code==second.result(10).status_code==302
        assert len(events())==count+1
        # Department status changes still do not introduce an active-only budget rule.
        blocker=raw();cur=blocker.cursor();cur.execute('UPDATE departments SET is_active=0 WHERE department_id=3')
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(lambda:client().post('/finance/budgets/add',data=dict(race,budget_year='2028')))
                try:wait_for_lock()
                finally:blocker.commit()
                assert future.result(10).status_code==302
        finally:blocker.close()
        assert c.get('/finance/budgets/99999/edit').location.endswith('/finance/budgets')
        try:budgets.update_department_budget(99999,1,2026,'1',None)
        except ValueError:pass
        else:raise AssertionError('Missing budget silently updated')
        assert all('PRIVATE' not in row[2] and '113.00' not in row[2] for row in events())
        print('PASS observed duplicate/edit lock waits, exactly one post-commit audit per changed operation, no-op concurrency, missing records and unchanged inactive Department eligibility')
        # Actual nontransactional Finance storage fails closed; no automatic DDL.
        before=snapshot()
        for table in ('department_budgets','expenses'):
            sql('CREATE TABLE unsupported_fixture LIKE '+table)
            sql('ALTER TABLE unsupported_fixture ENGINE=MyISAM')
            sql('RENAME TABLE '+table+' TO saved_fixture,unsupported_fixture TO '+table)
            try:
                response=c.get('/finance/budgets?year=2026')
                assert response.status_code==503 and 'Total Budget' not in response.get_data(as_text=True)
                if table=='department_budgets':
                    assert c.post('/finance/budgets/add',data=dict(form,budget_year='2040')).status_code==503
                    try:budgets.update_department_budget(bid,1,2026,'1',None)
                    except ValueError as error:assert getattr(error,'status_code',None)==503
                    else:raise AssertionError('Nontransactional Budget write succeeded')
                assert sql('SELECT COUNT(*) FROM '+table,fetch=True)==[(0,)]
            finally:
                sql('RENAME TABLE '+table+' TO unsupported_fixture,saved_fixture TO '+table)
                sql('DROP TABLE unsupported_fixture')
            assert snapshot()==before
        print('PASS real MyISAM Budget writes/page and Expense page storage fail closed, no repair or financial/audit mutations')
        before=snapshot();viewer=client(2)
        assert viewer.get('/finance/budgets?year=2026').status_code==200
        assert viewer.post('/finance/budgets/add',data=form).location.endswith('/dashboard')
        no_csrf=erp.app.test_client()
        with no_csrf.session_transaction() as session:stamp_session(erp.app,session,erp.get_authorization_state(1))
        assert no_csrf.post('/finance/budgets/add',data=form).status_code==400
        assert snapshot()==before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND p.permission_code='finance.expenses.manage'")
        assert c.post(f'/finance/budgets/{bid}/edit',data=form).location.endswith('/dashboard');assert snapshot()==before
        print('SUCCESS: Budget Management used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
