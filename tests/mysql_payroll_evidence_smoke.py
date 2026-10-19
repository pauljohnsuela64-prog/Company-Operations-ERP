r"""Version-2 evidence fixtures; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_payroll_evidence_smoke.py
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
        import copy
        import json
        import payroll_certification_repository as certs
        import payroll_generation_repository as generation
        import employee_repository as employees
        import payroll_repository as compensation
        from importlib.util import spec_from_file_location,module_from_spec
        for number,name in [('006','payroll_certification')]:
            spec=spec_from_file_location('workflow_'+number,ROOT/'database/migrations'/f'{number}_{name}.py')
            module=module_from_spec(spec);spec.loader.exec_module(module)
            for _ in range(2):
                with connect() as connection:module.upgrade(connection)
        registration=(ROOT/'database/payroll_certification_permissions.sql').read_text()
        registration=re.sub(r'--[^\n]*','',registration)
        before=sql('SELECT * FROM role_permissions ORDER BY 1,2',fetch=True)
        for _ in range(2):
            for statement in registration.split(';'):
                if statement.strip():sql(statement)
        assert sql('SELECT * FROM role_permissions ORDER BY 1,2',fetch=True)==before
        for code in ('payroll.view','payroll.certification.certify','payroll.certification.revoke'):
            sql('INSERT IGNORE INTO role_permissions SELECT 41,permission_id FROM permissions WHERE permission_code=%s',(code,))
        cfg=validation.initial_policy();cfg.update(policy_name='Synthetic workflow policy',effective_from='2035-01-01')
        for field,schema_def in validation.JSON_RULES.items():
            if schema_def['type']=='object':cfg[field]={k:('BLOCK' if 'BLOCK' in p['enum'] else next(v for v in p['enum'] if v!='UNRESOLVED')) for k,p in schema_def['properties'].items()}
        policy=policies.create_policy(cfg,7);policy=policies.approve_policy(policy['policy_version_id'],1,'Synthetic HR policy approval WF-001',True,7)
        policies.activate_policy(policy['policy_version_id'],7,'Asia/Manila')
        periods=generation.generate_month(2035,1,'2035-01-15','2035-01-31',7)
        pid=periods[0]['payroll_period_id']
        sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name,employment_status) VALUES(10,'HISTORICAL','Synthetic','Historical','Inactive')")
        def edit_employee(hire,status='Active'):
            e=employees.get_employee_by_id(9)
            employees.update_employee(9,e['employee_number'],e['department_id'],e['first_name'],e['middle_name'],e['last_name'],e['email'],e['phone'],e['job_title'],hire,status)
        def token(row):return certs.revision_token(row)
        def save(cid,eid,token,values):return certs.save_member(cid,eid,token,values,certs.digest(certs.get_employee_source(eid)))
        def reject(fn,contains=None):
            before=[sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('payroll_cutoff_certifications','payroll_certification_members','payroll_certification_events','payroll_entries','audit_logs')]
            try:fn()
            except ValueError as error:
                if contains:assert contains.casefold() in str(error).casefold(),str(error)
            else:raise AssertionError('Expected rejected operation')
            after=[sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('payroll_cutoff_certifications','payroll_certification_members','payroll_certification_events','payroll_entries','audit_logs')]
            assert before==after
        from payroll_schema_helpers import upgrade_certification_workflow
        upgrade_certification_workflow(connect)
        import payroll_evidence_repository as evidence
        from payroll_evidence import MONEY_FIELDS,COUNT_FIELDS,evidence_digest,fingerprint_for_version
        from decimal import Decimal
        edit_employee('2020-01-01')
        row=certs.prepare(pid,[9,10],'Synthetic authoritative HR roster EV-001','Synthetic calendar EV-001',7)
        include=dict(disposition='INCLUDE',eligibility='FULL_CUTOFF',verification_status='VERIFIED',
            employment_coverage_start='2035-01-01',employment_coverage_end='2035-01-15',
            employment_reference='Synthetic HR full cutoff EV-001',compensation_coverage_end='2035-01-15',
            compensation_reference='Synthetic Finance rate EV-001')
        exclude=dict(disposition='EXCLUDE',eligibility='NOT_ELIGIBLE',verification_status='VERIFIED',
            exclusion_reason='Synthetic HR excluded employee',exclusion_reference='Synthetic HR exclusion EV-002')
        row=save(row['certification_id'],9,token(row),include)
        row=save(row['certification_id'],10,token(row),exclude)
        def claims(r):
            return dict(roster_ids=sorted(r['roster_scope']['employee_ids']),roster_source_reference=r['roster_source_reference'],
                calendar_source_reference=r['calendar_source_reference'],calendar=r['calendar_configuration'],
                members=[{k:v for k,v in m.items() if k!='certification_id'} for m in r['members']])
        fixture=dict(certifier_ids=[7],claims=copy.deepcopy(claims(row)))
        with patch.object(certs,'authoritative_evidence',return_value=fixture):row=certs.publish(row['certification_id'],token(row),7)
        eid=sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,currency_code,generated_by) VALUES(%s,9,1,'MONTHLY',1000,'PHP',7)",(pid,))
        for day in certs.scheduled_dates(dict(start_date=date(2035,1,1),end_date=date(2035,1,15))):
            sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,'PRESENT',7)",(day,))
        outputs={k:Decimal('0.00') for k in MONEY_FIELDS};outputs.update({k:0 for k in COUNT_FIELDS})
        outputs.update(regular_pay=Decimal('456.78'),gross_pay=Decimal('456.78'),net_pay=Decimal('456.78'),
                       scheduled_work_days=11,present_days=11)
        # Explicit arbitrary synthetic outputs, NOT results of the production salary formula.
        def verify():
            with connect() as c:
                c.start_transaction();cur=c.cursor(dictionary=True)
                try:return evidence.verify_current(cur,pid,eid)
                finally:c.rollback();cur.close()
        def deny(fn,text=None):
            before=[sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in
                    ('payroll_entries','payroll_calculation_evidence','payroll_certification_events','audit_logs')]
            try:fn()
            except ValueError as err:
                if text:assert text.casefold() in str(err).casefold(),str(err)
            else:raise AssertionError('Expected evidence denial')
            assert before==[sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in
                           ('payroll_entries','payroll_calculation_evidence','payroll_certification_events','audit_logs')]
        deny(lambda:evidence.persist_proposed(pid,eid,outputs,7),'unavailable')
        with patch.object(certs,'authoritative_evidence',return_value=fixture):
            ev=evidence.persist_proposed(pid,eid,outputs,7);stored=verify()
            assert stored['calculation_evidence_id']==ev
            assert json.loads(stored['canonical_evidence'])['outputs']['regular_pay']=='456.78'
            # Production finalization remains v1-only and refuses these synthetic v2 entries.
            from payroll_freshness import verify_calculations
            with connect() as c:
                cur=c.cursor(dictionary=True)
                deny(lambda:verify_calculations(cur,pid),'unverified');c.rollback();cur.close()
            print('PASS synthetic atomic v2 persistence; production finalization remains unchanged')
            deny(lambda:evidence.persist_proposed(periods[1]['payroll_period_id'],eid,outputs,7))
            deny(lambda:evidence.persist_proposed(pid,eid+1000,outputs,7))
            # Failed pointer write rolls the inserted immutable row back too.
            sql("CREATE TRIGGER synthetic_evidence_fail BEFORE UPDATE ON payroll_entries FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic pointer failure'")
            before=sql('SELECT COUNT(*) n FROM payroll_calculation_evidence',fetch=True)
            try:evidence.persist_proposed(pid,eid,outputs,7)
            except mysql.connector.Error:pass
            else:raise AssertionError('Injected rollback expected')
            assert before==sql('SELECT COUNT(*) n FROM payroll_calculation_evidence',fetch=True)
            sql('DROP TRIGGER synthetic_evidence_fail');assert verify()['calculation_evidence_id']==ev
            # Hold a material source change uncommitted; validation must wait
            # on the guard, then observe the committed replacement (not RR history).
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True)
            from payroll_freshness import lock_payroll_inputs
            lock_payroll_inputs(hc)
            hc.execute("UPDATE employees SET hire_date='2020-02-01' WHERE employee_id=9")
            with ThreadPoolExecutor(2) as pool:
                pending=pool.submit(verify);deadline=time.monotonic()+10;waited=False
                while time.monotonic()<deadline:
                    if sql('SELECT COUNT(*) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']:
                        waited=True;break
                    time.sleep(.05)
                assert waited and not pending.done(),'Expected source/validator InnoDB wait'
                held.commit();hc.close();held.close()
                try:pending.result(timeout=10)
                except ValueError as err:assert 'sources changed' in str(err)
                else:raise AssertionError('Validation missed the committed source change')
            edit_employee('2020-01-01');verify()
            print('PASS actual InnoDB source-writer wait and fresh current reads after guard acquisition')
            # An earlier consistent read in a caller's transaction must not hide
            # a committed population change from the later authoritative gate.
            old=connect();old.start_transaction();oc=old.cursor(dictionary=True)
            oc.execute('SELECT employee_id FROM employees ORDER BY employee_id');oc.fetchall()
            with connect() as writer:
                wc=writer.cursor(dictionary=True);lock_payroll_inputs(wc)
                wc.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(11,'EV-NEW','Synthetic','Employee')")
                writer.commit();wc.close()
            try:evidence.verify_current(oc,pid,eid)
            except ValueError as err:assert 'sources changed' in str(err)
            else:raise AssertionError('A pre-guard snapshot concealed a population change')
            finally:old.rollback();oc.close();old.close()
            sql('DELETE FROM employees WHERE employee_id=11');verify()
            print('PASS current population read despite an earlier REPEATABLE READ snapshot')
            for statement,undo in [
                ("UPDATE attendance_records SET status='LATE' WHERE attendance_id=1","UPDATE attendance_records SET status='PRESENT' WHERE attendance_id=1"),
                ("UPDATE employee_compensation SET basic_rate=1001 WHERE compensation_id=1","UPDATE employee_compensation SET basic_rate=1000 WHERE compensation_id=1"),
                ("UPDATE employees SET hire_date='2020-01-02' WHERE employee_id=9","UPDATE employees SET hire_date='2020-01-01' WHERE employee_id=9"),
                ("UPDATE payroll_entries SET net_pay=456.79 WHERE payroll_entry_id=%s"%eid,"UPDATE payroll_entries SET net_pay=456.78 WHERE payroll_entry_id=%s"%eid),
                ("UPDATE payroll_entries SET basic_rate=999 WHERE payroll_entry_id=%s"%eid,"UPDATE payroll_entries SET basic_rate=1000 WHERE payroll_entry_id=%s"%eid)]:
                sql(statement);deny(verify);sql(undo);verify()
            aid=sql("INSERT INTO payroll_adjustments(payroll_entry_id,adjustment_type,adjustment_name,amount,created_by) VALUES(%s,'EARNING','Synthetic',1,7)",(eid,))
            deny(verify);sql('DELETE FROM payroll_adjustments WHERE adjustment_id=%s',(aid,));verify()
            lid=sql("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES('EV-LEAVE',9,1,'2035-01-01','2035-01-01',1,'Synthetic','APPROVED',7)")
            deny(verify,'conflict')
            sql("UPDATE attendance_records SET status='ON_LEAVE' WHERE attendance_date='2035-01-01'")
            # Configure supported paid leave in a NEW immutable policy is out of scope;
            # this fixture's BLOCK rule must reject it, not invent compensation.
            deny(verify,'blocks')
            sql("UPDATE leave_types SET is_paid=0 WHERE leave_type_id=1");deny(verify)
            sql("UPDATE leave_types SET is_paid=1 WHERE leave_type_id=1")
            sql('DELETE FROM leave_requests WHERE leave_request_id=%s',(lid,))
            sql("UPDATE attendance_records SET status='PRESENT' WHERE attendance_date='2035-01-01'");verify()
            # Stored digest tamper detection, without violating append-only history:
            # alter a SELECT result only, not the immutable production table.
            original=evidence.evidence_digest
            with patch.object(evidence,'evidence_digest',return_value='0'*64):deny(verify,'digest')
            assert evidence_digest(json.loads(stored['canonical_evidence']))==stored['evidence_digest']
            print('PASS ownership, rollback, adjustment/output/source drift, leave ambiguity and digest tampering')
            # A changed authoritative scope is not legitimized by a stored hash.
            with patch.object(certs,'authoritative_evidence',return_value=dict(fixture,claims=dict(fixture['claims'],roster_ids=[9]))):
                deny(verify,'Authoritative')
            for pay_type in ('DAILY','HOURLY'):
                sql('UPDATE payroll_entries SET pay_type=%s WHERE payroll_entry_id=%s',(pay_type,eid))
                deny(verify,'snapshot')
            sql("UPDATE payroll_entries SET pay_type='MONTHLY' WHERE payroll_entry_id=%s",(eid,))
            # Every included entry and every explicit exclusion matters.
            extra=sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(%s,10,1,'MONTHLY',1000,7)",(pid,))
            deny(verify,'roster');sql('DELETE FROM payroll_entries WHERE payroll_entry_id=%s',(extra,))
            # A prepared correction does not reactivate any older revision or
            # supersede the currently sealed one until the correction commits.
            replacement=certs.prepare(pid,[9,10],'Synthetic authoritative HR roster EV-004','Synthetic calendar EV-004',7,
                predecessor_id=row['certification_id'],predecessor_token=token(row),
                correction_reason='Synthetic correction',correction_reference='Synthetic case EV-004')
            verify()
            replacement=save(replacement['certification_id'],9,token(replacement),include)
            replacement=save(replacement['certification_id'],10,token(replacement),exclude)
            fixture.clear();fixture.update(certifier_ids=[7],claims=copy.deepcopy(claims(replacement)))
            row=certs.publish(replacement['certification_id'],token(replacement),7)
            deny(verify,'changed')
            ev=evidence.persist_proposed(pid,eid,outputs,7)
            assert verify()['calculation_sequence']==2
            print('PASS complete roster, unsupported pay types and latest sealed correction enforcement')
            # Two writers queue on the same guard; both commits retain immutable
            # evidence, allocate distinct sequences, and leave one correct pointer.
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True)
            lock_payroll_inputs(hc)
            with ThreadPoolExecutor(2) as pool:
                pending=[pool.submit(evidence.persist_proposed,pid,eid,outputs,7) for _ in range(2)]
                deadline=time.monotonic()+10;waited=False
                while time.monotonic()<deadline:
                    if sql('SELECT COUNT(*) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']>=2:
                        waited=True;break
                    time.sleep(.05)
                assert waited and not any(p.done() for p in pending),'Expected two actual evidence writer waits'
                held.commit();hc.close();held.close()
                ids=[p.result(timeout=10) for p in pending]
                assert len(set(ids))==2
            assert verify()['calculation_sequence']==4
            assert sql('SELECT calculation_sequence FROM payroll_calculation_evidence ORDER BY calculation_sequence',fetch=True)==[
                dict(calculation_sequence=n) for n in range(1,5)]
            print('PASS two actual queued evidence writers, immutable sequences and atomic current pointer')
            # Actual guard wait: revocation queues behind verification transaction.
            held=connect();held.start_transaction();hc=held.cursor(dictionary=True)
            evidence.verify_current(hc,pid,eid)
            def revoke():return certs.revoke(row['certification_id'],token(certs.get_certification(row['certification_id'])),7,'Synthetic withdrawal','Synthetic case EV-003')
            with ThreadPoolExecutor(2) as pool:
                pending=pool.submit(revoke)
                deadline=time.monotonic()+10;waited=False
                while time.monotonic()<deadline:
                    if sql('SELECT COUNT(*) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']:
                        waited=True;break
                    time.sleep(.05)
                assert waited and not pending.done(),'Expected actual InnoDB wait'
                held.commit();hc.close();held.close();pending.result(timeout=10)
            deny(verify,'withdrawn')
            deny(lambda:evidence.persist_proposed(pid,eid,outputs,7),'withdrawn')
            print('PASS actual InnoDB guard wait and post-commit revocation revalidation')
        # No production adapter, finalization, UI, authorization or historical rewrites.
        assert certs.authoritative_evidence({},7) is None
        print('SUCCESS: v2 foundation tested only with synthetic sources and isolated MySQL 004-007')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
