r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_payroll_policy_management_smoke.py
Requires the local Windows MySQL server binary, overridable with --mysqld.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date, datetime, timedelta
import importlib
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_business_audit import ACTIONS, SECRETS


from security_helpers import csrf_client

def run(port, data_dir):
    options = dict(host="127.0.0.1", port=port, user="root", password="", connection_timeout=3)
    server = mysql.connector.connect(**options)
    cursor = server.cursor()
    cursor.execute("SELECT @@datadir")
    assert Path(cursor.fetchone()[0]).resolve() == data_dir.resolve(), "Isolation check failed"
    schema = "erp_audit_smoke"
    cursor.execute(f"CREATE DATABASE {schema}")
    cursor.execute(f"USE {schema}")
    files = ["core", "inventory", "procurement", "finance", "budget", "attendance",
             "leave", "payroll", "payroll_period", "payroll_entries", "payroll_calculation",
             "payroll_approval", "payroll_adjustments", "audit_logs"]
    for name in files:
        sql = (ROOT / "database" / f"{name}_schema.sql").read_text()
        sql = re.sub(r"--[^\n]*", "", sql)
        for statement in sql.split(";"):
            statement = statement.strip()
            if not statement or re.match(r"(?:CREATE DATABASE|USE)\b", statement, re.I):
                continue
            assert "company_operations_erp" not in statement
            cursor.execute(statement)
    cursor.execute("INSERT INTO roles(role_id,role_name) VALUES (41,'Acting role'),(42,'Operations'),(43,'Denied role')")
    cursor.execute("INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES (7,41,'acting.user','test-only',1),(8,43,'denied.user','test-only',1),(42,42,'target.user','test-only',0)")
    cursor.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES (9,'SMOKE-9','Smoke','Employee')")
    cursor.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES (1,9,'MONTHLY',1000,'2026-01-01',7)")
    cursor.execute("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES (1,'SMOKE','Smoke')")
    cursor.execute("INSERT INTO inventory_items(item_id,item_code,item_name,unit_of_measure) VALUES (1,'SMOKE','Smoke','pcs')")
    server.commit()
    cursor.close()
    server.close()
    options["database"] = schema

    def connect():
        # Closure only contains this newly started loopback server's settings.
        return mysql.connector.connect(**options)

    def sql(statement, params=(), fetch=False):
        with connect() as connection:
            cur = connection.cursor(dictionary=True)
            cur.execute(statement, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            cur.close()
            return result

    with ExitStack() as stack:
        stack.enter_context(patch("dotenv.load_dotenv", return_value=False))
        stack.enter_context(patch.dict(os.environ, {"SECRET_KEY": "isolated-smoke-key", "ERP_ENV": "testing", "ERP_DEBUG": "false"}))
        database = importlib.import_module("database")
        stack.enter_context(patch.object(database, "get_connection", side_effect=connect))
        erp = importlib.import_module("app")
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        stack.enter_context(patch.object(erp.app.logger, "exception"))
        # All repository imports bind to the isolated factory above. No business
        # operation, identifier lookup, template, or audit writer is mocked.
        permissions = sorted({case.permission for case in ACTIONS} | {"audit_logs.view"})

        for permission in permissions:
            pid = sql("INSERT INTO permissions(permission_code) VALUES (%s) ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)", (permission,))
            sql("INSERT INTO role_permissions(role_id,permission_id) VALUES (41,%s)", (pid,))

        def client(allowed=True):
            c = csrf_client(erp.app)
            with c.session_transaction() as sess:
                from security_helpers import user_state, stamp_session
                state = user_state(user_id=7 if allowed else 8, username="acting.user" if allowed else "denied.user", role_id=41 if allowed else 43)
                stamp_session(erp.app, sess, state)
                sess.update(**SECRETS)
                # Secrets must not override the acting user's identity.
            return c

        def logs():
            return sql("SELECT * FROM audit_logs ORDER BY audit_log_id", fetch=True)

        from payroll_schema_helpers import upgrade_policy_foundation
        upgrade_policy_foundation(connect)
        import payroll_policy_repository as policies
        import payroll_policy_validation as validation
        import payroll_generation_repository as generation
        from payroll_period_repository import update_payroll_period, cancel_payroll_period

        def config(name,effective):
            value=validation.initial_policy();value.update(policy_name=name,effective_from=effective)
            for field,schema in validation.JSON_RULES.items():
                if schema['type']=='object':
                    value[field]={k:('BLOCK' if 'BLOCK' in p['enum'] else next(v for v in p['enum'] if v!='UNRESOLVED')) for k,p in schema['properties'].items()}
            return value
        def activate(name,effective):
            draft=policies.create_policy(config(name,effective),7)
            approved=policies.approve_policy(draft['policy_version_id'],1,'Synthetic company approval GEN-001',True,7)
            policies.activate_policy(approved['policy_version_id'],7,'Asia/Manila')
            return approved
        def post(year,month,**extra):
            return client().post('/payroll/periods/generate',data=dict(year=str(year),month=str(month),pay_date_a=f'{year}-{month:02}-15',pay_date_b=f'{year}-{month:02}-'+str(__import__('calendar').monthrange(year,month)[1]),action='generate',**extra))
        def records():return sql('SELECT * FROM payroll_periods ORDER BY payroll_period_id',fetch=True)
        def rejected(fn):
            before=records();audits=logs()
            try:fn()
            except ValueError:pass
            else:raise AssertionError('Expected validation failure')
            assert before==records() and audits==logs()

        rejected(lambda:generation.generate_month(2040,1,'2040-01-15','2040-01-31',7))
        draft=policies.create_policy(config('Unactivated','2039-01-01'),7)
        rejected(lambda:generation.generate_month(2040,1,'2040-01-15','2040-01-31',7))
        approved=policies.approve_policy(draft['policy_version_id'],1,'Synthetic approval GEN-002',True,7)
        rejected(lambda:generation.generate_month(2040,1,'2040-01-15','2040-01-31',7))
        policies.activate_policy(approved['policy_version_id'],7,'Asia/Manila')
        second=activate('Midmonth replacement','2040-01-16')
        preview=generation.generate_month(2040,1,preview=True)
        assert [r['policy_version_id'] for r in preview]==[approved['policy_version_id'],second['policy_version_id']]
        assert not records() and not logs()
        response=post(2040,1);assert response.status_code==200 and 'Created' in response.text
        first=records();assert len(first)==2 and all(r['status']=='DRAFT' for r in first)
        assert len(logs())==2 and all(r['user_id']==7 and r['action']=='CREATE' and r['entity_type']=='PAYROLL_PERIOD' for r in logs())
        assert 'policy version' in logs()[0]['description']
        assert 'already exist' in post(2040,1).text and len(logs())==2
        rejected(lambda:generation.generate_month(2040,1,'2040-01-16','2040-01-31',7))
        rejected(lambda:update_payroll_period(first[0]['payroll_period_id'],'Pinned changed','2040-01-02','2040-01-15','2040-01-15','',7))
        assert cancel_payroll_period(first[0]['payroll_period_id'],7)
        assert 'Created' in post(2040,1).text and len(logs())==3
        assert sql('SELECT COUNT(*) n FROM payroll_entries',fetch=True)[0]['n']==0
        for year,month in [(2040,2),(2041,2),(2040,4),(2040,12),(2041,1)]:
            result=generation.generate_month(year,month,f'{year}-{month:02}-15',f'{year}-{month:02}-'+str(__import__('calendar').monthrange(year,month)[1]),7)
            assert all(row['created'] for row in result)
        rejected(lambda:generation.generate_month(2042,1,'2042-01-14','2042-01-31',7))
        # Legacy NULL overlaps conflict, never become silently pinned.
        from payroll_period_repository import create_payroll_period
        legacy=create_payroll_period('Legacy overlap',date(2042,2,1),date(2042,2,15),date(2042,2,15),'',7)
        rejected(lambda:generation.generate_month(2042,2,'2042-02-15','2042-02-28',7))
        assert sql('SELECT policy_version_id FROM payroll_periods WHERE payroll_period_id=%s',(legacy,),True)[0]['policy_version_id'] is None
        # B conflicts must not leave a newly inserted A.
        create_payroll_period('B overlap',date(2042,3,16),date(2042,3,31),date(2042,3,31),'',7)
        rejected(lambda:generation.generate_month(2042,3,'2042-03-15','2042-03-31',7))
        print('PASS calendar boundaries, midmonth policy selection, explicit dates, pinning, idempotency, legacy overlap and cancel/recreate')
        # Actual late SQL failure after A insert rolls back both.
        before=records();before_logs=logs()
        sql("CREATE TRIGGER reject_second_cutoff BEFORE INSERT ON payroll_periods FOR EACH ROW BEGIN IF NEW.cutoff_code='B' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic B failure'; END IF; END")
        try:
            response=post(2043,1);assert 'Unable to generate' in response.text
        finally:sql('DROP TRIGGER reject_second_cutoff')
        assert records()==before and logs()==before_logs
        sql("CREATE TRIGGER reject_generation_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit outage'")
        before=len(logs())
        try:assert 'Created' in post(2043,1).text
        finally:sql('DROP TRIGGER reject_generation_audit')
        assert len(logs())==before and len([r for r in records() if r['start_date'].year==2043])==2
        # Two actual competing requests wait on the same guard before either writes.
        held=connect();held.start_transaction();hc=held.cursor();hc.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');hc.fetchall()
        def worker():return post(2044,1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker) for _ in range(2)]
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    waits=sql('SELECT COUNT(*) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']
                    if waits>=2:break
                    time.sleep(.05)
                else:raise AssertionError('Did not observe both InnoDB waiters')
            finally:held.commit();hc.close();held.close()
            results=[f.result(timeout=15) for f in futures]
        assert sum('Already exists' in r.text for r in results)==1
        assert len([r for r in records() if r['start_date'].year==2044])==2
        assert len(logs())==before+2
        print('PASS observed concurrent duplicate requests commit exactly two periods and two audits; late rollback and audit outage isolation')
        # Activation versus generation shares the guard: whichever commits first determines the result.
        def race(first,second):
            held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
            def attempt(fn):
                try:return fn()
                except ValueError:return 'rejected'
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(attempt,fn) for fn in (first,second)]
                    try:
                        deadline=time.monotonic()+10
                        while sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']<2:
                            assert time.monotonic()<deadline;time.sleep(.05)
                    finally:held.commit()
                    return [f.result(timeout=15) for f in futures]
            finally:cur.close();held.close()
        candidate=policies.create_policy(config('Concurrent activation','2046-01-16'),7)
        candidate=policies.approve_policy(candidate['policy_version_id'],1,'Synthetic GEN-003',True,7)
        result=race(lambda:generation.generate_month(2046,1,'2046-01-15','2046-01-31',7),
                    lambda:policies.activate_policy(candidate['policy_version_id'],7,'Asia/Manila'))
        generated=result[0];assert isinstance(generated,list)
        assert generated[0]['policy_version_id']==second['policy_version_id']
        assert generated[1]['policy_version_id']==(second['policy_version_id'] if result[1]=='rejected' else candidate['policy_version_id'])
        # Manual creation cannot bypass global overlap while generation is competing.
        result=race(lambda:generation.generate_month(2047,1,'2047-01-15','2047-01-31',7),
                    lambda:create_payroll_period('Concurrent manual',date(2047,1,1),date(2047,1,15),date(2047,1,15),'',7))
        assert result.count('rejected')==1
        relevant=[r for r in records() if r['start_date'].year==2047]
        assert len(relevant)==(1 if result[0]=='rejected' else 2)
        # An actual lock timeout must preserve entered values and leave no writes/audits.
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        def short_connection():
            connection=connect();c=connection.cursor();c.execute('SET SESSION innodb_lock_wait_timeout=1');c.close();return connection
        before=records();before_logs=logs()
        try:
            with patch.object(generation,'get_connection',side_effect=short_connection):
                response=post(2048,1)
                assert 'retry' in response.text and 'value="2048"' in response.text
        finally:held.rollback();cur.close();held.close()
        assert records()==before and logs()==before_logs
        # Force a real InnoDB cycle with an intentionally reversed synthetic writer.
        # Application writers never use this reverse lock order.
        before=records();before_logs=logs()
        held=connect();held.start_transaction();cur=held.cursor()
        cur.execute("UPDATE payroll_periods SET notes='Synthetic uncommitted deadlock fixture'")
        assert cur.rowcount>10
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(lambda:post(2044,1))
            try:
                deadline=time.monotonic()+10
                while not sql('SELECT COUNT(*) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']:
                    assert time.monotonic()<deadline;time.sleep(.05)
                try:
                    cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
                    root_victim=False
                except mysql.connector.Error as error:
                    assert error.errno==1213;root_victim=True
            finally:held.rollback();cur.close();held.close()
            response=future.result(timeout=15)
        if not root_victim:assert 'retry' in response.text
        assert records()==before and logs()==before_logs
        print('PASS actual InnoDB deadlock rollback with unchanged periods/audits')
        # Read-only user keeps views but cannot see or invoke generation.
        pid=sql("INSERT INTO permissions(permission_code) VALUES('payroll.view') ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)")
        sql('INSERT IGNORE INTO role_permissions VALUES(43,%s)',(pid,))
        viewer=client(False)
        assert 'Generate Monthly Cutoffs' not in viewer.get('/payroll/periods').text
        assert viewer.get('/payroll/periods/generate').status_code==302
        invalid=client().post('/payroll/periods/generate',data=dict(year='2048',month='2',pay_date_a='2048-02-14',pay_date_b='2048-02-29',action='generate'))
        assert 'value="2048-02-14"' in invalid.text and records()==before
        print('PASS activation/generation and manual/generation InnoDB races, real guard timeout, viewer controls and retained invalid values')
        # Security: no business writes for forged/read-only, CSRF, revocation or disabled accounts.
        before=records();before_logs=logs()
        from werkzeug.datastructures import MultiDict
        forged=client().post('/payroll/periods/generate',data=MultiDict([('year','2045'),('year','2046'),('month','1'),('action','generate')]))
        assert 'unsupported or repeated fields' in forged.text
        forged=client().post('/payroll/periods/generate',data=dict(year='2045',month='1',action='generate',policy_version_id='999'))
        assert 'unsupported or repeated fields' in forged.text
        assert client(False).post('/payroll/periods/generate',data={}).status_code==302
        assert erp.app.test_client().post('/payroll/periods/generate',data={}).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=41 AND permission_code='payroll.process'")
        assert post(2045,1).status_code==302
        sql('UPDATE users SET is_active=0 WHERE user_id=7')
        assert post(2045,1).location.endswith('/login')
        assert before==records() and before_logs==logs()
        print('PASS fresh authorization, disabled accounts, forged POST and CSRF with no success events')
    print('SUCCESS: generation checked only in disposable synthetic MySQL with migrations 004/005')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
