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
        import payroll_freshness as freshness
        from datetime import timezone
        from decimal import Decimal
        registration=(ROOT/'database/payroll_policy_permissions.sql').read_text()
        registration=re.sub(r'--[^\n]*','',registration)
        prior_grants=sql('SELECT * FROM role_permissions ORDER BY 1,2',fetch=True)
        for _ in range(2):
            for statement in registration.split(';'):
                if statement.strip():sql(statement)
        assert prior_grants==sql('SELECT * FROM role_permissions ORDER BY 1,2',fetch=True)
        assert len(sql("SELECT * FROM permissions WHERE permission_code LIKE 'payroll.policy.%'",fetch=True))==3
        for code in (*validation.PERMISSIONS,'payroll.view'):
            sql('INSERT IGNORE INTO role_permissions SELECT 41,permission_id FROM permissions WHERE permission_code=%s',(code,))
        for uid,rid,name,codes in [
            (11,51,'policy.viewer',('payroll.view',)),
            (12,52,'policy.manager',('payroll.view','payroll.policy.manage')),
            (13,53,'policy.approver',('payroll.view','payroll.policy.approve')),
            (14,54,'policy.activator',('payroll.view','payroll.policy.activate')),
            (15,55,'policy.super',('payroll.view',))]:
            sql('INSERT INTO roles(role_id,role_name) VALUES(%s,%s)',(rid,'Super Admin' if uid==15 else name))
            sql("INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES(%s,%s,%s,'test-only',1)",(uid,rid,name))
            for code in codes:sql('INSERT INTO role_permissions SELECT %s,permission_id FROM permissions WHERE permission_code=%s',(rid,code))
        def as_user(uid):
            c=csrf_client(erp.app)
            row=sql('SELECT * FROM users WHERE user_id=%s',(uid,),True)[0]
            with c.session_transaction() as sess:
                from security_helpers import stamp_session,user_state
                stamp_session(erp.app,sess,user_state(user_id=uid,username=row['username'],role_id=row['role_id']))
            return c

        def config(name='Synthetic policy',effective='2035-01-01',resolved=False):
            value=validation.initial_policy();value.update(policy_name=name,effective_from=effective)
            if resolved:
                for field,schema in validation.JSON_RULES.items():
                    if schema['type']=='object':
                        value[field]={k:('BLOCK' if 'BLOCK' in p['enum'] else next(v for v in p['enum'] if v!='UNRESOLVED')) for k,p in schema['properties'].items()}
            return value
        def create(**kwargs):return policies.create_policy(config(**kwargs),7)
        def path(row,action=''):return f"/payroll/policies/{row['policy_version_id']}"+('/'+action if action else '')
        def rows():
            return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in
                    ('payroll_policy_versions','payroll_policy_activations','payroll_periods','payroll_entries','audit_logs')]
        def reject(fn,contains=None):
            before=rows()
            try:fn()
            except ValueError as error:
                if contains:assert contains.casefold() in str(error).casefold(),str(error)
            else:raise AssertionError('Expected rejected operation')
            assert rows()==before
        def approve(row,reference='Synthetic HR/Finance approval 2035-001'):
            return policies.approve_policy(row['policy_version_id'],row['revision'],reference,True,7)

        viewer=as_user(11);manager=as_user(12);approver=as_user(13);activator=as_user(14)
        for invalid_id in (0,2147483648):
            assert viewer.get(f'/payroll/policies/{invalid_id}').location.endswith('/payroll/policies')
            assert manager.get(f'/payroll/policies/{invalid_id}/edit').location.endswith('/payroll/policies')
        # Actual forms: invalid input stays visible, then a corrected submission commits once.
        fields=validation.form_values(config())
        before=rows();bad=dict(fields,policy_name='x'*101)
        response=manager.post('/payroll/policies/add',data=bad)
        assert response.status_code==200 and 'must not exceed 100' in response.text and 'x'*101 in response.text and rows()==before
        bad=dict(fields,effective_from='2035-01-02');response=manager.post('/payroll/policies/add',data=bad)
        assert response.status_code==200 and '2035-01-02' in response.text and rows()==before
        assert manager.post('/payroll/policies/add',data=fields).status_code==302
        row=policies.list_policies()[0]
        assert row['status']=='DRAFT' and row['revision']==1 and row['created_by']==12
        assert logs()[-1]['action']=='CREATE' and logs()[-1]['entity_id']==str(row['policy_version_id']) and logs()[-1]['user_id']==12
        fields=validation.form_values(row);fields.update(revision='1',policy_name='Reviewed synthetic policy')
        assert manager.post(path(row,'edit'),data=fields).status_code==302
        edited=policies.get_policy(row['policy_version_id']);assert edited['revision']==2
        before=rows();assert manager.post(path(row,'edit'),data=fields).status_code==200 and rows()==before
        assert logs()[-1]['action']=='UPDATE' and logs()[-1]['user_id']==12
        reject(lambda:policies.update_policy(edited['policy_version_id'],2,{k:edited[k] for k in validation.CONFIG_FIELDS},7),'No policy')
        # Approval rejects unresolved rules, placeholders, stale revisions and missing attestation.
        rejected_form=dict(revision='2',approval_reference='HR-001',confirm_approval='yes')
        before=rows();response=approver.post(path(edited,'approve'),data=rejected_form)
        assert response.status_code==200 and 'UNRESOLVED' in response.text and 'HR-001' in response.text and rows()==before
        ready=create(name='Ready for approval',resolved=True)
        for ref,confirmed,revision in [('',True,1),('pending',True,1),('x'*256,True,1),('HR-001',False,1),('HR-001',True,99)]:
            reject(lambda:policies.approve_policy(ready['policy_version_id'],revision,ref,confirmed,7))
        assert approver.post(path(ready,'approve'),data=dict(revision='1',approval_reference='HR/FIN-2035-001',confirm_approval='yes')).status_code==302
        ready=policies.get_policy(ready['policy_version_id']);validation.verify_configuration_hash(ready)
        assert ready['approved_by']==13 and ready['revision']==2
        assert logs()[-1]['action']=='APPROVE' and logs()[-1]['user_id']==13
        before=rows();assert approver.post(path(ready,'approve'),data=dict(revision='1',approval_reference='HR/FIN-2035-001',confirm_approval='yes')).status_code==200 and rows()==before
        reject(lambda:policies.update_policy(ready['policy_version_id'],2,config(name='Illegal edit',resolved=True),7),'immutable')
        assert activator.post(path(ready,'activate'),data={'confirm_activation':'yes'}).status_code==302
        assert logs()[-1]['action']=='ACTIVATE' and logs()[-1]['user_id']==14
        before=rows();assert activator.post(path(ready,'activate'),data={'confirm_activation':'yes'}).status_code==302 and rows()==before
        assert policies.activation_history()[0]['activated_by']==14
        print('PASS retained native form values, correction, create/update audit actors, optimistic revisions, explicit approval/hash and separate scheduled activation')

        # Direct forged requests and permission-aware controls use independent permissions.
        another=create(name='Permission target',effective='2035-02-01',resolved=True)
        mutations=[('/payroll/policies/add',validation.form_values(config())),
                   (path(another,'edit'),dict(validation.form_values(config()),revision='1')),
                   (path(another,'approve'),dict(revision='1',approval_reference='HR-002',confirm_approval='yes')),
                   (path(ready,'activate'),dict(confirm_activation='yes'))]
        before=rows()
        for uid in (11,15):
            for endpoint,data in mutations:
                assert as_user(uid).post(endpoint,data=data).location.endswith('/dashboard')
        for endpoint,data in mutations:
            assert erp.app.test_client().post(endpoint,data=data).status_code==400
        assert rows()==before
        html=viewer.get(path(another)).text
        assert 'Edit Draft' not in html and 'Approve Policy</button>' not in html and 'Schedule Activation</button>' not in html
        assert 'Payroll Policies' in viewer.get('/payroll/policies').text
        assert 'Create Draft' not in viewer.get('/payroll/policies').text
        assert 'Edit Draft' in manager.get(path(another)).text and 'Approve Policy</button>' not in manager.get(path(another)).text
        assert 'Approve Policy</button>' in approver.get(path(another)).text and 'Edit Draft' not in approver.get(path(another)).text
        revoked_approver=as_user(13)
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=53 AND p.permission_code='payroll.policy.approve'")
        before=rows()
        assert revoked_approver.post(path(another,'approve'),data=dict(revision='1',approval_reference='HR-003',confirm_approval='yes')).location.endswith('/dashboard')
        assert rows()==before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=54 AND p.permission_code='payroll.policy.activate'")
        assert activator.post(path(ready,'activate'),data={'confirm_activation':'yes'}).location.endswith('/dashboard')
        assert rows()==before
        sql("INSERT INTO role_permissions SELECT 54,permission_id FROM permissions WHERE permission_code='payroll.policy.activate'")
        active_session=as_user(12)
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=52 AND p.permission_code='payroll.policy.manage'")
        before=rows();assert active_session.post('/payroll/policies/add',data=validation.form_values(config())).location.endswith('/dashboard') and rows()==before
        sql('UPDATE users SET is_active=0 WHERE user_id=14')
        assert activator.post(path(another,'activate'),data={'confirm_activation':'yes'}).location.endswith('/login')
        assert rows()==before
        print('PASS viewer/manager/approver/activator controls, Super Admin without new grants, forged POSTs, CSRF, same-session revocation and disabled accounts')

        # Activation prerequisites and append-only effective schedule.
        reject(lambda:policies.activate_policy(another['policy_version_id'],7,'Asia/Manila'),'APPROVED')
        earlier=approve(create(name='Earlier schedule',effective='2034-12-16',resolved=True))
        reject(lambda:policies.activate_policy(earlier['policy_version_id'],7,'Asia/Manila'),'chronological')
        past=approve(create(name='Past',effective='2020-01-01',resolved=True))
        reject(lambda:policies.activate_policy(past['policy_version_id'],7,'Asia/Manila'),'future')
        another=approve(another)
        reject(lambda:policies.activate_policy(another['policy_version_id'],7,''),'timezone')
        reject(lambda:policies.activate_policy(another['policy_version_id'],7,'Invalid/Zone'),'timezone')
        # A genuine legacy matching-looking hash is not sufficient for activation.
        legacy=create(name='Synthetic old approved hash',effective='2035-01-16',resolved=True)
        sql("UPDATE payroll_policy_versions SET status='APPROVED',revision=2,approved_by=7,approved_at=NOW(6),approval_reference='Legacy HR-001',configuration_hash=%s WHERE policy_version_id=%s",('a'*64,legacy['policy_version_id']))
        reject(lambda:policies.activate_policy(legacy['policy_version_id'],7,'Asia/Manila'),'hash')
        # Pinned periods are protected; unassigned legacy references remain untouched.
        p=sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by,policy_version_id,cutoff_code) VALUES('PINNED','Pinned future','2035-02-01','2035-02-15','2035-02-16','DRAFT',7,%s,'A')",(ready['policy_version_id'],))
        reject(lambda:policies.activate_policy(another['policy_version_id'],7,'Asia/Manila'),'non-cancelled')
        sql("UPDATE payroll_periods SET status='CANCELLED' WHERE payroll_period_id=%s",(p,))
        policies.activate_policy(another['policy_version_id'],7,'Asia/Manila')
        assert sql('SELECT policy_version_id FROM payroll_periods WHERE payroll_period_id=%s',(p,),True)[0]['policy_version_id']==ready['policy_version_id']
        print('PASS unresolved/legacy hash/date/timezone rejection, append ordering, pinned-period protection and cancelled-history preservation')
        with patch.object(validation,'company_today',return_value=date(2035,1,15)):
            assert 'Active' in viewer.get('/payroll/policies').text
        with patch.object(validation,'company_today',return_value=date(2035,2,1)):
            page=viewer.get('/payroll/policies').text
            assert 'Superseded' in page and 'Active' in page

        def race(first,second):
            held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
            def run(fn):
                try:return fn()
                except ValueError:return 'rejected'
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(run,fn) for fn in (first,second)]
                    try:
                        deadline=time.monotonic()+8
                        while sql("SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) AS n FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0]['n']<2:
                            assert time.monotonic()<deadline;time.sleep(.05)
                    finally:held.commit()
                    return [f.result(timeout=15) for f in futures]
            finally:cur.close();held.close()
        concurrent=create(name='Concurrent edits',effective='2035-03-01',resolved=True)
        result=race(lambda:policies.update_policy(concurrent['policy_version_id'],1,config(name='Edit A',effective='2035-03-01',resolved=True),7),
                    lambda:policies.update_policy(concurrent['policy_version_id'],1,config(name='Edit B',effective='2035-03-01',resolved=True),7))
        assert sum(isinstance(r,dict) for r in result)==1 and result.count('rejected')==1
        assert policies.get_policy(concurrent['policy_version_id'])['revision']==2
        concurrent=approve(policies.get_policy(concurrent['policy_version_id']))
        before=len(logs());result=race(lambda:client().post(path(concurrent,'activate'),data={'confirm_activation':'yes'}),
                                      lambda:client().post(path(concurrent,'activate'),data={'confirm_activation':'yes'}))
        assert all(r.status_code==302 for r in result) and len(logs())==before+1
        a=approve(create(name='Same date A',effective='2035-04-01',resolved=True));b=approve(create(name='Same date B',effective='2035-04-01',resolved=True))
        before=len(logs());result=race(lambda:client().post(path(a,'activate'),data={'confirm_activation':'yes'}),lambda:client().post(path(b,'activate'),data={'confirm_activation':'yes'}))
        assert all(r.status_code==302 for r in result) and len(logs())==before+1
        result=race(lambda:create(name='Concurrent version A'),lambda:create(name='Concurrent version B'))
        assert len({r['version_number'] for r in result})==2
        review=create(name='Concurrent review',effective='2038-01-01',resolved=True)
        result=race(lambda:approve(review),lambda:policies.update_policy(review['policy_version_id'],1,config(name='Edited during review',effective='2038-01-01',resolved=True),7))
        assert sum(isinstance(r,dict) for r in result)==1 and result.count('rejected')==1
        reviewed=policies.get_policy(review['policy_version_id'])
        if reviewed['status']=='APPROVED':validation.verify_configuration_hash(reviewed)
        else:assert reviewed['status']=='DRAFT' and reviewed['configuration_hash'] is None
        print('PASS five observed two-writer InnoDB races: stale edit, edit/approval, duplicate/same-date activation and unique version allocation; one success audit per activation')

        # Actual SQL failures and audit outages exercise independent commit boundaries.
        before=rows()
        sql("CREATE TRIGGER reject_policy_insert BEFORE INSERT ON payroll_policy_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic policy rollback'")
        try:
            try:create(name='Rollback')
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected rollback')
        finally:sql('DROP TRIGGER reject_policy_insert')
        assert rows()==before
        sql("CREATE TRIGGER reject_policy_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit outage'")
        before=len(logs())
        try:
            response=client().post('/payroll/policies/add',data=validation.form_values(config(name='Committed despite audit outage')))
            assert response.status_code==302
        finally:sql('DROP TRIGGER reject_policy_audit')
        assert len(logs())==before and policies.list_policies()[0]['policy_name']=='Committed despite audit outage'
        # Audit failures for UPDATE/APPROVE/ACTIVATE cannot undo any business commit.
        outage=create(name='Audit outage operations',effective='2036-01-01',resolved=True)
        sql("CREATE TRIGGER reject_policy_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit outage'")
        before=len(logs())
        try:
            fields=validation.form_values(config(name='Audit outage updated',effective='2036-01-01',resolved=True));fields['revision']='1'
            assert client().post(path(outage,'edit'),data=fields).status_code==302
            assert client().post(path(outage,'approve'),data=dict(revision='2',approval_reference='Synthetic HR-OUTAGE-001',confirm_approval='yes')).status_code==302
            assert client().post(path(outage,'activate'),data={'confirm_activation':'yes'}).status_code==302
        finally:sql('DROP TRIGGER reject_policy_audit')
        assert policies.get_policy(outage['policy_version_id'])['revision']==3
        assert policies.activation_history()[-1]['policy_version_id']==outage['policy_version_id'] and len(logs())==before
        rollback=create(name='Late rollback',effective='2037-01-01',resolved=True)
        sql("CREATE TRIGGER reject_policy_update AFTER UPDATE ON payroll_policy_versions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic late failure'")
        before=rows()
        try:
            for operation in (
                lambda:policies.update_policy(rollback['policy_version_id'],1,config(name='Failed update',effective='2037-01-01',resolved=True),7),
                lambda:approve(rollback)):
                try:operation()
                except mysql.connector.Error:pass
                else:raise AssertionError('Expected late rollback')
                assert rows()==before
        finally:sql('DROP TRIGGER reject_policy_update')
        rollback=approve(rollback)
        sql("CREATE TRIGGER reject_policy_activation AFTER INSERT ON payroll_policy_activations FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic late activation failure'")
        before=rows()
        try:
            try:policies.activate_policy(rollback['policy_version_id'],7,'Asia/Manila')
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected late activation rollback')
        finally:sql('DROP TRIGGER reject_policy_activation')
        assert rows()==before
        midnight=approve(create(name='Midnight boundary',effective='2039-01-01',resolved=True))
        with patch.object(policies,'company_today',side_effect=[date(2038,12,31),date(2039,1,1)]):
            reject(lambda:policies.activate_policy(midnight['policy_version_id'],7,'Asia/Manila'),'date changed')
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1 FOR UPDATE');cur.fetchall()
        def short_connection():
            connection=connect();c=connection.cursor();c.execute('SET SESSION innodb_lock_wait_timeout=1');c.close();return connection
        before=rows()
        try:
            with patch.object(policies,'get_connection',side_effect=short_connection):
                response=client().post('/payroll/policies/add',data=validation.form_values(config(name='Retained after timeout')))
                assert response.status_code==200 and 'retry' in response.text and 'Retained after timeout' in response.text
        finally:held.rollback();cur.close();held.close()
        assert rows()==before
        assert all('attendance_rules' not in row['description'] and 'HR/FIN-2035-001' not in row['description'] for row in logs())
        print('PASS SQL failure rollback, real audit storage failure isolation and concise policy identity-only success events')
    print('SUCCESS: policy management used migration 004/005 and disposable synthetic MySQL only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()

