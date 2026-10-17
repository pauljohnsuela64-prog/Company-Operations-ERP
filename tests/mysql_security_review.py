"""Cross-module security regression and optional real Chrome browser verification.

Uses the existing disposable MySQL launcher. No configured company DB is accessed.
"""
import argparse
import ast
from contextlib import ExitStack
import importlib
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state
from test_csrf_security import expired_token, form_token


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur=connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_security_review')
        cur.execute('USE erp_security_review')
        files=('core','inventory','procurement','finance','budget','attendance','leave','payroll',
               'payroll_period','payroll_entries','payroll_calculation','payroll_approval',
               'it_assets','it_asset_assignment','it_asset_maintenance','help_desk','help_desk_history','audit_logs')
        for name in files:
            text=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',text).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        connection.commit()
    options['database']='erp_security_review'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as connection:
            cur=connection.cursor()
            cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            return result
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Review operator'),(2,'No permissions')")
    password_hash=generate_password_hash('review-password')
    for uid,role,name in ((1,1,'review-user'),(2,2,'denied-user')):
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES (%s,%s,%s,%s)',(uid,role,name,password_hash))
    tree=ast.parse((harness.ROOT/'app.py').read_text())
    permissions={node.args[0].value for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='permission_required'}
    for code in permissions:
        pid=sql('INSERT INTO permissions(permission_code) VALUES (%s) ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)',(code,))
        sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(pid,))
    sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES (1,'REVIEW','Review','Employee')")
    sql("INSERT INTO helpdesk_categories(category_id,category_code,category_name) VALUES (1,'REVIEW','Review')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-security-review-key',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        # Test-only read helpers are registered only on this disposable-server runner.
        from flask import jsonify,session,request
        from itsdangerous import URLSafeTimedSerializer
        def old_token():
            with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())-3601):
                token=URLSafeTimedSerializer(erp.app.secret_key,salt='wtf-csrf-token').dumps(session['csrf_token'])
            return jsonify(csrf_token=token)
        erp.app.add_url_rule('/__review/expired-token','review_expired_token',old_token)
        erp.app.add_url_rule('/__review/supplier-count','review_supplier_count',lambda:jsonify(count=sql('SELECT COUNT(*) FROM suppliers WHERE supplier_code=%s',(request.args.get('code'),),True)[0][0]))
        cases=[
            ('HR','/departments/add',dict(department_code='REVIEW',department_name='Review Department'),'departments'),
            ('Leave','/leave/types/add',dict(leave_code='REVIEW',leave_name='Review Leave',annual_entitlement='10',is_paid='1'),'leave_types'),
            ('Payroll','/payroll/periods/add',dict(period_name='Review Period',start_date='2026-12-01',end_date='2026-12-31',pay_date='2027-01-01'),'payroll_periods'),
            ('Finance','/finance/expense-categories/add',dict(category_code='REVIEW',category_name='Review Expense'),'expense_categories'),
            ('Inventory','/inventory/categories/add',dict(category_code='REVIEW',category_name='Review Inventory'),'inventory_categories'),
            ('Procurement','/procurement/suppliers/add',dict(supplier_code='REVIEW',supplier_name='Review Supplier'),'suppliers'),
            ('IT Assets','/it/assets/categories/add',dict(category_code='REVIEW',category_name='Review Assets'),'it_asset_categories'),
            ('Help Desk','/it/help-desk/add',dict(employee_id='1',category_id='1',subject='Review Ticket',description='Synthetic review ticket',priority='MEDIUM'),'helpdesk_tickets'),
            ('Administration','/admin/users/add',dict(username='review-created',password='LongTestPassword!123',confirm_password='LongTestPassword!123',role_id='2'),'users'),
        ]
        tables=sorted({case[3] for case in cases}|{'audit_logs','role_permissions','permissions','helpdesk_ticket_history'})
        def snapshot():
            with connect() as connection:
                cur=connection.cursor()
                result=[]
                for table in tables:
                    cur.execute('SELECT * FROM '+table)
                    result.append(sorted(cur.fetchall(),key=repr))
                return result
        def client(allowed):
            c=erp.app.test_client()
            with c.session_transaction() as mapping:
                stamp_session(erp.app,mapping,user_state(user_id=1 if allowed else 2,username='review-user' if allowed else 'denied-user',role_id=1 if allowed else 2,password_hash=password_hash))
            return c
        for module,path,data,table in cases:
            allowed,denied=client(True),client(False)
            response=allowed.get(path)
            assert response.status_code==200,(module,response.status_code)
            token=form_token(response)
            before=snapshot()
            for submitted in (None,'invalid',expired_token(erp.app,allowed)):
                body=dict(data)
                if submitted:body['csrf_token']=submitted
                assert allowed.post(path,data=body).status_code==400,module
                assert snapshot()==before,module
            denied_token=form_token(denied.get('/logout'))
            response=denied.post(path,data=dict(data,csrf_token=denied_token))
            assert response.status_code==302 and response.location.endswith('/dashboard'),module
            assert snapshot()==before,module
            count=sql('SELECT COUNT(*) FROM '+table,fetch=True)[0][0]
            response=allowed.post(path,data=dict(data,csrf_token=token))
            assert response.status_code==302,(module,response.status_code,response.get_data(as_text=True))
            assert sql('SELECT COUNT(*) FROM '+table,fetch=True)[0][0]==count+1,module
            print(f'PASS {module}: rendered form, valid authorized write, unauthorized denial, and no business/audit writes for missing/invalid/expired CSRF')

        chrome=Path(r'C:\Program Files\Google\Chrome\Application\chrome.exe')
        if not chrome.exists():
            print('BROWSER NOT RUN: Chrome executable unavailable; manual browser checklist remains required')
            return
        server=make_server('127.0.0.1',0,erp.app,threaded=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        try:
            with tempfile.TemporaryDirectory(prefix='erp_browser_security_') as folder:
                profile=Path(folder).resolve()
                assert profile.parent==Path(tempfile.gettempdir()).resolve()
                process=subprocess.Popen([str(chrome),'--headless=new','--no-first-run','--no-default-browser-check','--disable-background-networking',f'--user-data-dir={profile}','--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
                try:
                    active=profile/'DevToolsActivePort'
                    deadline=time.monotonic()+20
                    while not active.exists() and time.monotonic()<deadline:time.sleep(0.1)
                    if not active.exists():raise RuntimeError('Chrome remote debugging did not become available')
                    debug_port=active.read_text().splitlines()[0]
                    result=subprocess.run(['node',str(harness.ROOT/'tests/browser_security_review.cjs'),f'http://127.0.0.1:{server.server_port}',debug_port],capture_output=True,text=True,timeout=90,creationflags=flags)
                    print(result.stdout)
                    if result.returncode or 'SUCCESS: browser execution' not in result.stdout:raise RuntimeError(result.stderr or 'Browser did not complete its assertions')
                    process.wait(timeout=15)
                    assert sql("SELECT COUNT(*) FROM suppliers WHERE supplier_code LIKE 'BROWSER-%'",fetch=True)==[(3,)]
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
    print('SUCCESS: security review completed with synthetic MySQL records only')


if __name__=='__main__':
    harness.run=run
    harness.main()
