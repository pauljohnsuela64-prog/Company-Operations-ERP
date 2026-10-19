r"""Synthetic period-wide calculator transaction fixtures; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_payroll_period_atomicity_smoke.py
Requires the local Windows MySQL server binary, overridable with --mysqld.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
import importlib
from pathlib import Path
import re
import sys
import threading
import time
from unittest.mock import patch

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
def run(port, data_dir):
    options = dict(host="127.0.0.1", port=port, user="root", password="", connection_timeout=3)
    server = mysql.connector.connect(**options)
    cursor = server.cursor()
    cursor.execute("SELECT @@datadir")
    assert Path(cursor.fetchone()[0]).resolve() == data_dir.resolve(), "Isolation check failed"
    schema = "erp_synthetic_payroll_period"
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
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        import copy
        import json
        from dataclasses import replace
        from decimal import Decimal
        import payroll_certification_repository as certs
        import payroll_evidence_repository as evidence
        import payroll_policy_repository as policies
        import payroll_policy_validation as validation
        import payroll_generation_repository as generation
        import payroll_entry_repository as entries
        import payroll_monthly_prototype as prototype
        from payroll_freshness import lock_payroll_inputs
        from payroll_schema_helpers import upgrade_policy_foundation
        from test_payroll_monthly_prototype import synthetic_input,adjustment
        from payroll_synthetic_period import DisposableFixture,calculate_period,entry_markers
        from importlib.util import spec_from_file_location,module_from_spec
        upgrade_policy_foundation(connect)
        def migrate(name):
            spec=spec_from_file_location('atomic_'+name[:3],ROOT/'database/migrations'/name)
            module=module_from_spec(spec);spec.loader.exec_module(module)
            with connect() as c:module.upgrade(c)
        migrate('006_payroll_certification.py')
        sql("UPDATE employees SET hire_date='2020-01-01' WHERE employee_id=9")
        sql("UPDATE employee_compensation SET basic_rate=30000 WHERE compensation_id=1")
        sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name,hire_date) VALUES(10,'SYNTHETIC-10','Synthetic','Second','2020-01-01')")
        sql("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(2,10,'MONTHLY',20000,'2026-01-01',7)")
        sql("INSERT IGNORE INTO role_permissions SELECT 41,permission_id FROM permissions WHERE permission_code='payroll.process'")
        config=validation.initial_policy();config.update(policy_name='SYNTHETIC:period policy',effective_from='2035-01-01')
        config.update(attendance_rules=dict(missing_evidence='BLOCK',late_treatment='NO_DEDUCTION',absence_treatment='PERIOD_WORKDAY_DIVISOR',half_day_treatment='HALF_DAY_DEDUCTION'),
            leave_rules=dict(paid_leave_treatment='NO_DEDUCTION',unpaid_leave_treatment='PERIOD_WORKDAY_DIVISOR',conflict='BLOCK'),
            eligibility_rules=dict(proration='BLOCK',full_cutoff_eligibility='VERIFIED_FULL_CUTOFF_ONLY'),
            deduction_rules=dict(excess_deductions='BLOCK',statutory='BLOCK',odd_cent_handling='BLOCK'))
        policy=policies.create_policy(config,7)
        policy=policies.approve_policy(policy['policy_version_id'],1,'SYNTHETIC:explicit hypothetical policy',True,7)
        policies.activate_policy(policy['policy_version_id'],7,'Asia/Manila')
        cutoffs=generation.generate_month(2035,1,'2035-01-15','2035-01-31',7)
        pid=cutoffs[0]['payroll_period_id']
        row=certs.prepare(pid,[9,10],'SYNTHETIC:roster','SYNTHETIC:calendar',7)
        for eid in (9,10):
            values=dict(disposition='INCLUDE',eligibility='FULL_CUTOFF',verification_status='VERIFIED',
                employment_coverage_start='2035-01-01',employment_coverage_end='2035-01-15',
                employment_reference=f'SYNTHETIC:employment-{eid}',compensation_coverage_end='2035-01-15',
                compensation_reference=f'SYNTHETIC:rate-{eid}')
            row=certs.save_member(row['certification_id'],eid,certs.revision_token(row),values,certs.digest(certs.get_employee_source(eid)))
        authority=dict(certifier_ids=[7],claims=dict(roster_ids=[9,10],roster_source_reference=row['roster_source_reference'],
            calendar_source_reference=row['calendar_source_reference'],calendar=copy.deepcopy(row['calendar_configuration']),
            members=[{k:v for k,v in m.items() if k!='certification_id'} for m in row['members']]))
        with patch.object(certs,'authoritative_evidence',return_value=authority):
            row=certs.publish(row['certification_id'],certs.revision_token(row),7)
        old_seal=copy.deepcopy(row)
        migrate('007_payroll_correction_references.py');migrate('007_payroll_correction_references.py')
        row=certs.get_certification(row['certification_id'])
        assert {k:v for k,v in row.items() if k not in ('correction_reason','correction_reference')}==old_seal
        entries.generate_payroll_entries(pid,7)
        current=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id',(pid,),True)
        entry_ids={r['employee_id']:r['payroll_entry_id'] for r in current}
        for eid in (9,10):
            for index,day in enumerate(certs.scheduled_dates(dict(start_date=date(2035,1,1),end_date=date(2035,1,15)))):
                sql('INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(%s,%s,%s,7)',
                    (eid,day,'ABSENT' if eid==10 and index==0 else 'PRESENT'))
        for kind,amount in [('EARNING',500),('DEDUCTION',300)]:
            sql('INSERT INTO payroll_adjustments(payroll_entry_id,adjustment_type,adjustment_name,amount,created_by) VALUES(%s,%s,%s,%s,7)',
                (entry_ids[9],kind,'SYNTHETIC:adjustment',amount))
        inputs=[]
        for eid,salary in [(9,'30000.00'),(10,'20000.00')]:
            item=synthetic_input(salary=Decimal(salary))
            item=replace(item,eligibility=replace(item.eligibility,hire_date=date(2020,1,1),
                compensation_coverage_start=date(2026,1,1),employment_reference=f'SYNTHETIC:employment-{eid}',
                compensation_reference=f'SYNTHETIC:rate-{eid}'))
            if eid==9:item=replace(item,adjustments=(adjustment('EARNING','500'),adjustment('DEDUCTION','300','SYNTHETIC:adjustment-2')))
            else:item=replace(item,attendance=(replace(item.attendance[0],status='ABSENT'),)+item.attendance[1:])
            inputs.append((eid,item))
        def fixture():
            records=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id',(pid,),True)
            return DisposableFixture(data_dir,schema,7,tuple(inputs),entry_markers(records))
        tables=('payroll_periods','payroll_entries','payroll_calculation_evidence','payroll_cutoff_certifications','payroll_certification_members','payroll_certification_events','audit_logs')
        def snapshot():return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in tables]
        def rejected(operation,contains=None):
            before=snapshot()
            try:operation()
            except (ValueError,mysql.connector.Error) as error:
                if contains:assert contains.casefold() in str(error).casefold(),str(error)
            else:raise AssertionError('Expected whole-period rejection')
            assert snapshot()==before,'Partial committed period state after rejection'
        def run_fixture(f=None,factory=connect):return calculate_period(factory,pid,f or fixture())
        rejected(run_fixture,'unavailable')
        with patch.object(certs,'authoritative_evidence',return_value=copy.deepcopy(authority)):
            # Real pre-007 seal remains byte-for-byte unchanged and is accepted
            # only through its exact known projection AFTER all source checks.
            with connect() as c:
                c.start_transaction();cur=c.cursor(dictionary=True)
                context=evidence.validate_eligibility(cur,pid)
                digest=certs.validate_publication(cur,row,context['period'],7)
                assert certs.verify_publication_digest(context['period'],row,digest)=='006'
                c.rollback();cur.close()
            assert certs.get_certification(row['certification_id'])==row
            print('PASS actual 006 seal through 007 without resealing, and production authority still fail-closed')
            # Caller-owned primitive must not commit its first employee.
            before=snapshot()
            with connect() as c:
                c.start_transaction();cur=c.cursor(dictionary=True)
                evidence.persist_proposed_in_transaction(cur,pid,entry_ids[9],prototype.calculate(inputs[0][1]).as_evidence_outputs(),7)
                assert snapshot()==before,'Primitive committed independently'
                c.rollback();cur.close()
            assert snapshot()==before
            # Explicit transaction atomicity also holds when the session default
            # is autocommit=1; do not change the public helper's supported behavior.
            with connect() as c:
                c.autocommit=True;c.start_transaction();cur=c.cursor(dictionary=True)
                evidence.persist_proposed_in_transaction(cur,pid,entry_ids[9],prototype.calculate(inputs[0][1]).as_evidence_outputs(),7)
                assert snapshot()==before
                c.rollback();cur.close()
            assert snapshot()==before
            for auto in (False,True):
                with connect() as c:
                    c.autocommit=auto;cur=c.cursor(dictionary=True)
                    rejected(lambda:evidence.persist_proposed_in_transaction(cur,pid,entry_ids[9],{},7),'caller-owned')
                    cur.close()
            # Failure matrix: policy, certification, eligibility, later arithmetic,
            # overflow, evidence insert, output and pointer association.
            for name in ('_policy',):
                import payroll_synthetic_period as adapter
                with patch.object(adapter,name,side_effect=ValueError('Synthetic policy failure')):rejected(run_fixture)
            with patch.object(certs,'authoritative_evidence',return_value=dict(authority,claims={})):rejected(run_fixture,'Authoritative')
            bad=replace(inputs[1][1],eligibility=replace(inputs[1][1].eligibility,hire_date=date(2035,1,2)))
            rejected(lambda:run_fixture(replace(fixture(),employee_inputs=(inputs[0],(10,bad)))),'proration')
            original=prototype.calculate
            def later(item):
                if item.monthly_salary==Decimal('20000'):raise ValueError('Synthetic second calculator failure')
                return original(item)
            with patch.object(prototype,'calculate',side_effect=later):rejected(run_fixture,'second calculator')
            bad=replace(inputs[1][1],adjustments=(adjustment('EARNING','9999999999.99'),))
            rejected(lambda:run_fixture(replace(fixture(),employee_inputs=(inputs[0],(10,bad)))),'database limit')
            for table,event,condition in (
                ('payroll_calculation_evidence','INSERT','NEW.employee_id=10'),
                ('payroll_entries','UPDATE','NEW.employee_id=10 AND NEW.calculation_input_version=2 AND NEW.net_pay<>OLD.net_pay'),
                ('payroll_entries','UPDATE','NEW.employee_id=10 AND NEW.current_calculation_evidence_id IS NOT NULL')):
                sql(f"CREATE TRIGGER synthetic_atomic_fail BEFORE {event} ON {table} FOR EACH ROW BEGIN IF {condition} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic later row failure'; END IF; END")
                try:rejected(run_fixture,'later row failure')
                finally:sql('DROP TRIGGER synthetic_atomic_fail')
            class CommitFailure:
                def __init__(self):self.inner=connect()
                def __getattr__(self,key):return getattr(self.inner,key)
                def commit(self):raise ValueError('Synthetic failure before commit')
            rejected(lambda:run_fixture(factory=CommitFailure),'before commit')
            first_fixture=fixture();saved=run_fixture(first_fixture)
            assert len(saved)==2 and len(set(saved))==2
            records=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id',(pid,),True)
            assert [r['net_pay'] for r in records]==[Decimal('15200.00'),Decimal('9090.91')]
            assert all(r['calculation_input_version']==2 and r['current_calculation_evidence_id'] in saved for r in records)
            assert len(sql('SELECT * FROM payroll_calculation_evidence',fetch=True))==2
            assert not sql('SELECT * FROM audit_logs',fetch=True)
            rejected(lambda:run_fixture(first_fixture),'changed')
            print('PASS multi-employee success exactly once, no synthetic central audit and full failure matrix rollback')
            # Recalculation failures restore the previous pointers AND immutable history.
            with patch.object(prototype,'calculate',side_effect=later):rejected(run_fixture,'second calculator')
            sql("CREATE TRIGGER synthetic_invalidate_fail BEFORE UPDATE ON payroll_entries FOR EACH ROW BEGIN IF NEW.employee_id=10 AND OLD.current_calculation_evidence_id IS NOT NULL AND NEW.current_calculation_evidence_id IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic invalidation failure'; END IF; END")
            try:rejected(run_fixture,'invalidation failure')
            finally:sql('DROP TRIGGER synthetic_invalidate_fail')
            history=sql('SELECT * FROM payroll_calculation_evidence ORDER BY 1',fetch=True)
            with connect() as c:
                c.start_transaction();cur=c.cursor(dictionary=True)
                assert evidence.invalidate_period_in_transaction(cur,pid)==2
                c.commit();cur.close()
            reset=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(pid,),True)
            assert all(r['current_calculation_evidence_id'] is None and r['calculation_input_version'] is None and r['calculation_input_hash'] is None and r['status']=='DRAFT' for r in reset)
            assert all(r[k]==0 for r in reset for k in evidence.MONEY_FIELDS+evidence.COUNT_FIELDS)
            assert history==sql('SELECT * FROM payroll_calculation_evidence ORDER BY 1',fetch=True)
            saved=run_fixture();assert len(saved)==2
            assert [r['calculation_sequence'] for r in sql('SELECT * FROM payroll_calculation_evidence ORDER BY payroll_entry_id,calculation_sequence',fetch=True)]==[1,2,1,2]
            print('PASS transactional invalidation, failure restoration and immutable recalculation sequences')
            def waits(count=1):
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    if sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']>=count:return
                    time.sleep(.03)
                raise AssertionError('Expected actual InnoDB wait')
            # Same reviewed fixture submitted concurrently: one whole period
            # commits; the queued request detects changed pointers and rolls back.
            f=fixture();before_count=len(sql('SELECT * FROM payroll_calculation_evidence',fetch=True))
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True);lock_payroll_inputs(hc)
            with ThreadPoolExecutor(2) as pool:
                pending=[pool.submit(run_fixture,f) for _ in range(2)]
                try:waits(2);assert not any(p.done() for p in pending)
                finally:held.commit();hc.close();held.close()
                outcomes=[]
                for p in pending:
                    try:outcomes.append(p.result(timeout=15))
                    except ValueError as err:assert 'changed' in str(err);outcomes.append(None)
                assert sum(r is not None for r in outcomes)==1
            assert len(sql('SELECT * FROM payroll_calculation_evidence',fetch=True))==before_count+2
            print('PASS simultaneous period calculations: two actual guard waits, one full commit, no duplicate evidence')
            # Timeouts happen before any calculations and must release all locks.
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True);lock_payroll_inputs(hc)
            def short_connect():
                c=connect();cur=c.cursor();cur.execute('SET SESSION innodb_lock_wait_timeout=1');cur.close();return c
            with ThreadPoolExecutor(1) as pool:
                before=snapshot();p=pool.submit(run_fixture,None,short_connect)
                try:
                    waits()
                    try:p.result(timeout=8)
                    except ValueError as err:assert getattr(err.__cause__,'errno',None)==1205
                    else:raise AssertionError('Expected real lock timeout')
                finally:held.rollback();hc.close();held.close()
            assert snapshot()==before
            # A deliberately noncooperating external session creates a genuine
            # lock-order cycle AFTER entry 9 wrote evidence. This test never
            # changes the application's established guard-first lock order.
            sql('CREATE TABLE synthetic_deadlock_weight(id INT PRIMARY KEY,v INT NOT NULL) ENGINE=InnoDB')
            for n in range(160):sql('INSERT INTO synthetic_deadlock_weight VALUES(%s,0)',(n,))
            external=connect();external.start_transaction();ec=external.cursor(dictionary=True)
            ec.execute('UPDATE synthetic_deadlock_weight SET v=v+1')
            ec.execute("UPDATE attendance_records SET notes='SYNTHETIC:external deadlock' WHERE employee_id=10")
            before=snapshot()
            with ThreadPoolExecutor(1) as pool:
                p=pool.submit(run_fixture)
                try:
                    waits()
                    ec.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');ec.fetchall()
                    try:p.result(timeout=10)
                    except ValueError as err:assert getattr(err.__cause__,'errno',None)==1213,str(err)
                    else:raise AssertionError('Expected calculation deadlock victim rollback')
                finally:external.rollback();ec.close();external.close()
            assert snapshot()==before
            print('PASS real 1205 timeout and real 1213 deadlock after earlier entry writes: whole-period rollback')
            # While the calculator holds the guard after its first employee,
            # a real compensation writer must wait. No mixed rate revisions.
            import payroll_repository as compensation
            ready=threading.Event();release=threading.Event()
            def pause_second(item):
                if item.monthly_salary==Decimal('20000'):
                    ready.set();assert release.wait(12)
                return original(item)
            with patch.object(prototype,'calculate',side_effect=pause_second),ThreadPoolExecutor(2) as pool:
                calc=pool.submit(run_fixture);assert ready.wait(10)
                writer=pool.submit(compensation.update_employee_compensation,1,'MONTHLY',Decimal('30002'),'2026-01-01',None,7)
                try:waits();assert not writer.done()
                finally:release.set()
                assert len(calc.result(timeout=15))==2;writer.result(timeout=15)
            rejected(run_fixture,'sources changed')
            compensation.update_employee_compensation(1,'MONTHLY',Decimal('30000'),'2026-01-01',None,7)
            # Reverse order: a validator waiting behind a rate change must read
            # the committed change and reject BEFORE it writes any entry.
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True);lock_payroll_inputs(hc)
            hc.execute('UPDATE employee_compensation SET basic_rate=30002 WHERE compensation_id=1')
            before=snapshot()
            with ThreadPoolExecutor(1) as pool:
                p=pool.submit(run_fixture)
                try:waits()
                finally:held.commit();hc.close();held.close()
                try:p.result(timeout=15)
                except ValueError as err:assert 'sources changed' in str(err)
                else:raise AssertionError('Expected stale compensation rejection')
            assert snapshot()==before
            compensation.update_employee_compensation(1,'MONTHLY',Decimal('30000'),'2026-01-01',None,7)
            sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(11,'SYNTHETIC-11','Synthetic','Roster change')")
            rejected(run_fixture,'sources changed');sql('DELETE FROM employees WHERE employee_id=11')
            print('PASS source writer/calculator in both lock orders, stale compensation and changed roster rejection')
            # Protected period and entry histories, and version dispatch, remain
            # guarded even when a new caller attempts transactional invalidation.
            for stage in ('APPROVED','PAID'):
                with connect() as c:
                    c.start_transaction();cur=c.cursor(dictionary=True);lock_payroll_inputs(cur)
                    cur.execute('UPDATE payroll_periods SET status=%s WHERE payroll_period_id=%s',(stage,pid))
                    try:evidence.invalidate_period_in_transaction(cur,pid)
                    except ValueError as err:assert 'history' in str(err)
                    else:raise AssertionError('Protected period invalidation was allowed')
                    c.rollback();cur.close()
                with connect() as c:
                    c.start_transaction();cur=c.cursor(dictionary=True);lock_payroll_inputs(cur)
                    cur.execute('UPDATE payroll_entries SET status=%s WHERE payroll_entry_id=%s',(stage,entry_ids[10]))
                    try:evidence.invalidate_period_in_transaction(cur,pid)
                    except ValueError as err:assert 'history' in str(err)
                    else:raise AssertionError('Protected entry invalidation was allowed')
                    c.rollback();cur.close()
            for version in (1,3):
                with connect() as c:
                    c.start_transaction();cur=c.cursor(dictionary=True)
                    evidence.invalidate_period_in_transaction(cur,pid)
                    cur.execute('UPDATE payroll_entries SET calculation_input_version=%s,calculation_input_hash=%s WHERE payroll_entry_id=%s',(version,'a'*64,entry_ids[9]))
                    try:evidence.invalidate_period_in_transaction(cur,pid)
                    except ValueError as err:assert 'version-1 or unknown' in str(err)
                    else:raise AssertionError('Unexpected migration of evidence version')
                    c.rollback();cur.close()
            # Safe commit failure was tested above. A lost acknowledgement AFTER
            # commit cannot be undone: inspect pointers and reject a stale replay.
            class LostAcknowledgement:
                def __init__(self):self.inner=connect()
                def __getattr__(self,key):return getattr(self.inner,key)
                def commit(self):self.inner.commit();raise ValueError('SYNTHETIC:lost commit acknowledgement')
            f=fixture();count=len(sql('SELECT * FROM payroll_calculation_evidence',fetch=True))
            try:run_fixture(f,LostAcknowledgement)
            except ValueError as err:assert 'acknowledgement' in str(err)
            else:raise AssertionError('Expected uncertain client outcome')
            assert len(sql('SELECT * FROM payroll_calculation_evidence',fetch=True))==count+2
            rejected(lambda:run_fixture(f),'changed')
            print('PASS protected history/version rejection and explicit post-commit acknowledgement limitation')
            # Publication/revocation policy stays unchanged. A real revocation
            # waits behind preparation; after its commit no stale calculation can run.
            ready.clear();release.clear()
            with patch.object(prototype,'calculate',side_effect=pause_second),ThreadPoolExecutor(2) as pool:
                calc=pool.submit(run_fixture);assert ready.wait(10)
                revoked=pool.submit(certs.revoke,row['certification_id'],certs.revision_token(row),7,
                    'SYNTHETIC:withdrawal','SYNTHETIC:case-001')
                try:waits();assert not revoked.done()
                finally:release.set()
                assert len(calc.result(timeout=15))==2;row=revoked.result(timeout=15)
            rejected(run_fixture,'withdrawn')
            # Draft invalidation is still possible when certification is revoked.
            with connect() as c:
                c.start_transaction();cur=c.cursor(dictionary=True)
                assert evidence.invalidate_period_in_transaction(cur,pid)==2
                c.commit();cur.close()
            assert not sql('SELECT * FROM audit_logs',fetch=True)
            print('PASS revocation waits behind dirty preparation, blocks later calculation, permits safe Draft invalidation')
        assert certs.authoritative_evidence({},7) is None
        print('SUCCESS: synthetic period-wide prototype, explicit disposable MySQL only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()

