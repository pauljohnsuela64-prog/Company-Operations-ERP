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
        from importlib.util import spec_from_file_location,module_from_spec
        import json
        spec=spec_from_file_location('schema006',ROOT/'database/migrations/006_payroll_certification.py')
        migration=module_from_spec(spec);spec.loader.exec_module(migration)
        def upgrade():
            with connect() as connection:migration.upgrade(connection)
        def insert(table,**values):
            columns=','.join('`'+k+'`' for k in values)
            return sql('INSERT INTO '+table+'('+columns+') VALUES('+','.join(['%s']*len(values))+')',tuple(json.dumps(v) if isinstance(v,(dict,list)) else v for v in values.values()))
        def rejects(statement,params=()):
            try:sql(statement,params)
            except mysql.connector.Error as error:
                assert error.errno in (1062,1451,1452,1644,3819),repr(error)
                return
            else:raise AssertionError('Expected SQL rejection: '+statement)
        # Seed only synthetic historical rows before additive upgrade.
        for state in ('DRAFT','PROCESSING','APPROVED','PAID'):
            period=insert('payroll_periods',period_number='LEGACY-'+state,period_name='Legacy '+state,start_date='2025-01-01',end_date='2025-01-15',pay_date='2025-01-16',status=state,created_by=7)
            insert('payroll_entries',payroll_period_id=period,employee_id=9,compensation_id=1,pay_type='MONTHLY',basic_rate='1000',status='PAID' if state=='PAID' else 'APPROVED' if state=='APPROVED' else 'CALCULATED',generated_by=7,calculation_input_version=1,calculation_input_hash='a'*64)
        protected=('payroll_periods','payroll_entries','employee_compensation','payroll_adjustments','audit_logs','permissions','role_permissions','payroll_input_guard','payroll_policy_versions','payroll_policy_activations')
        def snapshot():return {t:sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in protected}
        before=snapshot()
        # No fabricated upgrade of unknown pre-existing version-2 rows.
        incompatible=before['payroll_entries'][0]
        sql('UPDATE payroll_entries SET calculation_input_version=2 WHERE payroll_entry_id=%s',(incompatible['payroll_entry_id'],))
        with patch.object(migration,'_execute_ddl',wraps=migration._execute_ddl) as ddl:
            try:upgrade()
            except RuntimeError as error:assert 'historical evidence is never backfilled' in str(error)
            else:raise AssertionError('Unowned legacy version-2 evidence accepted')
            ddl.assert_not_called()
        sql('UPDATE payroll_entries SET calculation_input_version=1,updated_at=%s WHERE payroll_entry_id=%s',(incompatible['updated_at'],incompatible['payroll_entry_id']))
        assert before==snapshot()
        # Simulate a process failure after a committed additive DDL stage.
        original_ddl=migration._execute_ddl;stages=[]
        def interrupted(cur,statement):
            original_ddl(cur,statement);stages.append(statement)
            if len(stages)==7:raise RuntimeError('Synthetic interrupted DDL')
        with patch.object(migration,'_execute_ddl',side_effect=interrupted):
            try:upgrade()
            except RuntimeError as error:assert 'Synthetic interrupted' in str(error)
            else:raise AssertionError('Expected migration interruption')
        assert len(stages)==7
        upgrade();upgrade()
        after=snapshot()
        for row in after['payroll_entries']:assert row.pop('current_calculation_evidence_id') is None
        assert after==before
        assert all(not sql('SELECT * FROM '+t,fetch=True) for t in migration.TABLES)
        # Old 005 remains rerunnable after 006.
        from payroll_schema_helpers import upgrade_policy_foundation
        upgrade_policy_foundation(connect)
        print('PASS fresh/repeated 006, unchanged legacy states/fingerprints/snapshots/grants and repeatable 004/005')
        cfg=validation.initial_policy();cfg.update(policy_name='Synthetic schema certification',effective_from='2035-01-01')
        for field,schema_def in validation.JSON_RULES.items():
            if schema_def['type']=='object':cfg[field]={k:('BLOCK' if 'BLOCK' in p['enum'] else next(v for v in p['enum'] if v!='UNRESOLVED')) for k,p in schema_def['properties'].items()}
        draft=policies.create_policy(cfg,7)
        policy=policies.approve_policy(draft['policy_version_id'],1,'Synthetic schema approval 006',True,7)
        policies.activate_policy(policy['policy_version_id'],7,'Asia/Manila')
        def period(name,start='2035-01-01',end='2035-01-15',code='A'):
            return insert('payroll_periods',period_number=name,period_name=name,start_date=start,end_date=end,pay_date=end,status='DRAFT',created_by=7,policy_version_id=policy['policy_version_id'],cutoff_code=code)
        p=period('CERT-A');other=period('CERT-B','2035-01-16','2035-01-31','B')
        days=['2035-01-01','2035-01-02'] # Shape-valid only: real calendar verification belongs to 3B.
        schedule=dict(scheduled_dates=days,exceptions=[])
        calendar=dict(timezone='Asia/Manila',working_week_mask=31,**schedule)
        def certificate(pid=p,revision=1,predecessor=None,**changes):
            values=dict(payroll_period_id=pid,policy_version_id=policy['policy_version_id'],revision=revision,predecessor_certification_id=predecessor,cutoff_code='A',start_date='2035-01-01',end_date='2035-01-15',roster_scope=dict(kind='EXPLICIT_EMPLOYEE_ROSTER',employee_ids=[9]),roster_source_reference='Synthetic HR roster',calendar_source_reference='Synthetic calendar',calendar_configuration=calendar,source_digest='a'*64,configuration_digest='b'*64,created_by=7,created_at='2034-12-01 00:00:00')
            values.update(changes);return insert(migration.CERT,**values)
        def member(cid,emp=9,**changes):
            values=dict(certification_id=cid,employee_id=emp,disposition='INCLUDE',eligibility='FULL_CUTOFF',verification_status='VERIFIED',hire_date_snapshot='2020-01-01',employment_status_snapshot='Active',employment_coverage_start='2035-01-01',employment_coverage_end='2035-01-15',employment_reference='Synthetic employment verification',compensation_id=1,basic_rate='1000.00',pay_type='MONTHLY',currency_code='PHP',compensation_effective_date='2026-01-01',compensation_coverage_end='2035-01-15',compensation_reference='Synthetic rate evidence',schedule_evidence=schedule,material_source_digest='c'*64)
            values.update(changes);return insert(migration.MEMBER,**values)
        def seal(cid):return sql("UPDATE payroll_cutoff_certifications SET state='SEALED',certified_by=7,certified_at='2034-12-02 00:00:00',certification_digest=%s WHERE certification_id=%s",('d'*64,cid))
        cid=certificate()
        rejects("UPDATE payroll_cutoff_certifications SET state='SEALED',certified_by=7,certified_at=UTC_TIMESTAMP(6),certification_digest=%s WHERE certification_id=%s",('d'*64,cid))
        member(cid);seal(cid)
        assert len(sql('SELECT * FROM payroll_certification_events WHERE certification_id=%s',(cid,),True))==1
        print('PASS assembly, membership and sealing with transactional CERTIFY history')
        rejects('UPDATE payroll_cutoff_certifications SET source_digest=%s WHERE certification_id=%s',('f'*64,cid))
        rejects('DELETE FROM payroll_cutoff_certifications WHERE certification_id=%s',(cid,))
        rejects('UPDATE payroll_certification_members SET basic_rate=2000 WHERE certification_id=%s',(cid,))
        rejects('DELETE FROM payroll_certification_members WHERE certification_id=%s',(cid,))
        try:member(cid)
        except mysql.connector.Error:pass
        else:raise AssertionError('Sealed member insert allowed')
        for stmt in ("UPDATE payroll_certification_events SET reason='Changed'",'DELETE FROM payroll_certification_events'):
            rejects(stmt)
        rejects("UPDATE payroll_periods SET start_date='2035-01-02' WHERE payroll_period_id=%s",(p,))
        for revision,predecessor in ((1,None),(3,cid),(2,None)):
            try:certificate(revision=revision,predecessor=predecessor)
            except mysql.connector.Error:pass
            else:raise AssertionError('Invalid revision chain accepted')
        replacement=certificate(revision=2,predecessor=cid);member(replacement);seal(replacement)
        assert sql("SELECT replacement_certification_id FROM payroll_certification_events WHERE certification_id=%s AND event_type='SUPERSEDE'",(cid,),True)[0]['replacement_certification_id']==replacement
        insert(migration.EVENT,certification_id=replacement,event_type='REVOKE',actor_id=7,occurred_at='2034-12-03 00:00:00',reason='Synthetic revoked evidence',supporting_reference='Synthetic HR-REVOKE-006')
        assert sql('SELECT MAX(revision) r FROM payroll_cutoff_certifications WHERE payroll_period_id=%s',(p,),True)[0]['r']==2
        entry=insert('payroll_entries',payroll_period_id=p,employee_id=9,compensation_id=1,pay_type='MONTHLY',basic_rate='1000',generated_by=7)
        entry2=insert('payroll_entries',payroll_period_id=other,employee_id=9,compensation_id=1,pay_type='MONTHLY',basic_rate='1000',generated_by=7)
        active=certificate(revision=3,predecessor=replacement);member(active);seal(active)
        payload=dict(format_version=2,inputs={},outputs={})
        def evidence(**changes):
            values=dict(evidence_version=2,payroll_period_id=p,payroll_entry_id=entry,employee_id=9,certification_id=active,calculation_sequence=1,canonical_evidence=payload,rounding_contract='SYNTHETIC_ONLY_NOT_A_CALCULATOR',evidence_digest='e'*64,calculated_by=7,calculated_at='2034-12-02 00:00:00')
            values.update(changes);return insert(migration.EVIDENCE,**values)
        ev=evidence()
        for changes in ({},{'certification_id':cid},{'certification_id':replacement},{'payroll_entry_id':entry2},{'employee_id':42},{'payroll_period_id':other},{'evidence_version':3},{'calculation_sequence':0},{'calculation_sequence':2,'evidence_digest':'z'*64},{'calculation_sequence':2,'canonical_evidence':{'unknown':True}}):
            try:evidence(**changes)
            except mysql.connector.Error:pass
            else:raise AssertionError('Invalid evidence accepted '+str(changes))
        rejects('UPDATE payroll_entries SET current_calculation_evidence_id=%s,calculation_input_version=2,calculation_input_hash=%s WHERE payroll_entry_id=%s',(ev,'e'*64,entry2))
        rejects('UPDATE payroll_entries SET current_calculation_evidence_id=%s,calculation_input_version=2,calculation_input_hash=%s WHERE payroll_entry_id=%s',(ev,'f'*64,entry))
        sql('UPDATE payroll_entries SET current_calculation_evidence_id=%s,calculation_input_version=2,calculation_input_hash=%s WHERE payroll_entry_id=%s',(ev,'e'*64,entry))
        rejects('DELETE FROM payroll_calculation_evidence WHERE calculation_evidence_id=%s',(ev,))
        rejects("UPDATE payroll_calculation_evidence SET rounding_contract='Changed' WHERE calculation_evidence_id=%s",(ev,))
        print('PASS sealed/append-only history, revision chains, supersession/revocation, composite ownership and nullable legacy pointers')
        # Direct SQL constraints under both SQL modes (no company database involved).
        for mode in ('STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION','NO_ENGINE_SUBSTITUTION'):
            options['init_command']="SET SESSION sql_mode='"+mode+"'"
            with connect() as connection:
                cur=connection.cursor();cur.execute('SELECT @@SESSION.sql_mode');assert mode==cur.fetchone()[0];cur.close()
            for bad in ('z'*64,'a'*63,'a'*65,'a'*100,'a'*64+'\n','A'*64):
                try:evidence(calculation_sequence=2,evidence_digest=bad)
                except mysql.connector.Error:pass
                else:raise AssertionError('Invalid digest accepted in '+mode)
            for bad in ({},dict(format_version=3,inputs={},outputs={}),dict(format_version=2,inputs=[],outputs={})):
                try:evidence(calculation_sequence=2,canonical_evidence=bad)
                except mysql.connector.Error:pass
                else:raise AssertionError('Invalid JSON accepted in '+mode)
            # Unresolved included members can exist in assembly, but cannot be sealed.
            assembly=certificate(pid=other,cutoff_code='B',start_date='2035-01-16',end_date='2035-01-31')
            member(assembly,eligibility='UNRESOLVED',verification_status='UNVERIFIED')
            rejects("UPDATE payroll_cutoff_certifications SET state='SEALED',certified_by=7,certified_at='2034-12-02',certification_digest=%s WHERE certification_id=%s",('d'*64,assembly))
            sql('DELETE FROM payroll_certification_members WHERE certification_id=%s',(assembly,))
            sql('DELETE FROM payroll_cutoff_certifications WHERE certification_id=%s',(assembly,))
            print('PASS strict/non-strict digest length/format, JSON and incomplete sealing:',mode)
        options.pop('init_command')
        # An explicit exclusion can preserve absent historical evidence without inventing it.
        sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(10,'SCHEMA-10','Synthetic','Historical')")
        edge=period('CERT-EDGE','2035-02-01','2035-02-15')
        roster=certificate(pid=edge,start_date='2035-02-01',end_date='2035-02-15',roster_scope=dict(kind='EXPLICIT_EMPLOYEE_ROSTER',employee_ids=[9,10]))
        member(roster,employment_coverage_start='2035-02-01',employment_coverage_end='2035-02-15',compensation_coverage_end='2035-02-15')
        for attempt in (lambda:member(roster),lambda:member(roster,emp=10)):
            try:attempt()
            except mysql.connector.Error:pass
            else:raise AssertionError('Duplicate member or mismatched compensation accepted')
        member(roster,emp=10,disposition='EXCLUDE',eligibility='UNRESOLVED',exclusion_reason='HR must resolve historical entitlement separately',exclusion_reference='Synthetic HR-EXCLUDE-006',hire_date_snapshot=None,employment_status_snapshot=None,employment_coverage_start=None,employment_coverage_end=None,employment_reference=None,compensation_id=None,basic_rate=None,pay_type=None,currency_code=None,compensation_effective_date=None,compensation_coverage_end=None,compensation_reference=None)
        seal(roster)
        # A sealed header cannot lose employee identity through a parent UPDATE/DELETE.
        rejects('UPDATE employees SET employee_id=100 WHERE employee_id=9')
        rejects('DELETE FROM employees WHERE employee_id=9')
        rejects('UPDATE payroll_entries SET employee_id=10 WHERE payroll_entry_id=%s',(entry,))
        rejects('DELETE FROM payroll_entries WHERE payroll_entry_id=%s',(entry,))
        print('PASS complete declared roster, explicit historical exclusion, duplicate membership and restrictive parent identity ownership')
        with connect() as connection:
            cur=connection.cursor();cur.execute('SET SESSION foreign_key_checks=0')
            try:migration.upgrade(connection)
            except RuntimeError as error:assert 'foreign_key_checks' in str(error)
            else:raise AssertionError('Disabled integrity checks accepted')
            cur.close()
        # A second upgrade cannot enter while this verified schema is advisory-locked.
        import hashlib
        held=connect();cur=held.cursor()
        lock_name='erp_cert_006_'+hashlib.sha256(schema.encode()).hexdigest()[:32]
        cur.execute('SELECT GET_LOCK(%s,0)',(lock_name,));assert cur.fetchone()[0]==1
        try:
            try:upgrade()
            except RuntimeError as error:assert 'Another migration' in str(error)
            else:raise AssertionError('Concurrent migration accepted')
        finally:cur.execute('SELECT RELEASE_LOCK(%s)',(lock_name,));cur.fetchall();cur.close();held.close()
        # Missing prerequisites and incompatible owned objects are rejected before any DDL.
        sql('DELETE FROM payroll_input_guard WHERE guard_id=1')
        with patch.object(migration,'_execute_ddl',wraps=original_ddl) as ddl:
            try:upgrade()
            except RuntimeError as error:assert 'coordination row' in str(error)
            else:raise AssertionError('Missing guard accepted')
            ddl.assert_not_called()
        sql('INSERT INTO payroll_input_guard VALUES(1)')
        sql('ALTER TABLE payroll_calculation_evidence DROP CHECK chk_pcev_version')
        sql('ALTER TABLE payroll_calculation_evidence ADD CONSTRAINT chk_pcev_version CHECK(evidence_version > 0)')
        with patch.object(migration,'_execute_ddl',wraps=original_ddl) as ddl:
            try:upgrade()
            except RuntimeError as error:assert 'Incompatible' in str(error)
            else:raise AssertionError('Incompatible check accepted')
            ddl.assert_not_called()
        sql('ALTER TABLE payroll_calculation_evidence DROP CHECK chk_pcev_version')
        sql('DROP TRIGGER pcev_delete_006')
        sql('ALTER TABLE payroll_entries DROP FOREIGN KEY fk_entry_evidence_006')
        upgrade();upgrade()
        # Compatible metadata is verified, not inferred merely from object names.
        sql('ALTER TABLE payroll_calculation_evidence MODIFY rounding_contract VARCHAR(41) NOT NULL')
        with patch.object(migration,'_execute_ddl',wraps=original_ddl) as ddl:
            try:upgrade()
            except RuntimeError as error:assert 'Incompatible column' in str(error)
            else:raise AssertionError('Incompatible type accepted')
            ddl.assert_not_called()
        sql('ALTER TABLE payroll_calculation_evidence MODIFY rounding_contract VARCHAR(40) NOT NULL')
        sql('DROP TRIGGER pcev_delete_006')
        sql("CREATE TRIGGER pcev_delete_006 BEFORE DELETE ON payroll_calculation_evidence FOR EACH ROW SET @synthetic_bad_trigger=1")
        with patch.object(migration,'_execute_ddl',wraps=original_ddl) as ddl:
            try:upgrade()
            except RuntimeError as error:assert 'Incompatible trigger' in str(error)
            else:raise AssertionError('Incompatible trigger accepted')
            ddl.assert_not_called()
        sql('DROP TRIGGER pcev_delete_006');upgrade()
        for changes in (dict(state='SEALED',certified_by=7,certified_at='2034-12-02',certification_digest='d'*64),
                        dict(revision=5),dict(cutoff_code='B'),dict(roster_scope=dict(kind='EXPLICIT_EMPLOYEE_ROSTER',employee_ids=[9,9])),
                        dict(calendar_configuration=dict(timezone='UTC',working_week_mask=31,scheduled_dates=days,exceptions=[]))):
            try:certificate(revision=changes.pop('revision',4),predecessor=active,**changes)
            except mysql.connector.Error:pass
            else:raise AssertionError('Invalid header accepted')
        # Required seal events are transactional: a real insert failure undoes sealing.
        failure=certificate(revision=4,predecessor=active);member(failure)
        sql("CREATE TRIGGER fail_certification_event BEFORE INSERT ON payroll_certification_events FOR EACH ROW BEGIN IF NEW.event_type='SUPERSEDE' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic required event failure'; END IF; END")
        try:
            try:seal(failure)
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected event insertion failure')
        finally:sql('DROP TRIGGER fail_certification_event')
        assert sql('SELECT state FROM payroll_cutoff_certifications WHERE certification_id=%s',(failure,),True)[0]['state']=='ASSEMBLY'
        assert not sql('SELECT * FROM payroll_certification_events WHERE certification_id=%s',(failure,),True)
        seal(failure)
        # Direct-SQL revision writers serialize on the actual period row.
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT payroll_period_id FROM payroll_periods WHERE payroll_period_id=%s FOR UPDATE',(p,));cur.fetchall()
        def competing_revision():
            try:return certificate(revision=5,predecessor=failure)
            except mysql.connector.Error as error:
                assert error.errno in (1062,1644);return 'rejected'
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(competing_revision) for _ in range(2)]
            try:
                deadline=time.monotonic()+10
                while sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']<2:
                    assert time.monotonic()<deadline;time.sleep(.05)
            finally:held.commit();cur.close();held.close()
            results=[future.result(timeout=15) for future in futures]
        assert results.count('rejected')==1 and len(sql('SELECT * FROM payroll_cutoff_certifications WHERE payroll_period_id=%s AND revision=5',(p,),True))==1
        print('PASS two observed InnoDB period-lock waiters cannot fork the revision chain')
        upgrade()
        # Existing application formula and valid version-1 finalization remain operational after 006.
        legacy_period=erp.create_payroll_period('006 old workflow',date(2036,1,1),date(2036,1,15),date(2036,1,16),None,7)
        erp.generate_payroll_entries(legacy_period,7)
        for offset in range(15):
            day=date(2036,1,1)+timedelta(days=offset)
            if day.weekday()<5:sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,'PRESENT',7)",(day,))
        erp.calculate_monthly_payroll_period(legacy_period,7)
        for suffix in ('submit','approve','paid'):assert client().post(f'/payroll/periods/{legacy_period}/'+suffix,data={}).status_code==302
        row=sql('SELECT status,net_pay,calculation_input_version,current_calculation_evidence_id FROM payroll_entries WHERE payroll_period_id=%s',(legacy_period,),True)[0]
        assert row['status']=='PAID' and row['net_pay']==500 and row['calculation_input_version']==1 and row['current_calculation_evidence_id'] is None
        print('PASS interruption recovery, prerequisite/incompatible-object preflight, missing FK/check/trigger restoration, event failure rollback and unchanged version-1 payment eligibility')
    print('SUCCESS: migration 006 verified on disposable synthetic MySQL only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
