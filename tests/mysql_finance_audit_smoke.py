"""Persisted Finance business audit events; disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as c:
        cur=c.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_finance_audit');cur.execute('USE erp_finance_audit')
        for name in ['core','inventory','procurement','finance','budget','audit_logs']:
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        c.commit()
    options['database']='erp_finance_audit'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as c:
            cur=c.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            c.commit();return result
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Finance operator'),(2,'Viewer')")
    for uid in [1,2]:
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES (%s,%s,%s,%s)',(uid,uid,f'finance-{uid}','synthetic'))
    sql("INSERT INTO permissions(permission_code) VALUES ('finance.view'),('finance.expenses.manage'),('finance.categories.manage'),('finance.expenses.approve'),('finance.expenses.pay')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO departments(department_id,department_code,department_name) VALUES (1,'DPT','private-name')")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES (1,'BASE','private-name')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-finance-audit-mysql',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        stack.enter_context(patch.object(erp.app.logger,'exception'))
        def client(uid=1):
            c=erp.app.test_client()
            with c.session_transaction() as sess:
                stamp_session(erp.app,sess,user_state(user_id=uid,role_id=uid,username=f'finance-{uid}',password_hash='synthetic'))
            return c
        c=client();token=csrf_token_for(c)
        def post(path,data=None):return c.post(path,data=dict(data or {},csrf_token=token))
        def rows():return sql('SELECT user_id,username,module,action,entity_type,entity_id,description FROM audit_logs ORDER BY audit_log_id',fetch=True)
        def snapshot():return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ['expenses','expense_categories','department_budgets','audit_logs']]
        def event(path,data,action,entity,eid,label):
            before=len(rows())
            assert post(path,data).status_code==302,path
            after=rows();assert len(after)==before+1,(path,after)
            row=after[-1]
            assert row[:6]==(1,'finance-1','FINANCE',action,entity,str(eid)),row
            assert str(eid) in row[6] and label in row[6],row
            for secret in ['private-name','private-notes','private-description','private-reference','87654.32']:
                assert secret not in str(row),row
            return row

        category=dict(category_code='NEW',category_name='private-name',description='private-description')
        event('/finance/expense-categories/add',category,'CREATE','EXPENSE_CATEGORY',2,'NEW')
        event('/finance/expense-categories/2/edit',dict(category,category_code='EDIT'),'UPDATE','EXPENSE_CATEGORY',2,'EDIT')
        event('/finance/expense-categories/2/status',{},'DEACTIVATE','EXPENSE_CATEGORY',2,'EDIT')
        event('/finance/expense-categories/2/status',{},'ACTIVATE','EXPENSE_CATEGORY',2,'EDIT')
        before=len(rows())
        # No-op category status and deleted category updates cannot log success.
        assert not erp.set_expense_category_active_status(2,True)
        assert len(rows())==before
        budget=dict(department_id='1',budget_year='2026',budget_amount='100.00',notes='private-notes')
        row=event('/finance/budgets/add',budget,'CREATE','DEPARTMENT_BUDGET',1,'DPT');assert '2026' in row[6]
        row=event('/finance/budgets/1/edit',dict(budget,budget_year='2027'),'UPDATE','DEPARTMENT_BUDGET',1,'DPT');assert '2027' in row[6]
        event('/finance/budgets/1/edit',budget,'UPDATE','DEPARTMENT_BUDGET',1,'DPT')
        expense=dict(expense_date='2026-01-01',category_id='1',department_id='1',description='private-description',
                     amount='60.00',notes='private-notes',reference_number='private-reference')
        event('/finance/expenses/add',expense,'CREATE','EXPENSE',1,'EXP-000001')
        event('/finance/expenses/1/edit',dict(expense,amount='50.00'),'UPDATE','EXPENSE',1,'EXP-000001')
        event('/finance/expenses/1/cancel',{},'CANCEL','EXPENSE',1,'EXP-000001')
        before=len(rows());assert post('/finance/expenses/1/cancel').status_code==302;assert len(rows())==before
        # Existing approve/payment events retain readable entity_id and occur once.
        event('/finance/expenses/add',expense,'CREATE','EXPENSE',2,'EXP-000002')
        for action,endpoint in [('APPROVE','approve'),('MARK_PAID','paid')]:
            before=len(rows());assert post(f'/finance/expenses/2/{endpoint}').status_code==302
            row=rows()[-1];assert len(rows())==before+1
            assert row[3:6]==(action,'EXPENSE','EXP-000002') and '2' in row[6]
            assert post(f'/finance/expenses/2/{endpoint}').status_code==302;assert len(rows())==before+1
        print('PASS all nine new events, persisted actor/numeric identity/readable labels/year/privacy; existing APPROVE and MARK_PAID exactly once')

        # Simulate a vanished category after the route loaded it: writer returns False.
        with patch.object(erp,'get_expense_category_by_id',return_value=dict(category_id=999,category_code='GONE',is_active=True)):
            before=len(rows());post('/finance/expense-categories/999/status');assert len(rows())==before
        before=snapshot()
        for path,data in [('/finance/expenses/add',dict(expense,amount='NaN')),
                          ('/finance/budgets/add',budget),('/finance/budgets/1/edit',dict(budget,budget_amount='1.001')),
                          ('/finance/expense-categories/add',dict(category,category_code='EDIT')),('/finance/expenses/2/cancel',{})]:
            assert post(path,data).status_code in (200,302)
            assert snapshot()==before,path
        # A real late business write failure after the initial INSERT must not audit.
        sql("CREATE TRIGGER fail_number BEFORE UPDATE ON expenses FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic commit path failure'")
        try:
            try:post('/finance/expenses/add',expense)
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected late write failure')
        finally:sql('DROP TRIGGER fail_number')
        assert snapshot()==before
        print('PASS invalid/duplicate/stale/failed transitions and actual late transaction rollback produce no success events')

        # Real audit INSERT failure, across each of the new business write paths.
        for path,data,query,expected in [
            ('/finance/expense-categories/add',dict(category,category_code='OUTAGE'),"SELECT COUNT(*) FROM expense_categories WHERE category_code='OUTAGE'",[(1,)]),
            ('/finance/expense-categories/2/edit',dict(category,category_code='ISOLATED'),"SELECT category_code FROM expense_categories WHERE category_id=2",[('ISOLATED',)]),
            ('/finance/expense-categories/2/status',{},'SELECT is_active FROM expense_categories WHERE category_id=2',[(0,)]),
            ('/finance/expense-categories/2/status',{},'SELECT is_active FROM expense_categories WHERE category_id=2',[(1,)]),
            ('/finance/budgets/add',dict(budget,budget_year='2028'),"SELECT COUNT(*) FROM department_budgets WHERE budget_year=2028",[(1,)]),
            ('/finance/budgets/1/edit',dict(budget,budget_amount='101.00'),'SELECT budget_amount FROM department_budgets WHERE budget_id=1',[(101,)]),
        ]:
            sql("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
            count=len(rows())
            try:assert post(path,data).status_code==302
            finally:sql('DROP TRIGGER fail_audit')
            assert sql(query,fetch=True)==expected and len(rows())==count,path
        # Exercise expense CREATE/UPDATE/CANCEL with the same audit outage.
        sql("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
        count=len(rows());expense_count=sql('SELECT COUNT(*) FROM expenses',fetch=True)[0][0]
        try:assert post('/finance/expenses/add',expense).status_code==302
        finally:sql('DROP TRIGGER fail_audit')
        assert len(rows())==count and sql('SELECT COUNT(*) FROM expenses',fetch=True)[0][0]==expense_count+1
        eid=sql('SELECT MAX(expense_id) FROM expenses',fetch=True)[0][0]
        for path,data,expected_status in [(f'/finance/expenses/{eid}/edit',dict(expense,amount='49.00'),'DRAFT'),
                                          (f'/finance/expenses/{eid}/cancel',{},'CANCELLED')]:
            sql("CREATE TRIGGER fail_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit failure'")
            count=len(rows())
            try:assert post(path,data).status_code==302
            finally:sql('DROP TRIGGER fail_audit')
            assert sql('SELECT status FROM expenses WHERE expense_id=%s',(eid,),True)==[(expected_status,)]
            assert len(rows())==count
        print('PASS real audit storage failures cannot reverse committed Finance writes')

        # Concurrent repeats of cancellation: one committed transition, one event.
        post('/finance/expenses/add',expense)
        eid=sql('SELECT MAX(expense_id) FROM expenses',fetch=True)[0][0]
        barrier=threading.Barrier(2);count=len(rows())
        def cancel():
            cc=client();tt=csrf_token_for(cc);barrier.wait(5)
            return cc.post(f'/finance/expenses/{eid}/cancel',data={'csrf_token':tt}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(cancel) for _ in range(2)]
            assert [f.result(timeout=15) for f in futures]==[302,302]
        assert len(rows())==count+1 and rows()[-1][3]=='CANCEL'
        before=snapshot();viewer=client(2);vt=csrf_token_for(viewer)
        assert viewer.post('/finance/budgets/add',data=dict(budget,csrf_token=vt)).location.endswith('/dashboard')
        for extra in ({},{'csrf_token':'forged'}):
            assert c.post('/finance/expenses/add',data=dict(expense,**extra)).status_code==400
        sql('DELETE FROM role_permissions WHERE role_id=1')
        assert post('/finance/expenses/add',expense).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS concurrent duplicate cancellation, forged POST/CSRF/fresh revocation without business or audit changes')
    print('SUCCESS: Finance audit integration used disposable MySQL only')


if __name__=='__main__':
    harness.run=run
    harness.main()
