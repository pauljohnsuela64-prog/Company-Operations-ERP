"""Committed HR business audit integration on a verified disposable MySQL server."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session, user_state
from test_hr_validation import EMPLOYEE, DEPARTMENT


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve(), 'Isolation failure'
        cur.execute('CREATE DATABASE erp_hr_audit')
        cur.execute('USE erp_hr_audit')
        for name in ['core', 'attendance', 'leave', 'it_assets', 'it_asset_assignment',
                     'it_asset_maintenance', 'help_desk', 'help_desk_history', 'audit_logs']:
            for stmt in re.sub(r'--[^\n]*', '', (harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', stmt, re.I):
                    cur.execute(stmt)
        db.commit()
    options['database'] = 'erp_hr_audit'

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
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-hr-audit', ERP_ENV='testing'))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app')
        employees=importlib.import_module('employee_repository')
        departments=importlib.import_module('department_repository')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client():
            c=csrf_client(erp.app)
            with c.session_transaction() as session:
                stamp_session(erp.app,session,user_state(user_id=1,role_id=1,username='hr-1',password_hash='synthetic'))
            return c
        def logs():return sql('SELECT user_id,username,module,action,entity_type,entity_id,description,created_at FROM audit_logs ORDER BY audit_log_id',fetch=True)
        def post(path,form,description,action,entity,target):
            before=len(logs())
            with patch.object(erp,'create_audit_log',wraps=erp.create_audit_log) as writer:
                assert client().post(path,data=form).status_code==302
                assert writer.call_count==1
            rows=logs();assert len(rows)==before+1
            row=rows[-1]
            assert row[:7]==(1,'hr-1','HR',action,entity,str(target),description),row
            assert row[7] is not None
        department_form=dict(DEPARTMENT,department_name='PRIVATE-DEPT-NAME',description='PRIVATE-REFERENCE')
        form=dict(EMPLOYEE,employee_number='PRIVATE-NUMBER',first_name='PRIVATE-FIRST',last_name='PRIVATE-LAST',email='private@example.invalid',phone='PRIVATE-PHONE')
        post('/employees/add',form,'Employee 1 created; revision 1.','CREATE','EMPLOYEE',1)
        for r in (1,2):
            post('/employees/1/edit',dict(form,employment_status='Active',expected_revision=str(r)),f'Employee 1 profile save committed; revision {r} to {r+1}.','UPDATE','EMPLOYEE',1)
        post('/employees/1/edit',dict(form,employment_status='Resigned',department_id='',expected_revision='3'),'Employee 1 profile save committed; revision 3 to 4.','UPDATE','EMPLOYEE',1)
        post('/departments/add',department_form,'Department 3 created; revision 1.','CREATE','DEPARTMENT',3)
        post('/departments/3/edit',dict(department_form,expected_revision='1'),'Department 3 detail save committed; revision 1 to 2.','UPDATE','DEPARTMENT',3)
        post('/departments/3/status',dict(is_active='0',expected_revision='2'),'Department 3 deactivated; revision 2 to 3.','DEACTIVATE','DEPARTMENT',3)
        before=logs()
        assert client().post('/departments/3/status',data=dict(is_active='0',expected_revision='2')).status_code==302
        assert logs()==before
        post('/departments/3/status',dict(is_active='1',expected_revision='3'),'Department 3 activated; revision 3 to 4.','ACTIVATE','DEPARTMENT',3)
        # Concurrent real requests with one shared revision produce one committed audit.
        for path,payload in [('/employees/1/edit',dict(form,employment_status='Active',expected_revision='4')),
                             ('/departments/3/edit',dict(department_form,expected_revision='4')),
                             ('/departments/3/status',dict(is_active='0',expected_revision='5'))]:
            barrier=threading.Barrier(2);before=len(logs())
            def race():
                barrier.wait(10)
                return client().post(path,data=payload).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=sorted(f.result(timeout=20) for f in [pool.submit(race),pool.submit(race)])
            assert outcomes==([302,302] if path.endswith('status') else [302,409]),outcomes
            assert len(logs())==before+1
        before=logs()
        for path,payload in [('/employees/1/edit',dict(form,employment_status='Active',expected_revision='5')),
                             ('/departments/3/edit',dict(department_form,expected_revision='6')),
                             ('/departments/3/status',dict(is_active='1',expected_revision='6'))]:
            current=int(payload['expected_revision'])
            for bad,status in [('',400),('0',400),('1.0',400),(str(current-1),409),(str(current+1),409)]:
                assert client().post(path,data=dict(payload,expected_revision=bad)).status_code==status
        for path in ('/employees/99999/edit','/departments/99999/edit','/departments/99999/status'):
            assert client().post(path,data=dict(form,expected_revision='1',is_active='0',employment_status='Active')).status_code==404
        assert client().post('/employees/add',data=form).status_code==200
        assert client().post('/departments/add',data=department_form).status_code==200
        assert logs()==before
        # SQL rollback and commit failure on real route repositories: no success audit.
        for table,path,payload,repo in [('employees','/employees/1/edit',dict(form,employment_status='Active',expected_revision='5'),employees),
                                        ('departments','/departments/3/edit',dict(department_form,expected_revision='6'),departments)]:
            before=logs()
            sql(f"CREATE TRIGGER reject_hr_write BEFORE UPDATE ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic rollback'")
            try:
                try:client().post(path,data=payload)
                except mysql.connector.Error:pass
                else:raise AssertionError('SQL failure expected')
            finally:sql('DROP TRIGGER reject_hr_write')
            assert logs()==before
            class CommitFailure:
                def __init__(self):self.inner=connect()
                def __getattr__(self,name):return getattr(self.inner,name)
                def commit(self):raise RuntimeError('synthetic pre-commit failure')
            with patch.object(repo,'get_connection',side_effect=CommitFailure):
                try:client().post(path,data=payload)
                except RuntimeError:pass
                else:raise AssertionError('commit failure expected')
            assert logs()==before
        # Genuine audit INSERT failure after successful business commit, for all mutations.
        before=logs()
        sql("CREATE TRIGGER reject_hr_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic audit failure'")
        try:
            for path,payload in [('/employees/add',dict(form,employee_number='SECOND',email='second@example.invalid')),
                                 ('/employees/1/edit',dict(form,employment_status='Active',expected_revision='5')),
                                 ('/departments/add',dict(department_form,department_code='SECOND',department_name='Second')),
                                 ('/departments/3/edit',dict(department_form,expected_revision='6')),
                                 ('/departments/3/status',dict(is_active='1',expected_revision='7'))]:
                assert client().post(path,data=payload).status_code==302
            assert sql('SELECT revision FROM employees WHERE employee_id=1',fetch=True)==[(6,)]
            assert sql('SELECT revision,is_active FROM departments WHERE department_id=3',fetch=True)==[(8,1)]
            assert sql('SELECT COUNT(*) FROM employees',fetch=True)==[(2,)]
            assert sql('SELECT COUNT(*) FROM departments',fetch=True)==[(4,)]
            assert logs()==before
        finally:sql('DROP TRIGGER reject_hr_audit')
        # A lost acknowledgement is not proof of rollback: commit can persist
        # even though the route receives an exception and cannot attempt auditing.
        class CommitAcknowledgementLost:
            def __init__(self):self.inner=connect()
            def __getattr__(self,name):return getattr(self.inner,name)
            def commit(self):
                self.inner.commit()
                raise RuntimeError('synthetic lost acknowledgement after commit')
        before=logs()
        for repo,table,path,payload,target,committed in [
            (employees,'employees','/employees/1/edit',dict(form,employment_status='Active',expected_revision='6'),1,7),
            (departments,'departments','/departments/3/edit',dict(department_form,expected_revision='8'),3,9)]:
            with patch.object(repo,'get_connection',side_effect=CommitAcknowledgementLost):
                try:client().post(path,data=payload)
                except RuntimeError:pass
                else:raise AssertionError('lost acknowledgement expected')
            pk='employee_id' if table=='employees' else 'department_id'
            assert sql(f'SELECT revision FROM {table} WHERE {pk}=%s',(target,),True)==[(committed,)]
            assert logs()==before
        # Audit permission is unnecessary for writes and still required for viewing.
        assert client().get('/admin/audit-logs').status_code==302
        sql("INSERT INTO permissions(permission_code) VALUES('audit_logs.view')")
        sql("INSERT INTO role_permissions SELECT 1,permission_id FROM permissions WHERE permission_code='audit_logs.view'")
        response=client().get('/admin/audit-logs?module=HR&action=UPDATE')
        assert response.status_code==200 and 'profile save committed' in response.get_data(as_text=True)
        from audit_log_repository import get_filtered_audit_logs
        selected=get_filtered_audit_logs(module='HR',action='UPDATE')
        assert selected and all(row['action']=='UPDATE' for row in selected)
        for row in logs():
            assert len(row[6])<150
            for secret in ('PRIVATE','private@example.invalid','Resigned',department_form['department_name'],department_form['description']):
                assert secret not in row[6]
        # Exhaustion, invalid CSRF, revoked grants and disabled actors leave no audit.
        from hr_revision import MAX_REVISION
        sql('UPDATE employees SET revision=%s WHERE employee_id=1',(MAX_REVISION,))
        sql('UPDATE departments SET revision=%s WHERE department_id=3',(MAX_REVISION,))
        before=logs()
        assert client().post('/employees/1/edit',data=dict(form,employment_status='Active',expected_revision=str(MAX_REVISION))).status_code==503
        assert client().post('/departments/3/edit',data=dict(department_form,expected_revision=str(MAX_REVISION))).status_code==503
        assert client().post('/departments/3/status',data=dict(is_active='0',expected_revision=str(MAX_REVISION))).status_code==503
        for path,payload in [('/employees/add',form),('/departments/add',department_form)]:
            assert client().post(path,data=payload,headers={'X-CSRFToken':'invalid'}).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND p.permission_code IN ('employees.create','departments.manage')")
        assert client().post('/employees/add',data=form).status_code==302
        assert client().post('/departments/add',data=department_form).status_code==302
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert client().post('/employees/add',data=form).location.endswith('/login')
        assert logs()==before
        print('PASS HR create/save/state metadata, unchanged saves, actual concurrent writes, rollback/commit failure, audit storage isolation, filters/rendering and permissions')
    print('SUCCESS: disposable HR audit integration; no configured ERP database accessed')


if __name__=='__main__':
    harness.run=run
    harness.main()
