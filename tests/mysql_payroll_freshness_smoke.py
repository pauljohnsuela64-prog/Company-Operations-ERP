r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_audit_smoke.py
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

        from decimal import Decimal
        from importlib import util as import_util
        import payroll_freshness as freshness
        import payroll_workflow_repository as workflow
        import payroll_period_repository as periods
        import attendance_repository as attendance
        import payroll_repository as compensation
        import leave_repository as leave
        # Upgrade a deliberately old synthetic schema; never mark old values verified.
        sql('ALTER TABLE payroll_entries DROP COLUMN calculation_input_version, DROP COLUMN calculation_input_hash')
        sql('DROP TABLE payroll_input_guard')
        legacy=sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES('LEGACY','Legacy','2026-01-01','2026-01-01','2026-01-02','APPROVED',7)")
        sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,regular_pay,gross_pay,net_pay,status,generated_by,calculated_at) VALUES(%s,9,1,'MONTHLY',1000,500,500,500,'APPROVED',7,NOW())",(legacy,))
        legacy_paid=sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES('LEGACY-PAID','Legacy paid','2025-12-01','2025-12-01','2025-12-02','PAID',7)")
        sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,regular_pay,gross_pay,net_pay,status,generated_by,calculated_at) VALUES(%s,9,1,'MONTHLY',1000,500,500,500,'PAID',7,NOW())",(legacy_paid,))
        before=sql('SELECT * FROM payroll_entries',fetch=True)
        spec=import_util.spec_from_file_location('upgrade_payroll',ROOT/'database/migrations/004_payroll_freshness.py');migration=import_util.module_from_spec(spec);spec.loader.exec_module(migration)
        for _ in range(2):
            with connect() as connection:migration.upgrade(connection)
        after=sql('SELECT * FROM payroll_entries',fetch=True)
        assert all(r['calculation_input_hash'] is None and r['calculation_input_version'] is None for r in after)
        assert [{k:v for k,v in r.items() if k not in ['calculation_input_hash','calculation_input_version']} for r in after]==before
        sql('ALTER TABLE payroll_entries DROP COLUMN calculation_input_hash')
        with connect() as connection:migration.upgrade(connection)
        sql('ALTER TABLE payroll_entries MODIFY calculation_input_hash CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL')
        try:
            with connect() as connection:migration.upgrade(connection)
        except RuntimeError:pass
        else:raise AssertionError('Incompatible column accepted')
        sql('ALTER TABLE payroll_entries MODIFY calculation_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL')
        with connect() as connection:migration.upgrade(connection)
        sql('ALTER TABLE payroll_input_guard ENGINE=MyISAM')
        try:
            with connect() as connection:migration.upgrade(connection)
        except RuntimeError:pass
        else:raise AssertionError('Nontransactional guard accepted')
        sql('ALTER TABLE payroll_input_guard ENGINE=InnoDB')
        with connect() as connection:migration.upgrade(connection)
        from payroll_schema_helpers import upgrade_policy_foundation
        upgrade_policy_foundation(connect)
        assert sql('SELECT status,net_pay FROM payroll_entries WHERE payroll_period_id=%s',(legacy_paid,),True)==[dict(status='PAID',net_pay=Decimal('500'))]
        before_audit=len(logs());assert client().post(f'/payroll/periods/{legacy}/paid',data={}).status_code==302
        assert len(logs())==before_audit and erp.get_payroll_period_by_id(legacy)['status']=='APPROVED'
        print('PASS repeatable/interrupted migration, incompatible definition rejection, untouched legacy NULL evidence and blocked legacy APPROVED payment')
        counter=0
        def fixture(stage='DRAFT',on_leave=False):
            nonlocal counter
            counter+=1;start=date(2026,2,2)+timedelta(days=35*counter);end=start+timedelta(days=4)
            compensation.update_employee_compensation(1,'MONTHLY',Decimal('1000'),'2026-01-01',None,7)
            p=erp.create_payroll_period('Freshness '+str(counter),start,end,end+timedelta(days=1),None,7)
            erp.generate_payroll_entries(p,7)
            for i in range(5):
                sql('INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,%s,7)',(start+timedelta(days=i),'ON_LEAVE' if on_leave and i==0 else 'PRESENT'))
            if on_leave:sql("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(%s,9,1,%s,%s,1,'Synthetic','APPROVED',7)",('FRESH-'+str(counter),start,start))
            erp.calculate_monthly_payroll_period(p,7)
            if stage in ['PROCESSING','APPROVED']:erp.submit_payroll_for_approval(p,7)
            if stage=='APPROVED':erp.approve_payroll_period(p,7)
            eid=sql('SELECT payroll_entry_id FROM payroll_entries WHERE payroll_period_id=%s',(p,),True)[0]['payroll_entry_id']
            aid=sql('SELECT attendance_id FROM attendance_records WHERE employee_id=9 AND attendance_date=%s',(start,),True)[0]['attendance_id']
            return dict(p=p,eid=eid,aid=aid,start=start,end=end)
        def changed(f,status='ABSENT'):
            return attendance.update_attendance_record(f['aid'],9,f['start'],None,None,status,None,7)
        def row(f):return sql('SELECT * FROM payroll_entries WHERE payroll_entry_id=%s',(f['eid'],),True)[0]
        def action(f,stage):return client().post(f"/payroll/periods/{f['p']}/"+{'DRAFT':'submit','PROCESSING':'approve','APPROVED':'paid'}[stage],data={})
        def rejected(f,stage):
            before=row(f);audit=len(logs());assert action(f,stage).status_code==302
            assert row(f)==before and len(logs())==audit and erp.get_payroll_period_by_id(f['p'])['status']==stage
        for stage in ['DRAFT','PROCESSING','APPROVED']:
            f=fixture(stage);stamp=row(f)['calculated_at'];changed(f)
            sql('UPDATE attendance_records SET updated_at=%s WHERE attendance_id=%s',(stamp,f['aid']))
            rejected(f,stage)
        print('PASS same-second attendance changes reject submission, approval and payment with no successful audits or record rewrites')
        for kind in ['delete','move','leave_policy','leave_request','adjustment','snapshot','result']:
            f=fixture(on_leave=kind.startswith('leave_'))
            if kind=='delete':sql('DELETE FROM attendance_records WHERE attendance_id=%s',(f['aid'],))
            if kind=='move':sql('UPDATE attendance_records SET attendance_date=DATE_ADD(attendance_date,INTERVAL 7 DAY) WHERE attendance_id=%s',(f['aid'],))
            if kind=='leave_policy':leave.update_leave_type(1,'VL','Vacation Leave','Synthetic',5,0)
            if kind=='leave_request':sql("UPDATE leave_requests SET status='CANCELLED' WHERE request_number=%s",('FRESH-'+str(counter),))
            if kind=='adjustment':erp.add_payroll_adjustment(f['eid'],'EARNING','Synthetic',Decimal('10'),None,7)
            if kind=='snapshot':sql('UPDATE payroll_entries SET basic_rate=2000 WHERE payroll_entry_id=%s',(f['eid'],))
            if kind=='result':sql('UPDATE payroll_entries SET net_pay=1 WHERE payroll_entry_id=%s',(f['eid'],))
            rejected(f,'DRAFT')
            if kind=='leave_policy':leave.update_leave_type(1,'VL','Vacation Leave','Synthetic',5,1)
        print('PASS removal/date moves, leave policy/request changes, adjustments, entry snapshot changes and modified cached outputs invalidate evidence')
        f=fixture();before=row(f)
        compensation.update_employee_compensation(1,'MONTHLY',Decimal('2000'),'2026-01-01',None,7)
        # Nonmaterial notes/timestamps do not invalidate current monthly inputs.
        sql("UPDATE attendance_records SET notes='Only notes' WHERE attendance_id=%s",(f['aid'],))
        for stage in ['DRAFT','PROCESSING','APPROVED']:assert action(f,stage).status_code==302
        assert row(f)['status']=='PAID' and row(f)['basic_rate']==before['basic_rate'] and row(f)['net_pay']==before['net_pay']
        print('PASS unchanged legitimate workflow, intentional compensation snapshot, nonmaterial notes, and postcommit workflow audits')
        # Prove validation holds the shared guard until transition commit.
        for stage in ['DRAFT','PROCESSING','APPROVED']:
            f=fixture(stage);verified=threading.Event();release=threading.Event();original=workflow.verify_calculations
            def paused(*args,**kwargs):
                original(*args,**kwargs);verified.set();assert release.wait(10)
            before=len(logs())
            with patch.object(workflow,'verify_calculations',side_effect=paused),ThreadPoolExecutor(2) as pool:
                transition=pool.submit(action,f,stage);assert verified.wait(10)
                writer=pool.submit(changed,f)
                try:
                    deadline=time.monotonic()+8
                    while sql("SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<1:
                        assert time.monotonic()<deadline;time.sleep(0.05)
                    assert not writer.done()
                finally:release.set()
                assert transition.result(timeout=12).status_code==302;writer.result(timeout=12)
            assert len(logs())==before+1
            if stage=='DRAFT':rejected(f,'PROCESSING')
            elif stage=='PROCESSING':rejected(f,'APPROVED')
            else:assert row(f)['status']=='PAID' and row(f)['net_pay']==Decimal('500')
        print('PASS three real guard waits: Attendance cannot commit between final validation and submit/approve/pay; later edits cannot rewrite PAID history')
        # HR wins first: use the real attendance repository, paused immediately before commit.
        class PausedConnection:
            def __init__(self):self.inner=connect()
            def __getattr__(self,name):return getattr(self.inner,name)
            def commit(self):written.set();assert release.wait(10);self.inner.commit()
        for stage in ['DRAFT','PROCESSING','APPROVED']:
            f=fixture(stage);written=threading.Event();release=threading.Event();before=len(logs())
            with patch.object(attendance,'get_connection',side_effect=PausedConnection),ThreadPoolExecutor(2) as pool:
                writer=pool.submit(changed,f);assert written.wait(10)
                transition=pool.submit(action,f,stage)
                try:
                    deadline=time.monotonic()+8
                    while sql("SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<1:
                        assert time.monotonic()<deadline;time.sleep(0.05)
                    assert not transition.done()
                finally:release.set()
                writer.result(timeout=12);assert transition.result(timeout=12).status_code==302
            assert len(logs())==before and erp.get_payroll_period_by_id(f['p'])['status']==stage
        print('PASS three real guard waits with HR first: every finalization stage re-reads committed inputs and rejects stale payroll')
        # Real leave-type policy writes obey the same first-lock protocol.
        f=fixture('PROCESSING',on_leave=True);verified=threading.Event();release=threading.Event();original=workflow.verify_calculations
        def paused_leave(*args,**kwargs):
            original(*args,**kwargs);verified.set();assert release.wait(10)
        with patch.object(workflow,'verify_calculations',side_effect=paused_leave),ThreadPoolExecutor(2) as pool:
            transition=pool.submit(action,f,'PROCESSING');assert verified.wait(10)
            writer=pool.submit(leave.update_leave_type,1,'VL','Vacation Leave','Synthetic',5,0)
            try:
                deadline=time.monotonic()+8
                while sql("SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<1:
                    assert time.monotonic()<deadline;time.sleep(0.05)
                assert not writer.done()
            finally:release.set()
            assert transition.result(timeout=12).status_code==302;writer.result(timeout=12)
        rejected(f,'APPROVED');leave.update_leave_type(1,'VL','Vacation Leave','Synthetic',5,1)
        f=fixture('APPROVED',on_leave=True);written=threading.Event();release=threading.Event();before=len(logs())
        with patch.object(leave,'get_connection',side_effect=PausedConnection),ThreadPoolExecutor(2) as pool:
            writer=pool.submit(leave.update_leave_type,1,'VL','Vacation Leave','Synthetic',5,0);assert written.wait(10)
            transition=pool.submit(action,f,'APPROVED')
            try:
                deadline=time.monotonic()+8
                while sql("SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<1:
                    assert time.monotonic()<deadline;time.sleep(0.05)
            finally:release.set()
            writer.result(timeout=12);assert transition.result(timeout=12).status_code==302
        assert len(logs())==before and erp.get_payroll_period_by_id(f['p'])['status']=='APPROVED'
        leave.update_leave_type(1,'VL','Vacation Leave','Synthetic',5,1)
        print('PASS two real Leave policy/approval/payment guard waits in both winning orders')
        # Failure after a calculation UPDATE must roll back its evidence and amounts.
        f=fixture();before=row(f);changed(f)
        sql("CREATE TRIGGER reject_fingerprint BEFORE UPDATE ON payroll_entries FOR EACH ROW BEGIN IF NEW.calculation_input_hash<>OLD.calculation_input_hash THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic fingerprint failure'; END IF; END")
        try:
            try:erp.calculate_monthly_payroll_period(f['p'],7)
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected evidence failure')
        finally:sql('DROP TRIGGER reject_fingerprint')
        assert row(f)==before
        erp.calculate_monthly_payroll_period(f['p'],7);assert action(f,'DRAFT').status_code==302
        print('PASS late fingerprint failure rolls back amounts/evidence and releases coordination for explicit successful recalculation')
        # Legacy DRAFT/PROCESSING remain unverified, never implicitly attested.
        for stage in ['DRAFT','PROCESSING']:
            f=fixture(stage);sql('UPDATE payroll_entries SET calculation_input_version=NULL,calculation_input_hash=NULL WHERE payroll_entry_id=%s',(f['eid'],))
            rejected(f,stage)
            if stage=='PROCESSING':erp.return_payroll_to_draft(f['p'],7)
            erp.calculate_monthly_payroll_period(f['p'],7);assert action(f,'DRAFT').status_code==302
        print('PASS legacy DRAFT recalculation and existing PROCESSING return/recalculate recovery; no historical backfill')
        for protected in ['APPROVED','PAID']:
            f=fixture();sql('UPDATE payroll_entries SET status=%s WHERE payroll_entry_id=%s',(protected,f['eid']))
            before=row(f);audit=len(logs())
            for operation in [lambda:erp.calculate_monthly_payroll_period(f['p'],7),lambda:erp.add_payroll_adjustment(f['eid'],'EARNING','Blocked',Decimal('10'),None,7)]:
                try:operation()
                except ValueError:pass
                else:raise AssertionError('Finalized historical child was rewritten')
                assert row(f)==before and len(logs())==audit
        print('PASS inconsistent DRAFT parent cannot permit recalculation or adjustments of APPROVED/PAID children')
        # Guard timeout is a rolled-back validation error, never success.
        f=fixture('PROCESSING');before=row(f);audit=len(logs());held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        def short_wait():
            connection=connect();cur=connection.cursor();cur.execute('SET SESSION innodb_lock_wait_timeout=1');cur.close();return connection
        try:
            with patch.object(workflow,'get_connection',side_effect=short_wait):assert action(f,'PROCESSING').status_code==302
        finally:held.rollback();held.close()
        assert row(f)==before and len(logs())==audit
        # HR and period-form routes display coordinated-write errors instead of 500s.
        for permission in ['attendance.manage','leave.manage']:
            permission_id=sql('INSERT INTO permissions(permission_code) VALUES(%s) ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)',(permission,))
            sql('INSERT IGNORE INTO role_permissions(role_id,permission_id) VALUES(41,%s)',(permission_id,))
        for module,path,fields,table in [
            (attendance,'/attendance/add',dict(employee_id='9',attendance_date='2040-02-01',time_in='09:00',time_out='17:00',status='PRESENT',notes='Synthetic'),'attendance_records'),
            (leave,'/leave/types/add',dict(leave_code='GUARDTEST',leave_name='Guard test',description='Synthetic',annual_entitlement='5',is_paid='1'),'leave_types'),
            (periods,'/payroll/periods/add',dict(period_name='Guard period',start_date='2040-03-01',end_date='2040-03-15',pay_date='2040-03-16',notes='Synthetic'),'payroll_periods')]:
            old_count=sql('SELECT COUNT(*) AS n FROM '+table,fetch=True)[0]['n'];held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
            try:
                with patch.object(module,'get_connection',side_effect=short_wait):
                    http=client();response=http.post(path,data=fields);assert response.status_code==302
                    with http.session_transaction() as session:assert any('concurrently' in message for _,message in session.get('_flashes',[])),path
            finally:held.rollback();held.close()
            assert sql('SELECT COUNT(*) AS n FROM '+table,fetch=True)[0]['n']==old_count
        print('PASS HR and period-form lock-timeout responses: visible retry errors, no partial business writes')
        # An opposite-order external/legacy writer is deliberately not a protocol participant.
        f=fixture('PROCESSING');before=row(f);audit=len(logs());outsider=connect();outsider.start_transaction();cur=outsider.cursor()
        cur.execute("UPDATE attendance_records SET notes='Synthetic deadlock weight'")
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(action,f,'PROCESSING')
            try:
                deadline=time.monotonic()+8
                while sql("SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<1:
                    assert time.monotonic()<deadline;time.sleep(0.05)
                cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
            finally:outsider.rollback();outsider.close()
            assert future.result(timeout=12).status_code==302
        assert row(f)==before and len(logs())==audit
        assert action(f,'PROCESSING').status_code==302 and row(f)['status']=='APPROVED'
        print('PASS real lock timeout/deadlock: full rollback, no success audit, released locks and explicit successful retry')
        # Real route boundaries stay ahead of every business mutation.
        for stage,permission in [('DRAFT','payroll.process'),('PROCESSING','payroll.approve'),('APPROVED','payroll.pay')]:
            f=fixture(stage);before=row(f);audit=len(logs())
            path=f"/payroll/periods/{f['p']}/"+{'DRAFT':'submit','PROCESSING':'approve','APPROVED':'paid'}[stage]
            assert client(False).post(path,data={}).location.endswith('/dashboard')
            assert erp.app.test_client().post(path,data={}).status_code==400
            sql('DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=41 AND permission_code=%s',(permission,))
            assert client().post(path,data={}).location.endswith('/dashboard')
            assert row(f)==before and len(logs())==audit
            sql('INSERT INTO role_permissions SELECT 41,permission_id FROM permissions WHERE permission_code=%s',(permission,))
        print('PASS submit/approve/pay: forged POST, CSRF and committed permission revocation leave amounts, evidence and audits unchanged')
    print('SUCCESS: full Payroll freshness tested on disposable MySQL and synthetic records only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
