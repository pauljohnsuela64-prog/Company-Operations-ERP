"""Release-only synthetic migration/access, backup/restore and bounded guard checks.

Not a company setup tool. All connection targets are owned by the verified harness.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash
import mysql_audit_smoke as harness


def run(port, data_dir):
    real_connect = mysql.connector.connect
    config = dict(host='127.0.0.1', port=port, user='root', password='',
                  database='erp_release_rehearsal', connection_timeout=3)
    with real_connect(host=config['host'], port=port, user='root', password='') as db:
        cur = db.cursor(); cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_release_rehearsal')
        cur.execute('USE erp_release_rehearsal')
        for name in ('core','inventory','procurement','finance','budget','attendance','leave',
                     'payroll','payroll_period','payroll_entries','payroll_calculation',
                     'payroll_approval','payroll_adjustments','audit_logs'):
            source = (harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        cur.execute("INSERT INTO permissions(permission_code) VALUES('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage')")
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic release operator')")
        cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'synthetic-release',%s)",
                    (generate_password_hash('synthetic-release-only'),))
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(1,'RELEASE','Synthetic','Employee')")
        cur.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(1,1,'MONTHLY',1000,'2026-01-01',1)")
        for identity, status in ((1,'DRAFT'),(2,'PAID')):
            start, end, payday = ('2026-01-05','2026-01-09','2026-01-10') if identity == 1 else ('2026-01-12','2026-01-16','2026-01-17')
            cur.execute("INSERT INTO payroll_periods(payroll_period_id,period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,1)",
                        (identity,'RELEASE-'+str(identity),'Synthetic release '+str(identity),start,end,payday,status))
            cur.execute("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,net_pay,status,generated_by) VALUES(%s,1,1,'MONTHLY',1000,123,%s,1)", (identity,status))
        db.commit()

    def sql(statement, params=(), fetch=False, target=None):
        with real_connect(**dict(config, database=target or config['database'])) as db:
            cur = db.cursor(); cur.execute(statement, params)
            result = cur.fetchall() if fetch else None
            db.commit(); return result

    def guarded_connect(**options):
        assert options['host'] == config['host'] and options['port'] == port
        assert options['database'] == config['database'] and options['user'] == 'root'
        return real_connect(**config)

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict(os.environ, SECRET_KEY='synthetic-release-verification-only', ERP_ENV='testing',
            ERP_DEBUG='false', DB_HOST=config['host'], DB_PORT=str(port), DB_USER='root',
            DB_PASSWORD='synthetic-config-only', DB_NAME=config['database']))
        stack.enter_context(patch('mysql.connector.connect', side_effect=guarded_connect))
        database = importlib.import_module('database')
        erp = importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        client = erp.app.test_client()
        database.invalidate_compatibility()
        assert client.get('/health/ready').status_code == 200
        assert client.get('/login').status_code == 200
        print('PASS fresh synthetic installation through real global schema admission and HTTP login page')

        # Simulate legacy/partial 010 only on our owned synthetic target.
        evidence = {'attendance_evidence_version','attendance_scope_start','attendance_scope_end'}
        columns = [r[0] for r in sql('SHOW COLUMNS FROM payroll_entries', fetch=True) if r[0] not in evidence]
        query = 'SELECT '+','.join(columns)+' FROM payroll_entries ORDER BY payroll_entry_id'
        before = sql(query, fetch=True)
        for table in ('payroll_attendance_snapshots','payroll_attendance_generations','payroll_attendance_guard'):
            sql('DROP TABLE '+table)
        for column in sorted(evidence):
            sql('ALTER TABLE payroll_entries DROP COLUMN '+column)
        database.invalidate_compatibility()
        assert client.get('/health/ready').status_code == 503
        response = client.get('/login')
        assert response.status_code == 503 and response.headers['Cache-Control'] == 'no-store'
        assert sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_attendance_guard'", fetch=True) == [(0,)]
        spec = importlib.util.spec_from_file_location('release_migration010', harness.ROOT/'database/migrations/010_payroll_attendance_freshness.py')
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        import payroll_freshness as freshness
        sql(freshness.GENERATIONS_DDL)
        sql('ALTER TABLE payroll_entries ADD attendance_scope_start DATE NULL')
        for _ in range(2):
            with real_connect(**config) as db: migration.migrate(db,config['database'])
        assert sql(query, fetch=True) == before
        assert sql('SELECT COUNT(*) FROM payroll_attendance_snapshots', fetch=True) == [(0,)]
        assert sql('SELECT COUNT(*) FROM payroll_entries WHERE attendance_evidence_version IS NOT NULL', fetch=True) == [(0,)]
        database.invalidate_compatibility()
        assert client.get('/health/ready').status_code == 200 and client.get('/login').status_code == 200
        print('PASS missing 010 blocks application access without repair; partial/repeated migration restores access and preserves legacy/PAID amounts and statuses')

        attendance = importlib.import_module('attendance_repository')
        calculation = importlib.import_module('payroll_calculation_repository')
        workflow = importlib.import_module('payroll_workflow_repository')
        identities = [attendance.create_attendance_record(1,date(2026,1,day),None,None,'PRESENT',None,1) for day in range(5,10)]
        durations = []
        for _ in range(20):
            started = time.perf_counter(); calculation.calculate_monthly_payroll_period(1,1)
            durations.append((time.perf_counter()-started)*1000)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: calculation.calculate_monthly_payroll_period(1,1), range(12)))
        concurrent_ms = (time.perf_counter()-started)*1000
        assert sql('SELECT COUNT(*) FROM payroll_attendance_snapshots WHERE payroll_entry_id=1', fetch=True) == [(5,)]
        paid_before = sql('SELECT * FROM payroll_entries WHERE payroll_period_id=2', fetch=True)
        attendance.update_attendance_record(identities[0],1,date(2026,1,5),None,None,'ABSENT',None,1)
        print('MEASURE '+json.dumps(dict(dataset='1 employee / 5 weekdays / 2 periods', samples=20,
            serial_median_ms=round(statistics.median(durations),3), serial_max_ms=round(max(durations),3),
            concurrent_workers=4, concurrent_operations=12, concurrent_total_ms=round(concurrent_ms,3),
            logical_cpus=os.cpu_count(), concurrent_other_release_checks=True)))

        # Dump and restore with installed client tools, no option files or company endpoint.
        binary = Path(r'C:\Program Files\MySQL\MySQL Server 8.0\bin')
        args = ['--no-defaults','--host=127.0.0.1','--port='+str(port),'--user=root']
        dump = subprocess.run([str(binary/'mysqldump.exe'),*args,'--single-transaction','--skip-lock-tables',
            '--set-gtid-purged=OFF','--no-tablespaces',config['database']],capture_output=True,check=True).stdout
        restored = 'erp_release_restored'
        sql('CREATE DATABASE '+restored)
        subprocess.run([str(binary/'mysql.exe'),*args,restored],input=dump,capture_output=True,check=True)
        tables = [row[0] for row in sql('SHOW TABLES', fetch=True)]
        for table in tables:
            assert sql('SELECT * FROM '+table+' ORDER BY 1', fetch=True) == sql('SELECT * FROM '+table+' ORDER BY 1', fetch=True,target=restored), table
        with real_connect(**dict(config,database=restored)) as db: migration.migrate(db,restored)
        # Every worker uses the restored target together; evidence remains stale.
        config['database'] = restored
        os.environ['DB_NAME'] = restored
        database.invalidate_compatibility()
        assert client.get('/health/ready').status_code == 200
        try: workflow.submit_payroll_for_approval(1,1)
        except freshness.FreshnessError: pass
        else: raise AssertionError('Restoration fabricated fresh evidence')
        calculation.calculate_monthly_payroll_period(1,1)
        workflow.submit_payroll_for_approval(1,1); workflow.approve_payroll_period(1,1)
        workflow.mark_payroll_period_as_paid(1,1)
        assert sql('SELECT * FROM payroll_entries WHERE payroll_period_id=2', fetch=True) == paid_before
        print('PASS synthetic backup/restore exact '+str(len(tables))+' tables; dump SHA256 '+hashlib.sha256(dump).hexdigest())
        print('PASS restored readiness, stale rejection, explicit calculation/submit/approve/pay and unchanged prior PAID history')
        verify_payroll_http(erp, sql)
    print('SUCCESS release rehearsal: disposable synthetic data only; no production capacity or recovery policy certification')


def verify_payroll_http(erp, sql):
    """Earn entries through generation and use actual authenticated route contracts."""
    from decimal import Decimal
    from security_helpers import csrf_client
    for code in ('payroll.view','payroll.compensation.manage','payroll.process','payroll.approve','payroll.pay'):
        sql('INSERT INTO permissions(permission_code) VALUES(%s) ON DUPLICATE KEY UPDATE permission_code=VALUES(permission_code)', (code,))
        sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions WHERE permission_code=%s', (code,))
    sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(2,'HTTP-RELEASE','Synthetic','HTTP Employee')")
    client = csrf_client(erp.app)
    response = client.post('/login', data=dict(username='synthetic-release',password='synthetic-release-only'))
    assert response.status_code == 302 and response.location.endswith('/dashboard')
    compensation = dict(employee_id='2',pay_type='MONTHLY',basic_rate='1200.00',effective_date='2026-01-01',notes='Synthetic release')
    assert client.post('/payroll/compensation/add',data=compensation).status_code == 302
    identity = sql('SELECT compensation_id FROM employee_compensation WHERE employee_id=2',fetch=True)[0][0]
    assert client.post(f'/payroll/compensation/{identity}/edit',data=dict(compensation,basic_rate='1400.00')).status_code == 302
    assert sql('SELECT basic_rate FROM employee_compensation WHERE employee_id=2',fetch=True) == [(Decimal('1400.00'),)]
    form = dict(period_name='HTTP release period',start_date='2026-01-19',end_date='2026-01-23',pay_date='2026-01-24',notes='Synthetic')
    assert client.post('/payroll/periods/add',data=form).status_code == 302
    period = sql("SELECT payroll_period_id FROM payroll_periods WHERE period_name='HTTP release period'",fetch=True)[0][0]
    for _ in range(2):
        assert client.post(f'/payroll/periods/{period}/generate').status_code == 302
    entries = sql('SELECT payroll_entry_id,employee_id FROM payroll_entries WHERE payroll_period_id=%s ORDER BY employee_id',(period,),True)
    assert len(entries)==2 and {row[1] for row in entries}=={1,2}
    for employee in (1,2):
        for day in range(19,24):
            erp.create_attendance_record(employee,date(2026,1,day),None,None,'PRESENT',None,1)
    assert client.post(f'/payroll/periods/{period}/calculate-monthly').status_code == 302
    entry = next(row[0] for row in entries if row[1]==2)
    before = sql('SELECT net_pay FROM payroll_entries WHERE payroll_entry_id=%s',(entry,),True)[0][0]
    assert client.post(f'/payroll/entries/{entry}/adjustments/add',data=dict(adjustment_type='EARNING',adjustment_name='Synthetic allowance',amount='25.10',notes='Synthetic')).status_code == 302
    adjustment = sql('SELECT adjustment_id FROM payroll_adjustments WHERE payroll_entry_id=%s',(entry,),True)[0][0]
    assert sql('SELECT net_pay FROM payroll_entries WHERE payroll_entry_id=%s',(entry,),True)==[(before+Decimal('25.10'),)]
    assert client.post(f'/payroll/entries/{entry}/adjustments/{adjustment}/delete').status_code == 302
    assert sql('SELECT net_pay FROM payroll_entries WHERE payroll_entry_id=%s',(entry,),True)==[(before,)]
    assert client.post(f'/payroll/periods/{period}/submit').status_code == 302
    assert client.post(f'/payroll/periods/{period}/return-to-draft').status_code == 302
    assert client.post(f'/payroll/periods/{period}/submit').status_code == 302
    assert client.post(f'/payroll/periods/{period}/approve').status_code == 302
    assert client.post(f'/payroll/periods/{period}/paid').status_code == 302
    assert sql('SELECT status FROM payroll_periods WHERE payroll_period_id=%s',(period,),True)==[('PAID',)]
    assert client.get(f'/payroll/entries/{entry}/payslip').status_code == 200
    assert client.get('/payroll/periods?status=PAID').status_code == 200
    number = sql('SELECT period_number FROM payroll_periods WHERE payroll_period_id=%s',(period,),True)[0][0]
    events = sql("SELECT action FROM audit_logs WHERE module='PAYROLL' AND entity_type='PAYROLL_PERIOD' AND entity_id=%s ORDER BY audit_log_id",(number,),True)
    assert [row[0] for row in events if row[0] in ('SUBMIT','RETURN_TO_DRAFT','APPROVE','MARK_PAID')] == ['SUBMIT','RETURN_TO_DRAFT','SUBMIT','APPROVE','MARK_PAID'], events
    print('PASS real HTTP login/compensation create-edit/generate dedup/calculation/adjustment add-delete/submit-return-approve-pay/payslip/history/audit; exact Decimal adjustment reversal')


if __name__ == '__main__':
    harness.run = run
    harness.main()
