"""Finance validation and uniqueness using disposable MySQL and synthetic data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as c:
        cur = c.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_finance_validation')
        cur.execute('USE erp_finance_validation')
        for name in ['core','inventory','procurement','finance','budget','audit_logs']:
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I): cur.execute(statement)
        c.commit()
    options['database'] = 'erp_finance_validation'
    # Deliberately non-strict: validators must prevent MySQL silent coercion.
    def connect():
        c = mysql.connector.connect(**options)
        cur = c.cursor(); cur.execute("SET SESSION sql_mode = ''"); cur.close()
        return c
    def sql(query, params=(), fetch=False):
        with connect() as c:
            cur=c.cursor(); cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            c.commit(); return result
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Finance Test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'finance-test','synthetic')")
    sql("INSERT INTO permissions(permission_code) VALUES ('finance.expenses.manage'),('finance.view')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES (1,'A','Active',1),(2,'B','Inactive',0)")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name,is_active) VALUES (1,'A','Active',1),(2,'B','Inactive',0)")
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name,is_active) VALUES (1,'A','Active',1),(2,'B','Inactive',0)")
    sql("INSERT INTO purchase_orders(purchase_order_id,po_number,supplier_id,created_by,status) VALUES (1,'A',1,1,'SENT'),(2,'B',1,1,'CANCELLED')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-finance-validation',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app')
        expenses=importlib.import_module('expense_repository')
        budgets=importlib.import_module('budget_repository')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client():
            c=erp.app.test_client()
            with c.session_transaction() as sess:
                stamp_session(erp.app,sess,user_state(user_id=1,role_id=1,username='finance-test',password_hash='synthetic'))
            return c
        c=client()
        token=csrf_token_for(c)
        def post(path, fields): return c.post(path,data=dict(fields,csrf_token=token))
        def snapshot():
            return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ['expenses','department_budgets','audit_logs']]
        def rejected(path,fields):
            before=snapshot()
            response=post(path,fields)
            assert response.status_code==200,(path,response.status_code)
            assert 'alert-danger' in response.get_data(as_text=True)
            assert snapshot()==before
        expense=dict(expense_date='2026-01-01',category_id='1',department_id='1',supplier_id='1',
                     purchase_order_id='1',description='Synthetic',amount='1.00')
        budget=dict(department_id='1',budget_year='2026',budget_amount='1.00')
        assert post('/finance/expenses/add',expense).status_code==302
        eid=sql('SELECT expense_id FROM expenses',fetch=True)[0][0]
        assert post('/finance/budgets/add',budget).status_code==302
        bid=sql('SELECT budget_id FROM department_budgets',fetch=True)[0][0]
        for key,values in {
            'amount':['NaN','sNaN','Infinity','-Infinity','0','-1','0.001','1.000','10000000000','1,2'],
            'expense_date':['2026-02-30','0000-00-00','0001-01-01','bad','20260101'],
            'category_id':['0','-1','2','999','2147483648','x'],
            'department_id':['2','999','-1'], 'supplier_id':['2','999','x'], 'purchase_order_id':['2','999','x'],
            'description':['','x'*256], 'reference_number':['x'*101], 'notes':['x'*256], 'payment_method':['WIRE']
        }.items():
            for value in values:
                fields=dict(expense,**{key:value})
                for path in ['/finance/expenses/add',f'/finance/expenses/{eid}/edit']: rejected(path,fields)
        for key,values in {'budget_amount':['NaN','Infinity','0','-1','1.001','1.000','1000000000000'],
                           'budget_year':['0','-1','999','10000','2026.0','NaN'],
                           'department_id':['0','999','x','2147483648'], 'notes':['x'*256]}.items():
            for value in values:
                fields=dict(budget,**{key:value})
                for path in ['/finance/budgets/add',f'/finance/budgets/{bid}/edit']: rejected(path,fields)
        print('PASS malformed/nonfinite/negative/zero/precision/overflow/date/id/text/reference forms: no business or audit changes even with non-strict SQL')

        max_expense=dict(expense,amount='9999999999.99',description='x'*255,reference_number='r'*100,notes='n'*255)
        assert post(f'/finance/expenses/{eid}/edit',max_expense).status_code==302
        assert sql('SELECT amount FROM expenses WHERE expense_id=%s',(eid,),True)==[(Decimal('9999999999.99'),)]
        assert post(f'/finance/budgets/{bid}/edit',dict(budget,budget_amount='999999999999.99')).status_code==302
        assert sql('SELECT budget_amount FROM department_budgets WHERE budget_id=%s',(bid,),True)==[(Decimal('999999999999.99'),)]
        # Existing policy permits historical/inactive department budgets and reductions.
        assert post('/finance/budgets/add',dict(budget,department_id='2')).status_code==302
        assert post(f'/finance/budgets/{bid}/edit',dict(budget,budget_amount='0.01')).status_code==302
        rejected('/finance/budgets/add',budget)
        other=sql('SELECT budget_id FROM department_budgets WHERE department_id=2',fetch=True)[0][0]
        rejected(f'/finance/budgets/{other}/edit',budget)

        barrier=threading.Barrier(2)
        def create():
            barrier.wait(5)
            try: return budgets.create_department_budget(1,2027,Decimal('1.00'),None,1)
            except ValueError as error: return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(create) for _ in range(2)]
            results=[f.result(timeout=15) for f in futures]
        assert sum(isinstance(r,int) for r in results)==1,results
        assert any('already has a budget' in str(r) for r in results)
        assert sql('SELECT COUNT(*) FROM department_budgets WHERE department_id=1 AND budget_year=2027',fetch=True)==[(1,)]
        edit_ids=[budgets.create_department_budget(1,y,Decimal('1'),None,1) for y in (2029,2030)]
        barrier=threading.Barrier(2)
        def collide(budget_id):
            barrier.wait(5)
            try:
                budgets.update_department_budget(budget_id,1,2028,Decimal('1'),None)
                return True
            except ValueError: return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(collide,b) for b in edit_ids]
            assert sum(f.result(timeout=15) for f in futures)==1
        assert sql('SELECT COUNT(*) FROM department_budgets WHERE department_id=1 AND budget_year=2028',fetch=True)==[(1,)]
        print('PASS exact schema maxima, inactive historical budget compatibility, reductions and concurrent duplicate creation')

        before=snapshot()
        sql("CREATE TRIGGER fail_expense_number BEFORE UPDATE ON expenses FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic rollback test'")
        try:
            try: expenses.create_expense('2026-01-01',1,None,None,None,'Rollback',Decimal('1'),None,None,1,None)
            except mysql.connector.Error: pass
            else: raise AssertionError('Expected second-stage expense write failure')
        finally: sql('DROP TRIGGER fail_expense_number')
        assert snapshot()==before
        print('PASS actual INSERT followed by UPDATE failure rolls back the entire expense creation')

        # A deactivation holding the master row wins before the writer's validation.
        master=connect(); master.start_transaction()
        cur=master.cursor();cur.execute('UPDATE suppliers SET is_active=0 WHERE supplier_id=1')
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(lambda: expenses.create_expense('2026-01-01',1,1,1,1,'Race',Decimal('1'),None,None,1,None))
            master.commit();master.close()
            try: future.result(timeout=15)
            except ValueError as error: assert 'supplier' in str(error)
            else: raise AssertionError('Inactive supplier accepted')
        before=snapshot()
        for path in ['/finance/expenses/add',f'/finance/expenses/{eid}/edit','/finance/budgets/add',f'/finance/budgets/{bid}/edit']:
            assert c.post(path,data={}).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE p.permission_code='finance.expenses.manage'")
        assert post('/finance/budgets/add',dict(budget,budget_year='2028')).location.endswith('/dashboard')
        assert post(f'/finance/expenses/{eid}/edit',expense).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS transaction-time reference checks, CSRF and same-session committed permission revocation')
    print('SUCCESS: Finance validation tested only on disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
