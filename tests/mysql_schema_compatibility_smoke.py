"""Real gate regression; exclusively uses the launcher's verified synthetic server."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
import importlib.util
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch, Mock

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session, user_state
from test_hr_validation import EMPLOYEE, DEPARTMENT


def run(port, data_dir):
    original_connect = mysql.connector.connect
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with original_connect(**options) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT @@datadir')
            assert Path(cursor.fetchone()[0]).resolve() == data_dir.resolve()
            cursor.execute('CREATE DATABASE erp_schema_gate')
            cursor.execute('USE erp_schema_gate')
            for name in ('core', 'inventory', 'procurement', 'audit_logs'):
                text = (harness.ROOT/'database'/f'{name}_schema.sql').read_text()
                for statement in re.sub(r'--[^\n]*', '', text).split(';'):
                    if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                        cursor.execute(statement)
            cursor.execute("INSERT INTO permissions(permission_code) VALUES ('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage')")
            cursor.execute("INSERT INTO roles(role_id,role_name) VALUES (42,'Synthetic gate role')")
            cursor.execute("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (7,42,'acting.user','test-only')")
            cursor.execute("INSERT INTO departments(department_code,department_name) VALUES ('SYNTH','Synthetic')")
        connection.commit()
    options['database'] = 'erp_schema_gate'
    def connect(): return original_connect(**options)
    def sql(statement):
        with connect() as db:
            with db.cursor() as cur:
                cur.execute(statement)
                rows = cur.fetchall() if cur.with_rows else []
            db.commit()
            return rows
    def snapshot():
        return tuple(sql('SELECT * FROM '+table+' ORDER BY 1') for table in ('employees','departments','audit_logs'))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='synthetic-schema-gate', ERP_ENV='testing',
            DB_HOST='127.0.0.1', DB_PORT=str(port), DB_USER='root', DB_PASSWORD='synthetic-configuration-only', DB_NAME=options['database']))
        # Replace connectivity only; retain real get_connection, inspector and HTTP guard.
        stack.enter_context(patch('mysql.connector.connect', side_effect=lambda **kw: connect()))
        database = importlib.import_module('database')
        erp = importlib.import_module('app')
        inspector = importlib.import_module('schema_compatibility')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        state = user_state(permissions=['employees.view','employees.create','employees.edit','departments.view','departments.manage'])
        auth = stack.enter_context(patch.object(erp, 'get_authorization_state', return_value=state))
        def client(authenticated=False):
            c = csrf_client(erp.app)
            if authenticated:
                with c.session_transaction() as session: stamp_session(erp.app, session, state)
            return c
        def inspect():
            with connect() as db: return inspector.inspect_schema(db, options['database'])
        def blocked(label):
            database.invalidate_compatibility()
            before = snapshot()
            auth.reset_mock()
            # Cover every business endpoint without invoking any handler. Valid CSRF
            # means rejection cannot be attributed to missing tokens.
            checked = 0
            with ExitStack() as handlers:
                for endpoint in erp.app.view_functions:
                    if endpoint not in ('static','schema_liveness','schema_readiness','logout'):
                        handlers.enter_context(patch.dict(erp.app.view_functions, {endpoint: Mock(side_effect=AssertionError('Business handler executed'))}))
                for authenticated in (False, True):
                    c = client(authenticated)
                    for rule in erp.app.url_map.iter_rules():
                        if rule.endpoint in ('static','schema_liveness','schema_readiness','logout'): continue
                        if not label.startswith('pre-008') and rule.endpoint not in ('add_employee','add_department','employees','departments'):
                            continue
                        path = rule.rule
                        path = re.sub(r'<(?:int:)?[^>]+>', '1', path)
                        for method in sorted(rule.methods - {'HEAD','OPTIONS'}):
                            response = c.open(path, method=method, data=EMPLOYEE if 'employees' in path else DEPARTMENT)
                            checked += 1
                            assert response.status_code == 503, (label, path, method, response.status_code)
                            assert response.headers['Cache-Control'] == 'no-store'
                auth.assert_not_called()
            assert snapshot() == before, label
            for function, args, kwargs in ((erp.create_employee, tuple(EMPLOYEE.values()), {}),
                    (erp.create_department, tuple(DEPARTMENT.values()), {}),
                    (erp.update_employee, (1,*EMPLOYEE.values(),'Active'), {'expected_revision':1}),
                    (erp.update_department, (1,*DEPARTMENT.values()), {'expected_revision':1}),
                    (erp.set_department_active_status, (1,False), {'expected_revision':1})):
                try: function(*args, **kwargs)
                except database.SchemaUnavailable: pass
                else: raise AssertionError('Direct business operation bypassed gate')
            assert snapshot() == before
            assert client(True).get('/health/live').status_code == 200
            assert client(True).get('/health/ready').status_code == 503
            auth.assert_not_called()
            response = client().get('/employees', headers={'Accept':'application/json'})
            assert response.json == {'error':'service_unavailable'}
            assert options['database'] not in response.get_data(as_text=True)
            print('PASS HTTP requests=', checked, '; direct CRUD blocked; snapshots unchanged; handlers unexecuted:', label)
        assert inspect().compatible, inspect().issues
        database.invalidate_compatibility()
        assert client(True).get('/health/ready').status_code == 200
        assert client(True).get('/employees').status_code == 200
        with ThreadPoolExecutor(max_workers=6) as pool:
            assert list(pool.map(lambda _: client().get('/health/ready').status_code, range(12))) == [200]*12
        worker_code = """
