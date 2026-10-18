"""Draft period-date invalidation, real races and rollback on disposable MySQL."""

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
        from decimal import Decimal
        import payroll_period_repository as periods
        import payroll_workflow_repository as workflow
        import payroll_adjustment_repository as adjustments
        counter=0
        def fixture():
            nonlocal counter
            counter+=1;start=date(2026,2,2)+timedelta(days=35*counter);end=start+timedelta(days=4)
            period=erp.create_payroll_period(f'Date edit {counter}',start,end,end+timedelta(days=1),None,7)
            erp.generate_payroll_entries(period,7)
            for i in range(5):
                sql('INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,%s,7)',(start+timedelta(days=i),'ABSENT' if i==0 else 'PRESENT'))
            erp.calculate_monthly_payroll_period(period,7)
            eid=sql('SELECT payroll_entry_id FROM payroll_entries WHERE payroll_period_id=%s',(period,),True)[0]['payroll_entry_id']
            return period,eid,start,end
        def entry(eid):return sql('SELECT * FROM payroll_entries WHERE payroll_entry_id=%s',(eid,),True)[0]
        def edit(f,changed=True):
            p,eid,s,e=f
            return periods.update_payroll_period(p,'Edited '+str(p),s,s if changed else e,e+timedelta(days=2),'Synthetic notes',7)
        def snapshot():return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ['payroll_periods','payroll_entries','payroll_adjustments','employee_compensation','audit_logs']]
        f=fixture();p,eid,s,e=f
        adjustments.add_payroll_adjustment(eid,'EARNING','Retained',Decimal('10'),None,7)
        assert entry(eid)['net_pay']==Decimal('410')
        before_adjustments=sql('SELECT * FROM payroll_adjustments',fetch=True)
        assert edit(f)
        row=entry(eid);assert row['status']=='DRAFT' and row['calculated_at'] is None and row['calculated_by'] is None
        assert all(row[key]==0 for key in ['scheduled_work_days','present_days','absent_days','daily_rate','regular_pay','additional_earnings','attendance_deduction','total_deductions','net_pay'])
        assert row['basic_rate']==Decimal('1000') and sql('SELECT * FROM payroll_adjustments',fetch=True)==before_adjustments
        before=len(logs())
        response=client().post(f'/payroll/periods/{p}/submit',data={})
        assert response.status_code==302 and len(logs())==before
        assert erp.get_payroll_period_by_id(p)['status']=='DRAFT'
        erp.calculate_monthly_payroll_period(p,7)
        assert entry(eid)['status']=='CALCULATED' and entry(eid)['scheduled_work_days']==1 and entry(eid)['net_pay']==Decimal('10')
        erp.submit_payroll_for_approval(p,7);erp.approve_payroll_period(p,7);erp.mark_payroll_period_as_paid(p,7)
        assert entry(eid)['status']=='PAID' and entry(eid)['net_pay']==Decimal('10')
        print('PASS date edit atomically clears cached values, blocks stale submission/audit, preserves rate/adjustments and permits explicit recalculation with unchanged formula/workflow')
        f=fixture();before=entry(f[1]);assert edit(f,False);assert entry(f[1])==before
        print('PASS metadata/pay-date-only edits preserve calculation evidence and amounts')
        for status in ['PROCESSING','APPROVED','PAID','CANCELLED']:
            f=fixture();sql('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s',(status,f[0]))
            if status in ['APPROVED','PAID']:sql('UPDATE payroll_entries SET status=%s WHERE payroll_entry_id=%s',(status,f[1]))
            before=snapshot();assert not edit(f);assert snapshot()==before
        for status in ['APPROVED','PAID']:
            f=fixture();sql('UPDATE payroll_entries SET status=%s WHERE payroll_entry_id=%s',(status,f[1]))
            before=snapshot()
            try:edit(f)
            except ValueError:pass
            else:raise AssertionError('Finalized child unexpectedly invalidated')
            assert snapshot()==before
        print('PASS submitted/approved/paid/cancelled periods and finalized children in inconsistent drafts remain unchanged')
        f=fixture();before=snapshot()
        sql("CREATE TRIGGER reject_invalidation BEFORE UPDATE ON payroll_entries FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic invalidation rollback'")
        try:
            try:edit(f)
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected late failure')
        finally:sql('DROP TRIGGER reject_invalidation')
        assert snapshot()==before
        print('PASS actual late SQL failure rolls back period dates and entry invalidation together')
        for other in ['submit','calculate']:
            f=fixture();held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT payroll_period_id FROM payroll_periods WHERE payroll_period_id=%s FOR UPDATE',(f[0],));cur.fetchall()
            def operation():
                try:return erp.submit_payroll_for_approval(f[0],7) if other=='submit' else erp.calculate_monthly_payroll_period(f[0],7)
                except ValueError:return 'rejected'
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(edit,f),pool.submit(operation)]
                    try:
                        deadline=time.monotonic()+8
                        while sql("SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<2:
                            assert time.monotonic()<deadline,'Both real writers must wait';time.sleep(0.05)
                    finally:held.commit()
                    results=[future.result(timeout=12) for future in futures]
            finally:held.close()
            period=erp.get_payroll_period_by_id(f[0]);row=entry(f[1])
            if period['status']=='PROCESSING':assert period['end_date']==f[3] and row['net_pay']==Decimal('400') and results[0] is False
            elif row['status']=='DRAFT':assert period['end_date']==f[2] and row['calculated_at'] is None and row['net_pay']==0
            else:assert other=='calculate' and period['end_date']==f[2] and row['scheduled_work_days']==1 and row['net_pay']==0
        print('PASS two actual two-waiter date-edit/submit and date-edit/calculation races preserve matching dates/state/calculations')
        f=fixture();values=dict(period_name='Route edit',start_date=f[2].isoformat(),end_date=f[2].isoformat(),pay_date=(f[3]+timedelta(days=1)).isoformat(),notes='Synthetic')
        before=snapshot()
        assert client(False).post(f'/payroll/periods/{f[0]}/edit',data=values).location.endswith('/dashboard')
        assert erp.app.test_client().post(f'/payroll/periods/{f[0]}/edit',data=values).status_code==400
        assert snapshot()==before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=41 AND permission_code='payroll.process'")
        assert client().post(f'/payroll/periods/{f[0]}/edit',data=values).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS actual CSRF, permission denial and committed revocation prevent edits without audit/business changes')
    print('SUCCESS: draft-date safeguard tested only on disposable MySQL; versioned freshness is covered by its separate suite')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
