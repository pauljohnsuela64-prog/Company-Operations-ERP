"""HR validation and observed InnoDB eligibility races on disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from hr_validation import HRValidationError, employee_values
from hr_revision import HRMissingRecordError
from security_helpers import csrf_client, stamp_session, user_state
from test_hr_validation import EMPLOYEE, DEPARTMENT, LIMITS


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve(), 'Isolation failure'
        cur.execute('CREATE DATABASE erp_hr_validation')
        cur.execute('USE erp_hr_validation')
        for name in ['core', 'attendance', 'leave', 'it_assets', 'it_asset_assignment',
                     'it_asset_maintenance', 'help_desk', 'help_desk_history', 'audit_logs']:
            for stmt in re.sub(r'--[^\n]*', '', (harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', stmt, re.I):
                    cur.execute(stmt)
        db.commit()
    options['database'] = 'erp_hr_validation'

    def connect():
        return mysql.connector.connect(**options)

    def sql(query, params=(), fetch=False):
        with connect() as db:
            cur = db.cursor()
            cur.execute(query, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            db.commit()
            cur.close()
            return result

    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'HR synthetic manager'),(2,'HR synthetic viewer')")
    for code in ['employees.view','employees.create','employees.edit','departments.view','departments.manage']:
        sql('INSERT INTO permissions(permission_code) VALUES(%s)', (code,))
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('employees.view','departments.view')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'hr-1','synthetic'),(2,2,'hr-2','synthetic')")
    sql("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'HR1','Active',1),(2,'HR2','Inactive',0)")

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-hr-validation', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        erp = importlib.import_module('app')
        employees = importlib.import_module('employee_repository')
        departments = importlib.import_module('department_repository')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))

        def current_revision(table, target):
            pk = 'employee_id' if table == 'employees' else 'department_id'
            rows = sql(f'SELECT revision FROM {table} WHERE {pk}=%s',(target,),True)
            return rows[0][0] if rows else 1

        def client(uid=1):
            c = csrf_client(erp.app)
            with c.session_transaction() as session:
                stamp_session(erp.app, session, user_state(user_id=uid,role_id=uid,username=f'hr-{uid}',password_hash='synthetic'))
            # Existing validation tests open a fresh form for each attempt.
            # Stale-token coverage uses explicit tokens in mysql_hr_revision_smoke.
            original_post = c.post
            def post(path, data=None, **kwargs):
                data = dict(data or {})
                match = re.fullmatch(r'/(employees|departments)/(\d+)/(edit|status)',path)
                if match and 'expected_revision' not in data:
                    data['expected_revision'] = str(current_revision(match[1],int(match[2])))
                return original_post(path,data=data,**kwargs)
            c.post = post
            return c

        def snapshot():
            return [sql('SELECT * FROM '+table+' ORDER BY 1', fetch=True)
                    for table in ['employees','departments','users','audit_logs']]

        sequence = 0
        def fields():
            nonlocal sequence
            sequence += 1
            return dict(EMPLOYEE, employee_number=f'HR-{sequence}', email=f'hr-{sequence}@example.invalid')

        for mode in ['STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE', '']:
            options['init_command'] = "SET SESSION sql_mode='"+mode+"'"
            assert ('STRICT_TRANS_TABLES' in sql('SELECT @@sql_mode',fetch=True)[0][0]) == bool(mode)
            form = fields()
            assert client().post('/employees/add', data=form).status_code == 302
            eid = sql('SELECT employee_id FROM employees WHERE employee_number=%s',(form['employee_number'],),True)[0][0]
            edit = f'/employees/{eid}/edit'
            assert client().post(edit,data=dict(form,employment_status='Active')).status_code == 302
            invalid = []
            for key,limit in LIMITS.items():
                # Persist each exact boundary too, with an email that fits browser semantics.
                exact = ('a'*138+'@example.org') if key=='email' else 'X'*limit
                bounded = dict(fields(), **{key:exact})
                assert client().post('/employees/add',data=bounded).status_code == 302
                sql('DELETE FROM employees WHERE employee_number=%s',(bounded['employee_number'].upper(),))
                invalid.append(dict(form,**{key:'X'*(limit+1)}))
            invalid += [dict(form,**{key:''}) for key in ['employee_number','first_name','last_name']]
            invalid += [dict(form,hire_date=value) for value in ['bad','2025-02-29','0000-00-00','0999-01-01']]
            invalid += [dict(form,department_id=value) for value in ['abc','0','-1','2147483648','99999','2']]
            for path in ['/employees/add',edit]:
                for values in invalid:
                    before = snapshot()
                    response = client().post(path,data=dict(values,employment_status='Active'))
                    assert response.status_code == 200,(path,response.status_code)
                    assert snapshot() == before, (path,values)
            before = snapshot()
            assert client().post('/employees/add',data=form).status_code == 200
            duplicate_email = dict(fields(),email=form['email'])
            assert client().post('/employees/add',data=duplicate_email).status_code == 200
            assert snapshot() == before
            other = fields()
            assert client().post('/employees/add',data=other).status_code == 302
            before = snapshot()
            for overrides in [dict(employee_number=other['employee_number']),dict(email=other['email'])]:
                assert client().post(edit,data=dict(form,employment_status='Active',**overrides)).status_code == 200
                assert snapshot() == before
            for bad_status in ['', 'UNKNOWN', 'X'*31]:
                assert client().post(edit,data=dict(form,employment_status=bad_status)).status_code == 200
                assert snapshot() == before
            # Existing inactive association is preserved; moving to a different inactive department is rejected.
            sql('UPDATE departments SET is_active=0 WHERE department_id=1')
            assert client().post(edit,data=dict(form,employment_status='Active',phone='corrected')).status_code == 302
            assert sql('SELECT department_id,phone FROM employees WHERE employee_id=%s',(eid,),True)==[(1,'corrected')]
            assert client().post('/employees/add',data=fields()).status_code == 200
            sql('UPDATE departments SET is_active=1 WHERE department_id=1')
            assert client().post(edit,data=dict(form,department_id='',hire_date='',employment_status='Active')).status_code == 302
            assert sql('SELECT department_id,hire_date FROM employees WHERE employee_id=%s',(eid,),True)==[(None,None)]
            for key,limit in [('department_code',20),('department_name',100),('description',255)]:
                before = snapshot()
                for path in ['/departments/add','/departments/1/edit']:
                    assert client().post(path,data=dict(DEPARTMENT,**{key:'X'*(limit+1)})).status_code == 200
                    assert snapshot()==before
            depform = dict(department_code='D'+str(sequence).zfill(19),department_name='N'*99+str(bool(mode)),description='D'*255)
            # Name must remain within 100 and unique in each mode.
            depform['department_name']='N'*95+str(sequence).zfill(5)
            assert client().post('/departments/add',data=depform).status_code == 302
            did = sql('SELECT department_id FROM departments WHERE department_code=%s',(depform['department_code'],),True)[0][0]
            before = snapshot()
            assert client().post('/departments/add',data=depform).status_code == 200
            assert client().post('/departments/1/edit',data=depform).status_code == 200
            assert snapshot()==before
            assert client().post(f'/departments/{did}/edit',data=dict(depform,description='')).status_code == 302
            assert sql('SELECT description FROM departments WHERE department_id=%s',(did,),True)==[(None,)]
            print('PASS mode',mode or 'NON-STRICT',': exact/overlong fields, required values, dates, IDs, inactive references, duplicates, rollback, nullable values')

        for operation in [
            lambda:employees.update_employee(99999,expected_revision=1,**employee_values(dict(fields(),employment_status='Active'),True)),
            lambda:departments.update_department(99999,expected_revision=1,**DEPARTMENT),
            lambda:departments.set_department_active_status(99999,False,expected_revision=1)]:
            try: operation()
            except HRMissingRecordError: pass
            else: raise AssertionError('Missing HR target was accepted')
        for path in ['/employees/99999/edit','/departments/99999/edit']:
            assert client().post(path,data=fields()).status_code == 404

        def wait_for_lock():
            deadline = time.monotonic()+10
            while time.monotonic()<deadline:
                if sql("SELECT COUNT(*) FROM performance_schema.data_lock_waits w JOIN performance_schema.data_locks l ON l.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID WHERE l.OBJECT_SCHEMA='erp_hr_validation' AND l.OBJECT_NAME='departments'",fetch=True)[0][0]:
                    return
                time.sleep(.02)
            raise AssertionError('No observed InnoDB department lock wait')

        # Deactivation commits first: both CREATE and a new EDIT assignment must recheck after waiting.
        for editing in [False,True]:
            form=fields()
            target=employees.create_employee(**employee_values(dict(form,department_id=''))) if editing else None
            held=connect();held.start_transaction();cur=held.cursor()
            cur.execute('UPDATE departments SET is_active=0 WHERE department_id=1')
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    def write():
                        try:
                            if editing: employees.update_employee(target,expected_revision=current_revision('employees',target),**employee_values(dict(form,employment_status='Active'),True))
                            else: employees.create_employee(**employee_values(form))
                        except HRValidationError: return 'rejected'
                        return 'unexpected success'
                    future=pool.submit(write)
                    try: wait_for_lock()
                    finally: held.commit()
                    assert future.result(timeout=15)=='rejected'
            finally:cur.close();held.close()
            sql('UPDATE departments SET is_active=1 WHERE department_id=1')
        # Assignment holds SHARE first: deactivation cannot interleave before the write commits.
        acquired=threading.Event();release=threading.Event();real_lock=employees.lock_department
        def paused_lock(*args):
            real_lock(*args);acquired.set();assert release.wait(15)
        with patch.object(employees,'lock_department',side_effect=paused_lock), ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(employees.create_employee,**employee_values(fields()))
            try:
                assert acquired.wait(10)
                deactivation=pool.submit(departments.set_department_active_status,1,False,expected_revision=current_revision('departments',1))
                wait_for_lock()
            finally:release.set()
            created=future.result(timeout=15);assert deactivation.result(timeout=15)
        assert sql('SELECT department_id FROM employees WHERE employee_id=%s',(created,),True)==[(1,)]
        # Successful assignment followed by deactivation is permitted, not retroactively undone.
        for desired in ['0','0','1','1']:
            with ThreadPoolExecutor(max_workers=2) as pool:
                assert list(pool.map(lambda _:client().post('/departments/1/status',data={'is_active':desired}).status_code,range(2)))==[302,302]
            assert sql('SELECT is_active FROM departments WHERE department_id=1',fetch=True)==[(int(desired),)]
        print('PASS actual observed lock waits in both eligibility orders, missing/no-op targets and repeated/concurrent desired states')

        # Fail at SQL and at COMMIT; neither can partially change a master record.
        before=snapshot()
        sql("CREATE TRIGGER hr_reject_update BEFORE UPDATE ON employees FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic rollback'")
        try:
            try:employees.update_employee(created,expected_revision=current_revision('employees',created),**employee_values(dict(fields(),employment_status='Active'),True))
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected SQL failure')
        finally:sql('DROP TRIGGER hr_reject_update')
        assert snapshot()==before
        class CommitFailure:
            def __init__(self):self.inner=connect()
            def __getattr__(self,name):return getattr(self.inner,name)
            def commit(self):raise RuntimeError('synthetic commit failure')
        for repo,action in [(employees,lambda:employees.create_employee(**employee_values(fields()))),
                            (departments,lambda:departments.update_department(1,expected_revision=current_revision('departments',1),**DEPARTMENT))]:
            with patch.object(repo,'get_connection',side_effect=CommitFailure):
                try:action()
                except RuntimeError:pass
                else:raise AssertionError('Expected commit failure')
            assert snapshot()==before

        # Historical references and linked user status survive an unrelated employee update.
        sql('UPDATE users SET employee_id=%s WHERE user_id=1',(created,))
        sql("INSERT INTO attendance_records(employee_id,attendance_date,created_by) VALUES(%s,'2026-01-01',1)",(created,))
        sql("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,requested_by) SELECT 'HR-HISTORY',%s,MIN(leave_type_id),'2026-01-01','2026-01-01',1,'Synthetic',1 FROM leave_types",(created,))
        sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES(1,'HR','Synthetic')")
        asset=sql("INSERT INTO it_assets(asset_tag,asset_name,category_id,department_id,assigned_employee_id,status,created_by) VALUES('HR-ASSET','Synthetic',1,1,%s,'LOST',1)",(created,))
        sql('INSERT INTO it_asset_assignments(asset_id,employee_id,department_id,assigned_by) VALUES(%s,%s,1,1)',(asset,created))
        tables=['attendance_records','leave_requests','it_assets','it_asset_assignments','users']
        history=[sql('SELECT * FROM '+t,fetch=True) for t in tables]
        assert employees.update_employee(created,expected_revision=current_revision('employees',created),**employee_values(dict(fields(),employment_status='Resigned'),True))
        assert history==[sql('SELECT * FROM '+t,fetch=True) for t in tables]
        assert sql('SELECT is_active FROM users WHERE user_id=1',fetch=True)==[(1,)]
        before=snapshot()
        for path in ['/employees/add',f'/employees/{created}/edit','/departments/add','/departments/1/edit','/departments/1/status']:
            assert client(2).post(path,data=fields()).location.endswith('/dashboard')
            assert erp.app.test_client().post(path,data=fields()).status_code==400
        assert snapshot()==before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND p.permission_code IN ('employees.edit','departments.manage')")
        assert client().post(f'/employees/{created}/edit',data=fields()).location.endswith('/dashboard')
        assert client().post('/departments/1/status',data={'is_active':'0'}).location.endswith('/dashboard')
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert client().get('/employees').location.endswith('/login')
        assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(0,)]
        print('PASS SQL/commit rollback, historical references, unchanged user eligibility, permissions, CSRF, revocation and disabled accounts')
    print('SUCCESS: disposable-only HR validation and transaction tests')


if __name__ == '__main__':
    harness.run=run
    harness.main()