import importlib, os
from unittest.mock import patch
import mysql.connector
original = mysql.connector.connect
def isolated(**kw):
    assert kw['host'] == '127.0.0.1' and kw['port'] == int(os.environ['DB_PORT'])
    assert kw['database'] == 'erp_schema_gate'
    kw['password'] = ''
    return original(**kw)
with patch('dotenv.load_dotenv',return_value=False), patch('mysql.connector.connect',side_effect=isolated):
    erp = importlib.import_module('app')
    assert erp.app.test_client().get('/health/ready').status_code == 200
print('worker preflight passed')
"""
        def start_worker(_):
            result = subprocess.run([sys.executable,'-B','-c',worker_code],cwd=harness.ROOT,
                                    capture_output=True,text=True,timeout=45)
            assert result.returncode == 0, result.stderr
            return result.returncode
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(start_worker,range(4))) == [0]*4
        print('PASS compatible schema, concurrent requests and four fresh worker processes')
        # Reproduce the exact old-schema hole, then prove it is closed.
        for table in ('employees','departments'):
            sql(f'ALTER TABLE {table} DROP CHECK ck_{table}_revision_positive, DROP COLUMN revision')
        blocked('pre-008: employee and department creation cannot commit')
        sql('ALTER TABLE employees ADD revision BIGINT NOT NULL DEFAULT 1, ADD CONSTRAINT ck_employees_revision_positive CHECK(revision >= 1)')
        blocked('partial 008')
        sql('ALTER TABLE departments ADD revision BIGINT NOT NULL DEFAULT 1')
        blocked('columns without CHECK')
        sql('ALTER TABLE departments ADD CONSTRAINT ck_departments_revision_positive CHECK(revision >= 1) NOT ENFORCED')
        blocked('disabled CHECK')
        sql('ALTER TABLE departments DROP CHECK ck_departments_revision_positive, ADD CONSTRAINT ck_departments_revision_positive CHECK(revision >= 0)')
        blocked('incorrect CHECK')
        sql('ALTER TABLE departments DROP CHECK ck_departments_revision_positive, ADD CONSTRAINT ck_departments_revision_positive CHECK(revision >= 1)')
        for definition in ('INT NOT NULL DEFAULT 1','BIGINT UNSIGNED NOT NULL DEFAULT 1','BIGINT NOT NULL DEFAULT 2','BIGINT NULL DEFAULT 1'):
            sql('ALTER TABLE departments MODIFY revision '+definition)
            blocked('wrong revision definition: '+definition)
        sql('ALTER TABLE departments MODIFY revision BIGINT NOT NULL DEFAULT 1')
        definition = sql('SHOW CREATE TABLE goods_receipt_items')[0][1]
        sql('DROP TABLE goods_receipt_items')
        sql('CREATE TABLE goods_receipt_items(id INT) ENGINE=MyISAM')
        assert any('goods_receipt_items: InnoDB' in issue for issue in inspect().issues)
        blocked('non-InnoDB required table')
        sql('DROP TABLE goods_receipt_items')
        sql(definition)
        for table in ('goods_receipts','stock_movements'):
            index = 'uq_'+table+'_submission'
            sql(f'ALTER TABLE {table} DROP INDEX {index}')
            blocked('missing unique token index: '+table)
            sql(f'ALTER TABLE {table} DROP COLUMN submission_id')
            blocked('missing token column: '+table)
            sql(f'ALTER TABLE {table} ADD submission_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL, ADD CONSTRAINT {index} UNIQUE(submission_id)')
        sql("DELETE FROM permissions WHERE permission_code='helpdesk.manage'")
        blocked('missing authorization code without automatic grants')
        sql("INSERT INTO permissions(permission_code) VALUES ('helpdesk.manage')")
        # Wrong target, unsupported version and metadata errors retain real admission.
        with patch.object(inspector, '_inspect', side_effect=mysql.connector.Error('synthetic metadata failure')):
            blocked('metadata unavailable')
        with patch('mysql.connector.connect', side_effect=mysql.connector.Error('synthetic outage')):
            blocked('database unavailable')
            c = client(True)
            assert c.get('/logout').status_code == 200
            assert c.post('/logout').status_code == 302
            with c.session_transaction() as session: assert 'user_id' not in session
        with connect() as db:
            assert not inspector.inspect_schema(db, 'wrong-target').compatible
        with patch.dict('os.environ', DB_NAME='wrong-target'):
            blocked('wrong actual selected database')
        # An operator completes a compatible partial migration on this synthetic target.
        sql('ALTER TABLE departments DROP CHECK ck_departments_revision_positive, DROP COLUMN revision')
        database.invalidate_compatibility()
        assert client().get('/health/ready').status_code == 503
        spec = importlib.util.spec_from_file_location('migration008', harness.ROOT/'database/migrations/008_hr_employee_department_revisions.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with connect() as db: migration.upgrade(db)
        database.invalidate_compatibility()  # Replacement workers start with no lease.
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(lambda _: client().get('/health/ready').status_code,range(8))) == [200]*8
        database.invalidate_compatibility()
        assert client().get('/health/ready').status_code == 200
        assert client(True).post('/departments/add', data=DEPARTMENT).status_code == 302
        assert client(True).post('/employees/add', data=EMPLOYEE).status_code == 302
        assert client(True).post('/employees/1/edit', data=dict(EMPLOYEE,employment_status='Active',expected_revision='1')).status_code == 302
        assert client(True).post('/employees/1/edit', data=dict(EMPLOYEE,employment_status='Active',expected_revision='1')).status_code == 409
        assert client(True).post('/departments/2/edit', data=dict(DEPARTMENT,expected_revision='1')).status_code == 302
        assert client(True).post('/departments/1/status', data=dict(is_active='0',expected_revision='1')).status_code == 302
        assert client(True).post('/departments/add', data=DEPARTMENT, headers={'X-CSRFToken':'invalid'}).status_code == 400
        assert client().post('/departments/add', data=DEPARTMENT).status_code == 302
        assert len(sql("SELECT * FROM audit_logs WHERE module='HR'")) == 5
        print('PASS postmigration restart, CRUD, stale revision, CSRF and anonymous authorization')
        print('SUCCESS schema compatibility gate: no company database accessed')


if __name__ == '__main__':
    harness.run = run
    harness.main()
