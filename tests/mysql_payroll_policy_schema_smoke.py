r"""Explicit disposable-server smoke test; never connects to configured ERP databases.

Run: .venv\Scripts\python.exe tests/mysql_payroll_policy_schema_smoke.py
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

        from importlib.util import spec_from_file_location, module_from_spec
        from decimal import Decimal
        def load(number):
            name = '004_payroll_freshness.py' if number==4 else '005_payroll_policy.py'
            spec=spec_from_file_location('migration_'+str(number),ROOT/'database/migrations'/name)
            module=module_from_spec(spec);spec.loader.exec_module(module);return module
        previous=load(4); migration=load(5)
        def upgrade():
            with connect() as connection:migration.upgrade(connection)
        with connect() as connection:previous.upgrade(connection)
        # Representative legacy rows are preserved byte-for-byte except new NULL columns.
        for status in ('DRAFT','PROCESSING','APPROVED','PAID'):
            p=sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES(%s,%s,%s,%s,%s,%s,7)",
                  ('OLD-'+status,'Old '+status,'2025-01-01','2025-01-15','2025-01-16',status))
            sql("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,regular_pay,gross_pay,net_pay,status,generated_by,calculation_input_version,calculation_input_hash) VALUES(%s,9,1,'MONTHLY',1000,500,500,500,%s,7,1,%s)",
                (p,'APPROVED' if status=='APPROVED' else 'PAID' if status=='PAID' else 'CALCULATED','a'*64))
        sql("INSERT INTO audit_logs(user_id,username,module,action,entity_type,entity_id) VALUES(7,'acting.user','PAYROLL','LEGACY','PAYROLL_PERIOD','1')")
        preserved=('payroll_periods','payroll_entries','employee_compensation','payroll_adjustments','audit_logs','permissions','role_permissions')
        def snapshot():return {t:sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in preserved}
        before=snapshot()
        upgrade()
        upgrade()
        after=snapshot()
        assert all(r['policy_version_id'] is None and r['cutoff_code'] is None for r in after['payroll_periods'])
        after['payroll_periods']=[{k:v for k,v in r.items() if k not in ('policy_version_id','cutoff_code')} for r in after['payroll_periods']]
        assert after==before
        assert sql('SELECT * FROM payroll_policy_versions',fetch=True)==[]
        assert sql('SELECT * FROM payroll_policy_activations',fetch=True)==[]
        print('PASS fresh/repeated 005, unchanged legacy payroll/compensation/evidence/audits/permissions and NULL policy references')

        def rejected(operation, kind=Exception, contains=None):
            try:operation()
            except kind as error:
                if contains:assert contains.lower() in str(error).lower(),str(error)
            else:raise AssertionError('Expected rejection')

        held=connect(); held_cursor=held.cursor()
        lock_name='erp_policy_005_'+migration.hashlib.sha256(schema.encode()).hexdigest()[:32]
        held_cursor.execute('SELECT GET_LOCK(%s,0)',(lock_name,));assert held_cursor.fetchone()[0]==1
        try:rejected(upgrade,RuntimeError,'Another migration')
        finally:
            held_cursor.execute('SELECT RELEASE_LOCK(%s)',(lock_name,));held_cursor.fetchall();held_cursor.close();held.close()

        # Prerequisite failures must not repair or recreate 004 behind the operator's back.
        sql('RENAME TABLE payroll_input_guard TO fixture_saved_guard')
        rejected(upgrade,RuntimeError,'004')
        sql('RENAME TABLE fixture_saved_guard TO payroll_input_guard')
        sql('DELETE FROM payroll_input_guard WHERE guard_id=1')
        rejected(upgrade,RuntimeError,'coordination row')
        assert sql('SELECT * FROM payroll_input_guard',fetch=True)==[]
        sql('INSERT INTO payroll_input_guard VALUES(1)')
        sql('ALTER TABLE payroll_input_guard ENGINE=MyISAM')
        rejected(upgrade,RuntimeError,'InnoDB')
        sql('ALTER TABLE payroll_input_guard ENGINE=InnoDB')
        sql('ALTER TABLE payroll_entries RENAME COLUMN calculation_input_version TO old_evidence_version')
        rejected(upgrade,RuntimeError,'004')
        sql('ALTER TABLE payroll_entries RENAME COLUMN old_evidence_version TO calculation_input_version')
        sql('ALTER TABLE payroll_entries MODIFY calculation_input_hash CHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NULL')
        rejected(upgrade,RuntimeError,'calculation_input_hash')
        sql('ALTER TABLE payroll_entries MODIFY calculation_input_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL')
        upgrade()
        print('PASS missing/invalid migration 004 guard, engine, evidence column and collation fail closed without repair')

        # Incompatible existing objects are never silently replaced.
        sql('ALTER TABLE payroll_policy_versions MODIFY policy_name VARCHAR(99) NOT NULL')
        rejected(upgrade,RuntimeError,'column')
        assert sql("SELECT CHARACTER_MAXIMUM_LENGTH AS n FROM information_schema.columns WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='payroll_policy_versions' AND COLUMN_NAME='policy_name'",fetch=True)[0]['n']==99
        sql('ALTER TABLE payroll_policy_versions MODIFY policy_name VARCHAR(100) NOT NULL')
        sql('ALTER TABLE payroll_policy_versions DROP INDEX uq_ppv_number, ADD INDEX uq_ppv_number(version_number)')
        rejected(upgrade,RuntimeError,'index')
        sql('ALTER TABLE payroll_policy_versions DROP INDEX uq_ppv_number')
        upgrade()
        sql('ALTER TABLE payroll_policy_versions DROP CHECK chk_ppv_name, ADD CONSTRAINT chk_ppv_name CHECK(1=1)')
        rejected(upgrade,RuntimeError,'check')
        sql('ALTER TABLE payroll_policy_versions DROP CHECK chk_ppv_name')
        upgrade()
        sql('ALTER TABLE payroll_policy_versions ALTER CHECK chk_ppv_name NOT ENFORCED')
        rejected(upgrade,RuntimeError,'Unenforced check')
        sql('ALTER TABLE payroll_policy_versions ALTER CHECK chk_ppv_name ENFORCED')
        sql('ALTER TABLE payroll_policy_activations DROP FOREIGN KEY fk_ppa_actor')
        sql('ALTER TABLE payroll_policy_activations ADD CONSTRAINT fk_ppa_actor FOREIGN KEY(activated_by) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE RESTRICT')
        rejected(upgrade,RuntimeError,'foreign key')
        sql('ALTER TABLE payroll_policy_activations DROP FOREIGN KEY fk_ppa_actor')
        upgrade()
        sql('DROP TRIGGER ppv_before_update')
        sql('CREATE TRIGGER ppv_before_update BEFORE UPDATE ON payroll_policy_versions FOR EACH ROW BEGIN SET @policy_fixture=1; END')
        rejected(upgrade,RuntimeError,'trigger')
        sql('DROP TRIGGER ppv_before_update')
        upgrade()
        sql('ALTER TABLE payroll_policy_versions ADD COLUMN unexpected INT NULL')
        rejected(upgrade,RuntimeError,'Unexpected columns')
        sql('ALTER TABLE payroll_policy_versions DROP COLUMN unexpected')
        upgrade()
        sql('ALTER TABLE payroll_periods ADD CONSTRAINT unexpected_policy_check CHECK(policy_version_id IS NULL OR policy_version_id > 0)')
        rejected(upgrade,RuntimeError,'Unexpected check')
        sql('ALTER TABLE payroll_periods DROP CHECK unexpected_policy_check')
        upgrade()
        print('PASS incompatible columns/indexes/checks/FKs/triggers and extra columns are detected; missing upgrade stages resume safely')

        # Force an interruption between additive DDL operations, then resume.
        # Only test-created objects are removed in this verified temporary server.
        for name in migration.TRIGGERS:sql('DROP TRIGGER '+name)
        sql('ALTER TABLE payroll_periods DROP FOREIGN KEY fk_payroll_period_policy, DROP CHECK chk_payroll_period_policy_pair')
        sql('ALTER TABLE payroll_periods DROP INDEX idx_payroll_period_policy_dates, DROP INDEX idx_payroll_period_dates_status, DROP COLUMN policy_version_id, DROP COLUMN cutoff_code')
        sql('DROP TABLE payroll_policy_activations')
        sql('DROP TABLE payroll_policy_versions')
        original=migration._execute_ddl; count=0
        def interrupted(cursor,statement):
            nonlocal count
            count+=1
            if count==4:raise RuntimeError('Synthetic interrupted DDL')
            original(cursor,statement)
        with patch.object(migration,'_execute_ddl',side_effect=interrupted):
            rejected(upgrade,RuntimeError,'Synthetic interrupted')
        upgrade();upgrade()
        print('PASS actual partial DDL installation resumes after implicit commits without destructive automatic repair')

        import json
        counter=0
        def draft(**overrides):
            nonlocal counter
            counter+=1
            rules={}
            for field,schema in migration.JSON_RULES.items():
                if schema['type']=='array':rules[field]=['MONTHLY'];continue
                rules[field]={key:('BLOCK' if 'BLOCK' in prop['enum'] else next(v for v in prop['enum'] if v!='UNRESOLVED'))
                              for key,prop in schema['properties'].items()}
            values=dict(version_number=counter,policy_name='Synthetic Policy '+str(counter),effective_from='2028-01-01',
                        calculator_key='MONTHLY_SEMIMONTHLY_V1',calendar_key='SEMI_MONTHLY_1_15_16_EOM_V1',frequency='SEMI_MONTHLY',
                        working_week_mask=31,currency_code='PHP',full_cutoff_divisor=2,rounding_mode='ROUND_HALF_UP',rounding_scale=2,
                        created_by=7,updated_by=7,**{k:json.dumps(v) for k,v in rules.items()})
            values.update(overrides)
            return sql('INSERT INTO payroll_policy_versions('+','.join(values)+') VALUES('+','.join(['%s']*len(values))+')',tuple(values.values()))

        def policy(pid):return sql('SELECT * FROM payroll_policy_versions WHERE policy_version_id=%s',(pid,),True)[0]
        def approve(pid):
            sql("UPDATE payroll_policy_versions SET status='APPROVED',revision=revision+1,approved_by=7,approved_at=NOW(6),configuration_hash=%s,approval_reference='Synthetic approval' WHERE policy_version_id=%s",('a'*64,pid))

        base_connect=connect; mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'
        def connect():
            connection=base_connect();cur=connection.cursor();cur.execute('SET SESSION sql_mode=%s',(mode,));cur.close();return connection
        for mode,effective in [('STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION','2028-01-01'),('','2028-01-16')]:
            pid=draft(effective_from=effective)
            # Draft-only activation and direct INSERT of approved rows are prohibited.
            rejected(lambda:sql('INSERT INTO payroll_policy_activations VALUES(%s,%s,7,NOW(6))',(effective,pid)),mysql.connector.Error)
            rejected(lambda:draft(status='APPROVED',approved_by=7,approved_at=datetime.now(),configuration_hash='a'*64),mysql.connector.Error)
            for column,value in [('version_number',0),('revision',0),('policy_name',''),('policy_name','   '),
                                 ('effective_from','2028-01-02'),('calculator_key','arbitrary SQL'),('calendar_key','unknown'),
                                 ('working_week_mask',0),('currency_code','USD'),('full_cutoff_divisor',0),('rounding_mode','DOWN'),('rounding_scale',3),
                                 ('status',''),('created_by',999999),('cutoff_rules',json.dumps(dict(a_start=1,a_end=15,b_start=16,b_end=31))),
                                 ('payment_rules','{"mode":"MANUAL","sql":"DROP TABLE users"}'),('supported_pay_types','["HOURLY"]')]:
                rejected(lambda:draft(**{column:value}),mysql.connector.Error)
            for field in migration.JSON_RULES:
                rejected(lambda:draft(**{field:'{}'}),mysql.connector.Error)
                rejected(lambda:draft(**{field:'null'}),mysql.connector.Error)
            rejected(lambda:draft(version_number=policy(pid)['version_number']),mysql.connector.Error)
            saved=policy(pid)
            rejected(lambda:sql("UPDATE payroll_policy_versions SET policy_name='Lost edit' WHERE policy_version_id=%s",(pid,)),mysql.connector.Error)
            assert policy(pid)==saved
            sql("UPDATE payroll_policy_versions SET policy_name='Reviewed draft',revision=revision+1 WHERE policy_version_id=%s",(pid,))
            rejected(lambda:sql("UPDATE payroll_policy_versions SET status='APPROVED',revision=revision+1 WHERE policy_version_id=%s",(pid,)),mysql.connector.Error)
            for bad_hash in ('a'*63, 'g'*64, 'A'*64):
                rejected(lambda:sql("UPDATE payroll_policy_versions SET status='APPROVED',revision=revision+1,approved_by=7,approved_at=NOW(6),configuration_hash=%s WHERE policy_version_id=%s",(bad_hash,pid)),mysql.connector.Error)
            unresolved=draft(attendance_rules=json.dumps(dict(missing_evidence='BLOCK',late_treatment='UNRESOLVED',absence_treatment='BLOCK',half_day_treatment='BLOCK')))
            rejected(lambda:approve(unresolved),mysql.connector.Error)
            approve(pid);saved=policy(pid)
            assert saved['status']=='APPROVED' and saved['revision']==3 and saved['approved_by']==7
            for fragment in ("policy_name='Changed'","revision=revision+1","status='DRAFT'","configuration_hash=NULL","policy_version_id=99999"):
                rejected(lambda:sql('UPDATE payroll_policy_versions SET '+fragment+' WHERE policy_version_id=%s',(pid,)),mysql.connector.Error)
            rejected(lambda:sql('DELETE FROM payroll_policy_versions WHERE policy_version_id=%s',(pid,)),mysql.connector.Error)
            rejected(lambda:sql("INSERT INTO payroll_policy_versions SELECT * FROM payroll_policy_versions WHERE policy_version_id=%s ON DUPLICATE KEY UPDATE policy_name='Changed'",(pid,)),mysql.connector.Error)
            assert policy(pid)==saved
            wrong_date='2028-02-01'
            rejected(lambda:sql('INSERT INTO payroll_policy_activations VALUES(%s,%s,7,NOW(6))',(wrong_date,pid)),mysql.connector.Error)
            rejected(lambda:sql('INSERT INTO payroll_policy_activations VALUES(%s,99999,7,NOW(6))',(effective,)),mysql.connector.Error)
            rejected(lambda:sql('INSERT INTO payroll_policy_activations VALUES(%s,%s,99999,NOW(6))',(effective,pid)),mysql.connector.Error)
            sql('INSERT INTO payroll_policy_activations VALUES(%s,%s,7,NOW(6))',(effective,pid))
            activation=sql('SELECT * FROM payroll_policy_activations WHERE policy_version_id=%s',(pid,),True)
            rejected(lambda:sql('INSERT INTO payroll_policy_activations VALUES(%s,%s,7,NOW(6))',(effective,pid)),mysql.connector.Error)
            rejected(lambda:sql('UPDATE payroll_policy_activations SET activated_by=8 WHERE policy_version_id=%s',(pid,)),mysql.connector.Error)
            rejected(lambda:sql('DELETE FROM payroll_policy_activations WHERE policy_version_id=%s',(pid,)),mysql.connector.Error)
            rejected(lambda:sql('REPLACE INTO payroll_policy_activations VALUES(%s,%s,7,NOW(6))',(effective,pid)),mysql.connector.Error)
            assert sql('SELECT * FROM payroll_policy_activations WHERE policy_version_id=%s',(pid,),True)==activation
            # An invalid code must fail even when ENUM coercion is non-strict.
            rejected(lambda:sql("UPDATE payroll_periods SET policy_version_id=%s,cutoff_code='X' WHERE payroll_period_id=1",(pid,)),mysql.connector.Error)
            rejected(lambda:sql("UPDATE payroll_periods SET policy_version_id=NULL,cutoff_code='A' WHERE payroll_period_id=1"),mysql.connector.Error)
            rejected(lambda:sql("UPDATE payroll_periods SET policy_version_id=99999,cutoff_code='A' WHERE payroll_period_id=1"),mysql.connector.Error)
            upgrade()
            assert policy(pid)==saved
            print('PASS SQL mode',mode or 'NON-STRICT',': bounded JSON/fields, metadata, revisions, first approval, immutable approved/activation rows, FK dates/actors, duplicate versions and cutoff codes')

        mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'
        linked=erp.create_payroll_period('005 linked fixture',date(2028,1,16),date(2028,1,31),date(2028,2,1),None,7)
        sql("UPDATE payroll_periods SET policy_version_id=%s,cutoff_code='B' WHERE payroll_period_id=%s",(pid,linked))
        assert sql('SELECT policy_version_id,cutoff_code FROM payroll_periods WHERE payroll_period_id=%s',(linked,),True)==[dict(policy_version_id=pid,cutoff_code='B')]
        # Real old application operations continue to use NULL policy references.
        p=erp.create_payroll_period('005 compatibility',date(2029,1,1),date(2029,1,15),date(2029,1,16),None,7)
        erp.generate_payroll_entries(p,7)
        for offset in range(15):
            day=date(2029,1,1)+timedelta(days=offset)
            if day.weekday()<5:sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(9,%s,'PRESENT',7)",(day,))
        erp.calculate_monthly_payroll_period(p,7)
        for suffix in ('submit','return-to-draft','submit','approve','paid'):
            response=client().post(f'/payroll/periods/{p}/{suffix}',data={})
            assert response.status_code==302
        entry=sql('SELECT * FROM payroll_entries WHERE payroll_period_id=%s',(p,),True)[0]
        assert entry['net_pay']==Decimal('500') and entry['status']=='PAID' and entry['calculation_input_hash']
        period=sql('SELECT * FROM payroll_periods WHERE payroll_period_id=%s',(p,),True)[0]
        assert period['policy_version_id'] is None and period['cutoff_code'] is None
        for table,original_rows in before.items():
            current=sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True)
            for original in original_rows:
                actual=next(r for r in current if all(r.get(k)==v for k,v in original.items()))
                if table=='payroll_periods':
                    assert actual['policy_version_id'] is None and actual['cutoff_code'] is None
                    actual={k:v for k,v in actual.items() if k not in ('policy_version_id','cutoff_code')}
                assert actual==original,(table,original)
        before_repeat=snapshot();upgrade();assert snapshot()==before_repeat
        print('PASS old monthly calculation, evidence, return/submit/approve/pay, postcommit audits and legacy NULL handling; all original histories remain unchanged')
    print('SUCCESS: migration 005 actual MySQL foundation verified on synthetic disposable data only')


if __name__=='__main__':
    import mysql_audit_smoke as harness
    harness.run=run
    harness.main()

