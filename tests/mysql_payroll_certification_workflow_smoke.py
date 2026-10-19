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
        row=certs.prepare(pid,[9,10],'Synthetic authoritative HR roster WF-001','Synthetic calendar version WF-001',7)
        reject(lambda:certs.publish(row['certification_id'],token(row),7),'Every declared employee')
        include=dict(disposition='INCLUDE',eligibility='FULL_CUTOFF',verification_status='VERIFIED',employment_coverage_start='2035-01-01',employment_coverage_end='2035-01-15',employment_reference='Synthetic HR full-cutoff WF-001',compensation_coverage_end='2035-01-15',compensation_reference='Synthetic Finance rate WF-001')
        exclude=dict(disposition='EXCLUDE',eligibility='UNRESOLVED',verification_status='VERIFIED',exclusion_reason='Historical entitlement unresolved; HR case required',exclusion_reference='Synthetic historical HR case WF-002')
        row=save(row['certification_id'],9,token(row),include)
        reject(lambda:save(row['certification_id'],10,token(row),dict(exclude,exclusion_reason='')))
        row=save(row['certification_id'],10,token(row),exclude)
        reject(lambda:certs.publish(row['certification_id'],token(row),7),'hire')
        edit_employee('2035-01-05')
        assert certs.review(row['certification_id'])['source_stale']
        row=save(row['certification_id'],9,token(row),include)
        reject(lambda:certs.publish(row['certification_id'],token(row),7),'hire')
        edit_employee('2020-01-01','Inactive')
        row=save(row['certification_id'],9,token(row),include)
        reject(lambda:certs.publish(row['certification_id'],token(row),7),'unavailable')
        # Test-only approved fixture: captured expected source claims, never a production switch.
        def approved_claims(row):
            return dict(roster_ids=sorted(row['roster_scope']['employee_ids']),roster_source_reference=row['roster_source_reference'],calendar_source_reference=row['calendar_source_reference'],calendar=row['calendar_configuration'],members=[{k:v for k,v in m.items() if k!='certification_id'} for m in row['members']])
        fixture=dict(certifier_ids=[7],claims=copy.deepcopy(approved_claims(row)))
        with patch.object(certs,'authoritative_evidence',return_value=dict(fixture,claims=dict(fixture['claims'],roster_ids=[9,10,42]))):
            reject(lambda:certs.publish(row['certification_id'],token(row),7),'Authoritative')
        with patch.object(certs,'authoritative_evidence',return_value=dict(fixture,certifier_ids=[])):
            reject(lambda:certs.publish(row['certification_id'],token(row),7),'authority')
        def path(row,action=''):return '/payroll/certifications/'+str(row['certification_id'])+('/'+action if action else '')
        def publication(row):return client().post(path(row,'publish'),data=dict(token=token(row)))
        with patch.object(certs,'authoritative_evidence',return_value=fixture):
            before=len(logs());assert publication(row).status_code==302
        sealed=certs.get_certification(row['certification_id'])
        assert sealed['state']=='SEALED' and len(logs())==before+1 and logs()[-1]['user_id']==7
        assert [e['event_type'] for e in sealed['events']]==['CERTIFY']
        reject(lambda:save(sealed['certification_id'],9,token(sealed),include),'immutable')
        reject(lambda:certs.publish(sealed['certification_id'],token(sealed),7),'already')
        # Upgrade a real 006 seal without rewriting its evidence or transactional history.
        spec=spec_from_file_location('workflow_007',ROOT/'database/migrations/007_payroll_correction_references.py')
        correction_migration=module_from_spec(spec);spec.loader.exec_module(correction_migration)
        old_seal=copy.deepcopy(sealed)
        for _ in range(2):
            with connect() as connection:correction_migration.upgrade(connection)
        sealed=certs.get_certification(sealed['certification_id'])
        assert sealed['correction_reason'] is None and sealed['correction_reference'] is None
        assert {k:v for k,v in sealed.items() if k not in ('correction_reason','correction_reference')}==old_seal
        # An interrupted trigger replacement resumes without overwriting other objects.
        sql('DROP TRIGGER pcc_seal_events_006')
        with connect() as connection:correction_migration.upgrade(connection)
        assert certs.get_certification(sealed['certification_id'])==sealed
        # Replacement requires explicit reason, reference and current predecessor token.
        reject(lambda:certs.prepare(pid,[9,10],'Synthetic corrected roster WF-003','Synthetic calendar version WF-001',7,predecessor_id=sealed['certification_id'],predecessor_token=token(sealed)))
        replacement=certs.prepare(pid,[9,10],'Synthetic corrected roster WF-003','Synthetic calendar version WF-001',7,predecessor_id=sealed['certification_id'],predecessor_token=token(sealed),correction_reason='Verified correction to roster evidence',correction_reference='Synthetic correction case WF-003')
        replacement=save(replacement['certification_id'],9,token(replacement),include)
        replacement=save(replacement['certification_id'],10,token(replacement),exclude)
        fixture=dict(certifier_ids=[7],claims=approved_claims(replacement))
        # Two real competing POST publications queue at the guard; exactly one succeeds.
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        before=len(logs())
        with patch.object(certs,'authoritative_evidence',return_value=fixture),ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(publication,replacement) for _ in range(2)]
            try:
                deadline=time.monotonic()+10
                while sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']<2:
                    assert time.monotonic()<deadline;time.sleep(.05)
            finally:held.commit();cur.close();held.close()
            assert all(f.result(timeout=15).status_code==302 for f in futures)
        assert len(logs())==before+2 # CERTIFY plus SUPERSEDE, once each.
        assert [(e['action'],e['entity_id'],e['user_id']) for e in logs()[-2:]]==[('CERTIFY',str(replacement['certification_id']),7),('SUPERSEDE',str(sealed['certification_id']),7)]
        assert all('Synthetic Finance rate WF-001' not in e['description'] for e in logs())
        old=certs.get_certification(sealed['certification_id'])
        event=next(e for e in old['events'] if e['event_type']=='SUPERSEDE')
        assert event['reason']=='Verified correction to roster evidence' and event['supporting_reference']=='Synthetic correction case WF-003'
        replacement=certs.get_certification(replacement['certification_id'])
        response=client().post(path(replacement,'revoke'),data=dict(token=token(replacement),reason='Synthetic source approval withdrawn',supporting_reference='Synthetic revocation WF-004'))
        assert response.status_code==302
        revoked=certs.get_certification(replacement['certification_id'])
        reject(lambda:certs.revoke(revoked['certification_id'],token(revoked),7,'Duplicate revocation','Synthetic WF-004'))
        assert certs.list_certifications(pid)[0]['certification_id']==replacement['certification_id']
        assert any(e['event_type']=='REVOKE' for e in revoked['events']) and any(e['event_type']=='SUPERSEDE' for e in certs.get_certification(sealed['certification_id'])['events'])
        print('PASS missing/unknown/mid-hire eligibility, historical exclusions, explicit production source blocker, synthetic publication, real concurrent publication, corrected history, revocation and no fallback')
        assert certs.current_certification(pid)['certification_id']==revoked['certification_id']
        assert not certs.current_certification(pid)['source_consistent']
        # Validate coverage and known exceptions without inventing source authenticity.
        other=periods[1]['payroll_period_id']
        edge=certs.prepare(other,[9,10],'Synthetic edge roster WF-005','Synthetic edge calendar WF-005',7,
                           calendar_exceptions=[dict(date='2035-01-20',kind='HOLIDAY',source_reference='Synthetic holiday source WF-005')])
        include_b=dict(include,employment_coverage_start='2035-01-16',employment_coverage_end='2035-01-31',compensation_coverage_end='2035-01-31')
        edge=save(edge['certification_id'],9,token(edge),include_b);edge=save(edge['certification_id'],10,token(edge),exclude)
        reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'Calendar')
        edge=certs.update_scope(edge['certification_id'],token(edge),[9,10],edge['roster_source_reference'],edge['calendar_source_reference'])
        edge=certs.save_member(edge['certification_id'],9,token(edge),include_b,certs.digest(certs.get_employee_source(9)),[dict(date='2035-01-20',kind='SCHEDULE_EXCEPTION',source_reference='Synthetic schedule WF-005')])
        reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'schedule')
        edge=save(edge['certification_id'],9,token(edge),dict(include_b,employment_coverage_end=''))
        reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'cover the full cutoff')
        compensation.update_employee_compensation(1,'MONTHLY','1000','2035-01-17',None,7)
        edge=save(edge['certification_id'],9,token(edge),include_b)
        reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'cover the full cutoff')
        for unsupported in ('DAILY','HOURLY'):
            compensation.update_employee_compensation(1,unsupported,'1000','2026-01-01',None,7)
            edge=save(edge['certification_id'],9,token(edge),include_b)
            reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'MONTHLY/PHP')
        compensation.update_employee_compensation(1,'MONTHLY','1000','2026-01-01',None,7)
        edge=save(edge['certification_id'],9,token(edge),include_b)
        # Known employment does not fabricate a missing compensation record.
        historic=employees.get_employee_by_id(10)
        employees.update_employee(10,historic['employee_number'],historic['department_id'],historic['first_name'],historic['middle_name'],historic['last_name'],historic['email'],historic['phone'],historic['job_title'],'2020-01-01',historic['employment_status'])
        edge=save(edge['certification_id'],10,token(edge),include_b)
        reject(lambda:certs.publish(edge['certification_id'],token(edge),7),'compensation')
        employees.update_employee(10,historic['employee_number'],historic['department_id'],historic['first_name'],historic['middle_name'],historic['last_name'],historic['email'],historic['phone'],historic['job_title'],None,historic['employment_status'])
        edge=save(edge['certification_id'],10,token(edge),exclude)
        fixture_b=dict(certifier_ids=[7],claims=approved_claims(edge))
        sql("CREATE TRIGGER wf_required_failure BEFORE INSERT ON payroll_certification_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic required event outage'")
        before=len(logs())
        try:
            with patch.object(certs,'authoritative_evidence',return_value=fixture_b):assert publication(edge).status_code==302
        finally:sql('DROP TRIGGER wf_required_failure')
        assert certs.get_certification(edge['certification_id'])['state']=='ASSEMBLY' and len(logs())==before
        sql("CREATE TRIGGER wf_audit_outage BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic central audit outage'")
        try:
            with patch.object(certs,'authoritative_evidence',return_value=fixture_b):assert publication(edge).status_code==302
        finally:sql('DROP TRIGGER wf_audit_outage')
        edge=certs.get_certification(edge['certification_id'])
        assert edge['state']=='SEALED' and [e['event_type'] for e in edge['events']]==['CERTIFY'] and len(logs())==before
        sql("CREATE TRIGGER wf_required_failure BEFORE INSERT ON payroll_certification_events FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic required revocation failure'")
        try:
            response=client().post(path(edge,'revoke'),data=dict(token=token(edge),reason='Synthetic revocation evidence',supporting_reference='Synthetic WF-006'))
            assert response.status_code==302
        finally:sql('DROP TRIGGER wf_required_failure')
        assert certs.get_certification(edge['certification_id'])==edge and len(logs())==before
        sql("CREATE TRIGGER wf_audit_outage BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic central audit outage'")
        try:assert client().post(path(edge,'revoke'),data=dict(token=token(edge),reason='Synthetic revocation evidence',supporting_reference='Synthetic WF-006')).status_code==302
        finally:sql('DROP TRIGGER wf_audit_outage')
        edge=certs.get_certification(edge['certification_id']);assert any(e['event_type']=='REVOKE' for e in edge['events']) and len(logs())==before
        print('PASS coverage/pay-type/calendar/schedule blockers, required business-event rollback and postcommit audit outage isolation for publication/revocation')
        # Supersession remains committed even if both best-effort central audit inserts fail.
        audit_replacement=certs.prepare(other,[9,10],'Synthetic audit replacement WF-006A','Synthetic calendar WF-006A',7,
            predecessor_id=edge['certification_id'],predecessor_token=token(edge),correction_reason='Explicit audit-isolation correction',correction_reference='Synthetic correction WF-006A')
        audit_replacement=save(audit_replacement['certification_id'],9,token(audit_replacement),include_b)
        audit_replacement=save(audit_replacement['certification_id'],10,token(audit_replacement),exclude)
        before=len(logs());fixture_audit=dict(certifier_ids=[7],claims=approved_claims(audit_replacement))
        sql("CREATE TRIGGER wf_audit_outage BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic supersession audit outage'")
        try:
            with patch.object(certs,'authoritative_evidence',return_value=fixture_audit):assert publication(audit_replacement).status_code==302
        finally:sql('DROP TRIGGER wf_audit_outage')
        assert len(logs())==before and certs.get_certification(audit_replacement['certification_id'])['state']=='SEALED'
        assert any(e['event_type']=='SUPERSEDE' for e in certs.get_certification(edge['certification_id'])['events'])
        edge=certs.get_certification(audit_replacement['certification_id'])
        # Actual Employee and Compensation source writers wait before material row locks.
        def race_source(row,writer):
            held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
            fixture=dict(certifier_ids=[7],claims=approved_claims(row))
            with patch.object(certs,'authoritative_evidence',return_value=fixture),ThreadPoolExecutor(2) as pool:
                futures=[pool.submit(publication,row),pool.submit(writer)]
                try:
                    deadline=time.monotonic()+10
                    while sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']<2:
                        assert time.monotonic()<deadline;time.sleep(.05)
                finally:held.commit();cur.close();held.close()
                assert futures[0].result(timeout=15).status_code==302;futures[1].result(timeout=15)
            assert certs.review(row['certification_id'])['source_stale']
        coordinated=certs.prepare(other,[9,10],'Synthetic coordinated roster WF-007','Synthetic calendar WF-007',7,
            predecessor_id=edge['certification_id'],predecessor_token=token(edge),correction_reason='Reverify source coordination',correction_reference='Synthetic correction WF-007')
        coordinated=save(coordinated['certification_id'],9,token(coordinated),include_b);coordinated=save(coordinated['certification_id'],10,token(coordinated),exclude)
        race_source(coordinated,lambda:edit_employee('2021-01-01','Inactive'))
        edit_employee('2020-01-01','Inactive')
        coordinated=certs.get_certification(coordinated['certification_id'])
        if coordinated['state']=='SEALED':
            coordinated=certs.prepare(other,[9,10],'Synthetic compensation coordination WF-008','Synthetic calendar WF-008',7,
                predecessor_id=coordinated['certification_id'],predecessor_token=token(coordinated),correction_reason='Reverify compensation source',correction_reference='Synthetic correction WF-008')
            coordinated=save(coordinated['certification_id'],9,token(coordinated),include_b);coordinated=save(coordinated['certification_id'],10,token(coordinated),exclude)
        race_source(coordinated,lambda:compensation.update_employee_compensation(1,'MONTHLY','2000','2026-01-01',None,7))
        compensation.update_employee_compensation(1,'MONTHLY','1000','2026-01-01',None,7)
        # Profile-only edits and compensation notes complete while the guard is held.
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        try:
            with ThreadPoolExecutor(2) as pool:
                tasks=[pool.submit(compensation.update_employee_compensation,1,'MONTHLY','1000','2026-01-01','Nonmaterial synthetic notes',7)]
                e=employees.get_employee_by_id(9)
                tasks.append(pool.submit(employees.update_employee,9,e['employee_number'],e['department_id'],'Renamed',e['middle_name'],e['last_name'],e['email'],e['phone'],e['job_title'],e['hire_date'],e['employment_status']))
                for task in tasks:task.result(timeout=4)
        finally:held.rollback();cur.close();held.close()
        print('PASS two observed source/publication InnoDB races, stale source detection and no unnecessary guard on profile/notes edits')
        # Native forms retain validation failures; stale source forms cannot silently refresh rates.
        missing=client().post(f'/payroll/periods/{pid}/certifications/prepare',data=dict(employee_ids=['9'],roster_reference='pending',calendar_reference='Retained calendar reference'))
        assert missing.status_code==200 and 'Retained calendar reference' in missing.text
        newperiod=generation.generate_month(2035,2,'2035-02-15','2035-02-28',7)[0]['payroll_period_id']
        draft=certs.prepare(newperiod,[9],'Synthetic rollback roster WF-009','Synthetic calendar WF-009',7)
        include_c=dict(include,employment_coverage_start='2035-02-01',employment_coverage_end='2035-02-15',compensation_coverage_end='2035-02-15')
        draft=save(draft['certification_id'],9,token(draft),include_c)
        reviewed_source=certs.digest(certs.get_employee_source(9));compensation.update_employee_compensation(1,'MONTHLY','1001','2026-01-01',None,7)
        reject(lambda:certs.save_member(draft['certification_id'],9,token(draft),include_c,reviewed_source),'form opened')
        compensation.update_employee_compensation(1,'MONTHLY','1000','2026-01-01',None,7)
        sql("CREATE TRIGGER wf_member_failure BEFORE INSERT ON payroll_certification_members FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic late member failure'")
        try:
            response=client().post(path(draft,'members/9'),data=dict(include_c,token=token(draft),source_token=certs.digest(certs.get_employee_source(9))))
            assert response.status_code==200 and 'Unable to save evidence' in response.text
        finally:sql('DROP TRIGGER wf_member_failure')
        assert certs.get_certification(draft['certification_id'])==draft
        assert 'No compensation' not in client().get(path(draft,'members/9')).text
        print('PASS retained native values, stale-source token rejection and late member failure rollback without lost history')
        # Source changes retain Payroll snapshots; profile/notes changes do not invalidate evidence.
        assert not certs.review(replacement['certification_id'])['source_stale']
        compensation.update_employee_compensation(1,'MONTHLY','2000','2026-01-01',None,7)
        assert certs.review(replacement['certification_id'])['source_stale']
        assert not sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(pid,),True)
        # No version-1 cutover: old manual periods still calculate/approve/pay with snapshots.
        edit_employee('2020-01-01','Active')
        legacy=erp.create_payroll_period('Workflow old payment compatibility',date(2037,1,5),date(2037,1,9),date(2037,1,10),None,7)
        erp.generate_payroll_entries(legacy,7)
        compensation.update_employee_compensation(1,'MONTHLY','3000','2026-01-01',None,7)
        for offset in range(5):
            day=date(2037,1,5)+timedelta(days=offset)
            if day.weekday()<5:sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,'PRESENT',7)",(day,))
        erp.calculate_monthly_payroll_period(legacy,7)
        for action in ('submit','approve','paid'):assert client().post(f'/payroll/periods/{legacy}/'+action,data={}).status_code==302
        record=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(legacy,),True)[0]
        assert record['status']=='PAID' and record['basic_rate']==2000 and record['net_pay']==1000 and record['calculation_input_version']==1 and record['current_calculation_evidence_id'] is None
        print('PASS 007 historical-seal preservation/recovery and unchanged old manual version-1 snapshot/payment workflow')
        # Concurrent corrections cannot branch the same immutable predecessor.
        base=certs.get_certification(replacement['certification_id'])
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        def correction():
            try:return certs.prepare(pid,[9,10],'Synthetic raced correction WF-010','Synthetic calendar WF-010',7,predecessor_id=base['certification_id'],predecessor_token=token(base),correction_reason='Concurrent correction review',correction_reference='Synthetic case WF-010')
            except ValueError:return 'rejected'
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(correction) for _ in range(2)]
            try:
                deadline=time.monotonic()+10
                while sql('SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']<2:
                    assert time.monotonic()<deadline;time.sleep(.05)
            finally:held.commit();cur.close();held.close()
            results=[f.result(timeout=15) for f in futures]
        assert results.count('rejected')==1
        assert certs.current_certification(pid)['certification_id']==base['certification_id']
        print('PASS concurrent correction preparation creates one branch only, exact central audit identities and no historical fallback')
        # Permission and CSRF enforcement with fresh real database authorization.
        for action in ('publish','revoke','correct','edit'):
            assert client(False).post(path(replacement,action),data={}).status_code==302
        assert erp.app.test_client().post(path(replacement,'publish'),data={}).status_code==400
        persistent=client()
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=41 AND permission_code='payroll.certification.revoke'")
        assert persistent.post(path(replacement,'revoke'),data={}).location.endswith('/dashboard')
        for code in ('payroll.view','payroll.process'):
            sql('INSERT IGNORE INTO role_permissions SELECT 43,permission_id FROM permissions WHERE permission_code=%s',(code,))
        preparer=client(False)
        detail=preparer.get(path(draft));assert detail.status_code==200 and 'Publish Certification' not in detail.text
        assert preparer.get(path(draft,'members/9')).status_code==200
        for action in ('publish','revoke'):assert preparer.post(path(draft,action),data={}).location.endswith('/dashboard')
        sql('UPDATE users SET is_active=0 WHERE user_id=7')
        assert client().post(path(replacement,'publish'),data={}).location.endswith('/login')
        print('PASS new permission registration without grants, fresh revocation, disabled accounts and CSRF')
    print('SUCCESS: certification workflow used isolated synthetic MySQL, migrations 004-007; production publication remains unavailable')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()
