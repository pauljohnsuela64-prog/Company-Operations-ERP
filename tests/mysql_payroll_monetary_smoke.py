r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_payroll_monetary_smoke.py
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
        from decimal import Decimal
        from importlib.util import spec_from_file_location, module_from_spec
        import payroll_repository as compensation
        import payroll_period_repository as periods
        import payroll_adjustment_repository as adjustments
        import payroll_calculation_repository as calculation
        import payroll_freshness as freshness
        from payroll_validation import MAX_MONEY

        spec = spec_from_file_location('upgrade_payroll', ROOT/'database/migrations/004_payroll_freshness.py')
        migration = module_from_spec(spec); spec.loader.exec_module(migration)
        with connect() as connection:
            migration.upgrade(connection)
        # Every repository connection explicitly uses the mode being tested.
        mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'
        original_connect = connect
        def connect():
            connection = original_connect()
            cur = connection.cursor(); cur.execute('SET SESSION sql_mode=%s', (mode,)); cur.close()
            return connection

        for module in (compensation, periods, adjustments, calculation):
            stack.enter_context(patch.object(module, 'get_connection', side_effect=connect))
        for code in ('payroll.compensation.manage', 'payroll.view'):
            sql('INSERT IGNORE INTO role_permissions SELECT 41,permission_id FROM permissions WHERE permission_code=%s',(code,))

        def rejected(operation, message=None):
            try:
                operation()
            except ValueError as error:
                if message:
                    assert message in str(error), str(error)
            else:
                raise AssertionError('Expected validation rejection')

        def snapshot():
            return [sql('SELECT * FROM '+table+' ORDER BY 1', fetch=True)
                    for table in ('employee_compensation','payroll_periods','payroll_entries','payroll_adjustments','audit_logs')]

        counter = 0
        def fixture(rate=Decimal('1000')):
            nonlocal counter
            counter += 1
            start = date(2027,1,4) + timedelta(days=35*counter)
            p = periods.create_payroll_period('Money '+str(counter), start, start+timedelta(days=4), start+timedelta(days=5), None, 7)
            compensation.update_employee_compensation(1,'MONTHLY',rate,'2026-01-01',None,7)
            erp.generate_payroll_entries(p,7)
            for i in range(5):
                sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,'PRESENT',7)", (start+timedelta(days=i),))
            erp.calculate_monthly_payroll_period(p,7)
            eid = sql('SELECT payroll_entry_id FROM payroll_entries WHERE payroll_period_id=%s',(p,),True)[0]['payroll_entry_id']
            return p,eid

        def entry(eid):
            return sql('SELECT * FROM payroll_entries WHERE payroll_entry_id=%s',(eid,),True)[0]

        for mode in ('STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION', ''):
            assert sql('SELECT @@session.sql_mode AS mode',fetch=True)[0]['mode'] == mode
            label = 'strict' if mode else 'non-strict'
            for amount in ('NaN','Infinity','-Infinity','0','-1','0.001','1.000','10000000000','9999999999.995','broken'):
                before = snapshot()
                rejected(lambda: compensation.update_employee_compensation(1,'MONTHLY',amount,'2026-01-01',None,7))
                rejected(lambda: compensation.create_employee_compensation(9,'MONTHLY',amount,'2026-01-01',None,7))
                assert snapshot() == before
                response = client().post('/payroll/compensation/1/edit',data=dict(pay_type='MONTHLY',basic_rate=amount,effective_date='2026-01-01',notes='Synthetic'))
                assert response.status_code == 302 and response.location.endswith('/payroll/compensation/1/edit') and snapshot() == before
            for amount in ('0.01','9999999999.99'):
                compensation.update_employee_compensation(1,'MONTHLY',amount,'2026-01-01',None,7)
                assert sql('SELECT basic_rate FROM employee_compensation WHERE compensation_id=1',fetch=True)[0]['basic_rate'] == Decimal(amount)
                boundary_period,boundary_entry=fixture(Decimal(amount))
                expected=Decimal('0.01') if amount=='0.01' else Decimal('5000000000.00')
                assert entry(boundary_entry)['regular_pay']==expected
            p,eid = fixture()
            path = f'/payroll/entries/{eid}/adjustments/add'
            for amount in ('NaN','Infinity','0','-1','0.001','1.000','10000000000','broken'):
                before = snapshot()
                rejected(lambda: adjustments.add_payroll_adjustment(eid,'EARNING','Synthetic',amount,None,7))
                response = client().post(path,data=dict(adjustment_type='EARNING',adjustment_name='Synthetic',amount=amount,notes=''))
                assert response.status_code == 302 and snapshot() == before
            # Gross overflow can occur even when the earnings aggregate itself fits.
            before = snapshot()
            rejected(lambda: adjustments.add_payroll_adjustment(eid,'EARNING','Overflow',MAX_MONEY,None,7),'Gross pay')
            assert snapshot() == before
            adjustments.add_payroll_adjustment(eid,'EARNING','Exact boundary',MAX_MONEY-Decimal('500'),None,7)
            assert entry(eid)['gross_pay'] == MAX_MONEY
            erp.calculate_monthly_payroll_period(p,7)
            assert entry(eid)['net_pay'] == MAX_MONEY and entry(eid)['calculation_input_hash']
            before = snapshot()
            rejected(lambda: adjustments.add_payroll_adjustment(eid,'EARNING','One cent over','0.01',None,7))
            assert snapshot() == before
            # Existing excess-deduction policy remains a zero net floor.
            p,eid = fixture()
            adjustments.add_payroll_adjustment(eid,'DEDUCTION','Exact deduction boundary',MAX_MONEY,None,7)
            assert entry(eid)['net_pay'] == 0 and entry(eid)['total_deductions'] == MAX_MONEY
            before = snapshot()
            rejected(lambda: adjustments.add_payroll_adjustment(eid,'DEDUCTION','Overflow','0.01',None,7),'Other deductions')
            assert snapshot() == before
            # A changed attendance deduction can overflow total deductions on recalculation.
            sql("UPDATE attendance_records a JOIN payroll_periods p ON a.attendance_date=p.start_date SET a.status='ABSENT' WHERE p.payroll_period_id=%s",(p,))
            before = snapshot()
            rejected(lambda: calculation.calculate_monthly_payroll_period(p,7),'Total deductions')
            assert snapshot() == before
            # Reproduce a legacy oversized aggregate inserted directly in the isolated fixture.
            p,eid = fixture()
            for _ in range(2):
                sql("INSERT INTO payroll_adjustments(payroll_entry_id,adjustment_type,adjustment_name,amount,created_by) VALUES(%s,'EARNING','Legacy oversized aggregate',%s,7)",(eid,MAX_MONEY))
            before = snapshot()
            rejected(lambda: calculation.calculate_monthly_payroll_period(p,7))
            assert snapshot() == before
            assert entry(eid)['net_pay'] == Decimal('500')
            # Emulate old non-strict clipping with a genuine version-1 fingerprint.
            # Only fixture construction disables the new capacity check; real
            # submit/approve/pay requests below use all production safeguards.
            sql('UPDATE payroll_entries SET additional_earnings=%s,gross_pay=%s,net_pay=%s WHERE payroll_entry_id=%s',
                (MAX_MONEY,MAX_MONEY,MAX_MONEY,eid))
            with connect() as connection:
                cur=connection.cursor(dictionary=True)
                with patch.object(freshness,'validate_evidence_money'):
                    freshness.seal_calculation(cur,p,eid)
                connection.commit();cur.close()
            for stage,suffix in (('DRAFT','submit'),('PROCESSING','approve'),('APPROVED','paid')):
                sql('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s',(stage,p))
                sql('UPDATE payroll_entries SET status=%s WHERE payroll_entry_id=%s',('APPROVED' if stage=='APPROVED' else 'CALCULATED',eid))
                before=snapshot()
                response=client().post(f'/payroll/periods/{p}/{suffix}',data={})
                assert response.status_code==302 and snapshot()==before
            # A genuine late SQL failure rolls the inserted adjustment back too.
            p,eid = fixture(); before = snapshot()
            sql("CREATE TRIGGER reject_money BEFORE UPDATE ON payroll_entries FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic rollback'")
            try:
                try: adjustments.add_payroll_adjustment(eid,'EARNING','Rollback','0.01',None,7)
                except mysql.connector.Error: pass
                else: raise AssertionError('Expected late SQL failure')
            finally: sql('DROP TRIGGER reject_money')
            assert snapshot() == before
            # A later employee failure rolls back earlier employees in the batch.
            sql("INSERT IGNORE INTO employees(employee_id,employee_number,first_name,last_name,employment_status) VALUES(10,'MONEY-10','Zed','ZZZ','Inactive')")
            comp10=sql("INSERT INTO employee_compensation(employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(10,'MONTHLY',1000,'2026-01-01',7) ON DUPLICATE KEY UPDATE compensation_id=LAST_INSERT_ID(compensation_id)")
            other=sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(%s,10,%s,'MONTHLY',1000,7)",(p,comp10))
            sql("INSERT INTO payroll_adjustments(payroll_entry_id,adjustment_type,adjustment_name,amount,created_by) VALUES(%s,'EARNING','Synthetic second employee overflow',%s,7)",(other,MAX_MONEY))
            sql("UPDATE payroll_entries SET regular_pay=0,gross_pay=0,net_pay=0,status='DRAFT',calculation_input_hash=NULL,calculation_input_version=NULL WHERE payroll_entry_id=%s",(eid,))
            before=snapshot()
            rejected(lambda:calculation.calculate_monthly_payroll_period(p,7),'Gross pay')
            assert snapshot()==before
            print('PASS',label,': exact money boundaries, route/repository rejection, aggregate overflow, preserved evidence/values, late rollback and no success audits')

        mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'
        # Atomic period overlap verification: hold the actual shared row and
        # prove both real MySQL transactions are waiting before releasing it.
        def race(first, second):
            held = connect(); held.start_transaction(); cur = held.cursor()
            cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE'); cur.fetchall()
            def attempt(fn):
                try: return fn()
                except ValueError as error: return str(error)
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures = [pool.submit(attempt, fn) for fn in (first,second)]
                    try:
                        deadline = time.monotonic()+8
                        while sql("SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n'] < 2:
                            assert time.monotonic() < deadline, 'Both writers must reach a real InnoDB wait'
                            time.sleep(.05)
                    finally: held.commit()
                    return [f.result(timeout=12) for f in futures]
            finally: cur.close(); held.close()

        def create(name,start,end):
            return periods.create_payroll_period(name,start,end,end,None,7)
        start,end = date(2040,1,1),date(2040,1,15)
        results = race(lambda:create('Race create A',start,end),lambda:create('Race create B',start,end))
        assert sum(isinstance(r,int) for r in results)==1 and sum('overlap' in str(r) for r in results)==1,results
        winner=next(r for r in results if isinstance(r,int))
        for status in ('PROCESSING','APPROVED','PAID'):
            sql('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s',(status,winner))
            rejected(lambda:create('Overlap finalized '+status,start,end),'overlap')
        sql("UPDATE payroll_periods SET status='DRAFT' WHERE payroll_period_id=%s",(winner,))
        # Inclusive endpoints overlap; adjacent days are valid; cancelled periods are excluded.
        rejected(lambda:create('Inclusive overlap',end,end),'overlap')
        adjacent = create('Adjacent',date(2040,1,16),date(2040,1,20))
        assert periods.cancel_payroll_period(adjacent,7)
        create('Cancelled replacement',date(2040,1,16),date(2040,1,20))
        a = create('Edit source A',date(2041,1,1),date(2041,1,5))
        b = create('Edit source B',date(2041,2,1),date(2041,2,5))
        def edit(pid,name):
            return periods.update_payroll_period(pid,name,date(2041,3,1),date(2041,3,5),date(2041,3,6),None,7)
        results = race(lambda:edit(a,'Edited A'),lambda:edit(b,'Edited B'))
        assert results.count(True)==1 and sum('overlap' in str(r) for r in results)==1,results
        results = race(lambda:create('Nonoverlap A',date(2042,1,1),date(2042,1,5)),lambda:create('Nonoverlap B',date(2042,2,1),date(2042,2,5)))
        assert all(isinstance(r,int) for r in results)
        # CREATE versus EDIT also share the same coordination boundary.
        a=create('Create edit source',date(2043,1,1),date(2043,1,5))
        results=race(lambda:create('Create edit contender',date(2043,2,1),date(2043,2,5)),
                     lambda:periods.update_payroll_period(a,'Create edit moved',date(2043,2,1),date(2043,2,5),date(2043,2,6),None,7))
        assert sum('overlap' in str(r) for r in results)==1,results
        cancelled=create('Cancellation race',date(2043,4,1),date(2043,4,5))
        results=race(lambda:periods.cancel_payroll_period(cancelled,7),
                     lambda:create('Cancellation replacement',date(2043,4,1),date(2043,4,5)))
        assert results[0] is True
        assert isinstance(results[1],int) or 'overlap' in results[1],results
        assert sql("SELECT COUNT(*) AS n FROM payroll_periods WHERE status <> 'CANCELLED' AND start_date='2043-04-01'",fetch=True)[0]['n'] <= 1
        # Failed transactions do not leave a period or prevent a subsequent valid creation.
        before = snapshot()
        sql("CREATE TRIGGER reject_period_number BEFORE UPDATE ON payroll_periods FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic rollback'")
        try:
            try: create('Rollback period',date(2044,1,1),date(2044,1,5))
            except mysql.connector.Error: pass
            else: raise AssertionError('Expected late SQL failure')
        finally: sql('DROP TRIGGER reject_period_number')
        assert snapshot()==before
        create('Rollback period',date(2044,1,1),date(2044,1,5))
        print('PASS five actual two-waiter MySQL period races: overlapping CREATE, EDIT, CREATE/EDIT, nonoverlap, cancellation; inclusive endpoints, cancelled exclusion and late rollback')

        held=connect(); held.start_transaction(); cur=held.cursor()
        cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        def short_connection():
            connection=connect(); c=connection.cursor(); c.execute('SET SESSION innodb_lock_wait_timeout=1'); c.close(); return connection
        before=snapshot()
        try:
            with patch.object(periods,'get_connection',side_effect=short_connection):
                rejected(lambda:create('Timeout period',date(2045,1,1),date(2045,1,5)),'retry')
        finally: held.rollback();cur.close();held.close()
        assert snapshot()==before
        print('PASS real period guard timeout rolls back without partial records or success audits')

        p,eid=fixture()
        results=race(lambda:adjustments.add_payroll_adjustment(eid,'EARNING','Contender A',MAX_MONEY-Decimal('500'),None,7),
                     lambda:adjustments.add_payroll_adjustment(eid,'EARNING','Contender B',MAX_MONEY-Decimal('500'),None,7))
        assert results.count(None)==1 and sum(isinstance(r,str) for r in results)==1,results
        assert entry(eid)['gross_pay']==MAX_MONEY
        assert len(sql('SELECT * FROM payroll_adjustments WHERE payroll_entry_id=%s',(eid,),True))==1
        p,eid=fixture()
        results=race(lambda:calculation.calculate_monthly_payroll_period(p,7),
                     lambda:adjustments.add_payroll_adjustment(eid,'EARNING','Concurrent calculation','1.00',None,7))
        row=entry(eid)
        assert row['net_pay']==Decimal('501')
        assert (row['status']=='CALCULATED' and row['calculation_input_hash']) or (row['status']=='DRAFT' and row['calculation_input_hash'] is None)
        print('PASS actual concurrent adjustment overflow allows one commit; calculation/adjustment race preserves matching totals and evidence')

        p,eid=fixture(); path=f'/payroll/entries/{eid}/adjustments/add'
        form=dict(adjustment_type='EARNING',adjustment_name='Synthetic',amount='1.00',notes='')
        before=snapshot()
        assert client(False).post(path,data=form).location.endswith('/dashboard')
        assert erp.app.test_client().post(path,data=form).status_code==400
        active=client()
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=41 AND permission_code='payroll.process'")
        assert active.post(path,data=form).location.endswith('/dashboard')
        assert snapshot()==before
        print('PASS monetary route forged POST, CSRF and permission revoked after session creation; no mutations/audits')
    print('SUCCESS: Payroll monetary integrity and actual concurrent periods tested on disposable MySQL only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()

