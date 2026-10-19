"""Migration 008, stale HR requests and actual InnoDB races; disposable only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
import importlib.util
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch

import mysql.connector
from werkzeug.datastructures import MultiDict
import mysql_audit_smoke as harness
from hr_revision import (MAX_REVISION, HRConflictError, HRMissingRecordError,
                         HRRevisionExhaustedError)
from hr_validation import employee_values
from security_helpers import csrf_client, stamp_session, user_state
from test_hr_validation import EMPLOYEE, DEPARTMENT


def run(port, data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
    spec=importlib.util.spec_from_file_location('hr_upgrade_008',harness.ROOT/'database/migrations/008_hr_employee_department_revisions.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)

    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor(dictionary=True);cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();cur.close();return result
    def initialize(label,legacy=True):
        schema='erp_hr_revision_'+label
        with connect() as db:
            cur=db.cursor();cur.execute('CREATE DATABASE '+schema);cur.execute('USE '+schema)
            text=(harness.ROOT/'database/core_schema.sql').read_text()
            if legacy:
                text=re.sub(r'^\s*revision BIGINT NOT NULL DEFAULT 1,\s*$', '',text,flags=re.M)
                text=re.sub(r'^\s*CONSTRAINT ck_(employees|departments)_revision_positive CHECK \(revision >= 1\),\s*$', '',text,flags=re.M)
            for stmt in re.sub(r'--[^\n]*','',text).split(';'):
                if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',stmt,re.I):cur.execute(stmt)
            db.commit()
        options['database']=schema
        sql("INSERT INTO departments(department_id,department_code,department_name) VALUES(1,'HR','Synthetic')")
        sql("INSERT INTO employees(employee_id,employee_number,department_id,first_name,last_name) VALUES(1,'HR-1',1,'Synthetic','Employee')")
    def upgrade():
        with connect() as db:migration.upgrade(db)
    def snapshot():
        return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ('employees','departments')]
    def expect(error,operation):
        try:operation()
        except error:return
        raise AssertionError('Expected '+error.__name__)
    def strip_revisions(snap):
        return [[{k:v for k,v in row.items() if k!='revision'} for row in table] for table in snap]

    for index,mode in enumerate(['STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE','']):
        options['init_command']="SET SESSION sql_mode='"+mode+"'"
        initialize('legacy'+str(index))
        before=snapshot();upgrade()
        assert strip_revisions(snapshot())==before
        for table in ('employees','departments'):
            assert sql('SELECT revision FROM '+table,fetch=True)==[{'revision':1}]
            expect(mysql.connector.Error,lambda:sql('UPDATE '+table+' SET revision=0'))
        sql('UPDATE employees SET revision=17')
        before=snapshot();upgrade();assert snapshot()==before
        print('PASS migration 008 legacy/repeat/data preservation/enforced CHECK in',mode or 'NON-STRICT')
    initialize('fresh',legacy=False);before=snapshot();upgrade();assert snapshot()==before
    initialize('interrupted_column')
    sql('ALTER TABLE departments ADD COLUMN revision BIGINT NOT NULL DEFAULT 1')
    sql('UPDATE departments SET revision=23')
    upgrade();assert sql('SELECT revision FROM departments',fetch=True)==[{'revision':23}]
    assert sql('SELECT revision FROM employees',fetch=True)==[{'revision':1}]
    initialize('interrupted_table')
    sql('ALTER TABLE departments ADD COLUMN revision BIGINT NOT NULL DEFAULT 1, ADD CONSTRAINT ck_departments_revision_positive CHECK (revision>=1)')
    upgrade();upgrade()
    initialize('interrupted_execution')
    class InterruptCursor:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def execute(self,query,*args,**kwargs):
            if query.startswith('ALTER TABLE `employees`'):
                raise RuntimeError('synthetic interrupted second-table DDL')
            return self.inner.execute(query,*args,**kwargs)
    class InterruptConnection:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def cursor(self,*args,**kwargs):return InterruptCursor(self.inner.cursor(*args,**kwargs))
    with connect() as db:expect(RuntimeError,lambda:migration.upgrade(InterruptConnection(db)))
    assert sql('SELECT revision FROM departments',fetch=True)==[{'revision':1}]
    upgrade();upgrade()
    for label,statement in [
        ('bad_column','ALTER TABLE departments ADD COLUMN revision INT NOT NULL DEFAULT 1'),
        ('bad_check','ALTER TABLE departments ADD COLUMN revision BIGINT NOT NULL DEFAULT 1, ADD CONSTRAINT ck_departments_revision_positive CHECK (revision>=0)'),
        ('not_enforced','ALTER TABLE departments ADD COLUMN revision BIGINT NOT NULL DEFAULT 1, ADD CONSTRAINT ck_departments_revision_positive CHECK (revision>=1) NOT ENFORCED')]:
        initialize(label);sql(statement);before=snapshot()
        expect(RuntimeError,upgrade);assert snapshot()==before
        assert sql("SELECT COUNT(*) AS n FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='employees' AND column_name='revision'",fetch=True)==[{'n':0}]
    initialize('bad_engine');sql('ALTER TABLE employees DROP FOREIGN KEY fk_employees_department')
    sql('ALTER TABLE users DROP FOREIGN KEY fk_users_employee')
    sql('ALTER TABLE employees ENGINE=MyISAM');expect(RuntimeError,upgrade)
    print('PASS fresh install, interrupted column/table recovery, incompatible column/check/enforcement/engine rejected before other DDL')

    initialize('operations',legacy=False)
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'HR synthetic manager'),(2,'HR synthetic viewer')")
    for code in ['employees.view','employees.create','employees.edit','departments.view','departments.manage']:
        sql('INSERT INTO permissions(permission_code) VALUES(%s)',(code,))
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('employees.view','departments.view')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'revision-1','synthetic'),(2,2,'revision-2','synthetic')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-hr-revisions',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');employees=importlib.import_module('employee_repository');departments=importlib.import_module('department_repository')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=csrf_client(erp.app)
            with c.session_transaction() as session:stamp_session(erp.app,session,user_state(user_id=uid,role_id=uid,username=f'revision-{uid}',password_hash='synthetic'))
            return c
        def post(path,values,uid=1):return client(uid).post(path,data=values)
        def employee_form(expected,**overrides):
            return dict(EMPLOYEE,employment_status='Active',expected_revision=str(expected),**overrides)
        def current(table,target=1):
            pk='employee_id' if table=='employees' else 'department_id'
            return sql(f'SELECT revision FROM {table} WHERE {pk}=%s',(target,),True)[0]['revision']
        # Repository return contract and defaults for new rows; reference-only
        # Employee assignment must not consume the Department revision.
        department_revision=current('departments')
        new_department=departments.create_department('SECOND','Second department')
        assert current('departments',new_department)==1
        new_employee=employees.create_employee(**employee_values(dict(EMPLOYEE,employee_number='SECOND',email='second@example.invalid')))
        assert current('employees',new_employee)==1
        assert current('departments')==department_revision
        r=current('employees')
        result=employees.update_employee(1,expected_revision=r,**employee_values(employee_form(r),True))
        assert result.revision==r+1 and result.changed
        r=current('departments')
        result=departments.update_department(1,expected_revision=r,**DEPARTMENT)
        assert result.revision==r+1 and result.changed
        before=snapshot()
        duplicate=employee_form(current('employees'));duplicate['employee_number']='SECOND'
        assert post('/employees/1/edit',duplicate).status_code==200
        duplicate=employee_form(current('employees'));duplicate['email']='second@example.invalid'
        assert post('/employees/1/edit',duplicate).status_code==200
        assert post('/departments/1/edit',dict(DEPARTMENT,department_code='SECOND',expected_revision=str(current('departments')))).status_code==200
        assert snapshot()==before

        # All operational behavior is repeated under strict and non-strict SQL modes.
        for mode in ['STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE','']:
            options['init_command']="SET SESSION sql_mode='"+mode+"'"
            r=current('employees')
            form=employee_form(r)
            assert post('/employees/1/edit',form).status_code==302
            assert current('employees')==r+1
            before=snapshot();assert post('/employees/1/edit',form).status_code==409;assert snapshot()==before
            r=current('employees')
            # Another editor separates the employee; the old form cannot restore Active.
            approved=employee_form(r);approved['employment_status']='Resigned'
            assert post('/employees/1/edit',approved).status_code==302
            before=snapshot();assert post('/employees/1/edit',employee_form(r)).status_code==409;assert snapshot()==before
            assert sql('SELECT employment_status FROM employees WHERE employee_id=1',fetch=True)==[{'employment_status':'Resigned'}]
            r=current('employees')
            raw=employee_form(r);raw['phone']='P'*31
            response=post('/employees/1/edit',raw)
            assert response.status_code==200 and f'name="expected_revision" value="{r}"' in response.get_data(as_text=True)
            assert current('employees')==r
            assert post('/employees/1/edit',employee_form(r)).status_code==302
            response=post('/employees/1/edit',raw)
            assert response.status_code==200 and f'name="expected_revision" value="{r}"' in response.get_data(as_text=True)
            raw['phone']='corrected';before=snapshot()
            assert post('/employees/1/edit',raw).status_code==409;assert snapshot()==before
            # Identical visible detail saves consume a revision, for both entities.
            r=current('employees');same=employee_form(r)
            assert post('/employees/1/edit',same).status_code==302
            r=current('employees');same['expected_revision']=str(r)
            assert post('/employees/1/edit',same).status_code==302 and current('employees')==r+1
            r=current('departments');details=dict(DEPARTMENT,expected_revision=str(r))
            assert post('/departments/1/edit',details).status_code==302
            before=snapshot();assert post('/departments/1/edit',details).status_code==409;assert snapshot()==before
            details['expected_revision']=str(r+1)
            assert post('/departments/1/edit',details).status_code==302 and current('departments')==r+2
            r=current('departments')
            off={'is_active':'0','expected_revision':str(r)}
            assert post('/departments/1/status',off).status_code==302
            assert current('departments')==r+1
            before=snapshot()
            assert post('/departments/1/status',off).status_code==302;assert snapshot()==before
            assert post('/departments/1/status',dict(off,expected_revision=str(r+1))).status_code==302;assert snapshot()==before
            assert post('/departments/1/status',dict(off,is_active='1')).status_code==409;assert snapshot()==before
            assert post('/departments/1/status',dict(off,expected_revision=str(r+2))).status_code==409;assert snapshot()==before
            assert post('/departments/1/status',dict(off,is_active='1',expected_revision=str(r+1))).status_code==302
            for path,form in [('/employees/1/edit',employee_form(current('employees'))),
                              ('/departments/1/edit',dict(DEPARTMENT,expected_revision=str(current('departments')))),
                              ('/departments/1/status',{'is_active':'1','expected_revision':str(current('departments'))})]:
                before=snapshot()
                for bad in ['', '0','-1','1.0','9'*100,str(MAX_REVISION+1)]:
                    assert post(path,dict(form,expected_revision=bad)).status_code==400;assert snapshot()==before
                missing=dict(form);missing.pop('expected_revision')
                assert post(path,missing).status_code==400
                assert post(path,dict(form,expected_revision=str(MAX_REVISION))).status_code==409
                duplicate=MultiDict(form);duplicate.add('expected_revision','1')
                assert post(path,duplicate).status_code==400;assert snapshot()==before
            print('PASS no-op detail consumption, stale/duplicate/status conflicts, validation token retention and malformed/future revisions:',mode or 'NON-STRICT')

        for path in ['/employees/99999/edit','/departments/99999/edit','/departments/99999/status']:
            assert post(path,dict(employee_form(1),is_active='0')).status_code==404
        expect(HRMissingRecordError,lambda:employees.update_employee(99999,expected_revision=1,**employee_values(employee_form(1),True)))
        expect(HRMissingRecordError,lambda:departments.update_department(99999,expected_revision=1,**DEPARTMENT))

        # Both threads submit the SAME evidence, not a freshly fetched revision.
        for mode in ['STRICT_TRANS_TABLES','']:
            options['init_command']="SET SESSION sql_mode='"+mode+"'"
            for table,path,payload in [
                ('employees','/employees/1/edit',employee_form(current('employees'))),
                ('departments','/departments/1/edit',dict(DEPARTMENT,expected_revision=str(current('departments'))))]:
                r=current(table);barrier=threading.Barrier(2)
                def race():barrier.wait(10);return post(path,payload).status_code
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(race) for _ in range(2)]
                    assert sorted(f.result(timeout=20) for f in futures)==[302,409]
                assert current(table)==r+1
            print('PASS simultaneous actual InnoDB same-revision Employee/Department writes: exactly one commit in',mode or 'NON-STRICT')
        # Opposing simultaneous states: the stale opposite request can never
        # restore the old status. A same-state request may harmlessly finish first.
        r=current('departments');barrier=threading.Barrier(2)
        def status_race(desired):
            barrier.wait(10)
            return post('/departments/1/status',{'expected_revision':str(r),'is_active':desired}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(status_race,desired) for desired in ['0','1']]
            outcomes=sorted(f.result(timeout=20) for f in futures)
            assert outcomes in ([302,302],[302,409])
        assert sql('SELECT is_active,revision FROM departments WHERE department_id=1',fetch=True)==[{'is_active':0,'revision':r+1}]
        assert post('/departments/1/status',{'expected_revision':str(r+1),'is_active':'1'}).status_code==302

        # Force an observed lock wait, then release a committed newer status.
        held=connect();held.start_transaction();cur=held.cursor()
        r=current('employees')
        cur.execute("UPDATE employees SET employment_status='Resigned',revision=revision+1 WHERE employee_id=1")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(post,'/employees/1/edit',employee_form(r))
                try:
                    deadline=time.monotonic()+10
                    while not sql('SELECT COUNT(*) AS n FROM performance_schema.data_lock_waits',fetch=True)[0]['n']:
                        assert time.monotonic()<deadline;time.sleep(.02)
                finally:held.commit()
                assert future.result(timeout=15).status_code==409
        finally:cur.close();held.close()
        assert current('employees')==r+1

        # SQL and COMMIT failures must roll back the fields AND increment.
        for table,path,form in [('employees','/employees/1/edit',employee_form(current('employees'))),
                                ('departments','/departments/1/edit',dict(DEPARTMENT,expected_revision=str(current('departments'))))]:
            before=snapshot()
            sql(f"CREATE TRIGGER reject_hr_revision BEFORE UPDATE ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic revision rollback'")
            try:expect(mysql.connector.Error,lambda:post(path,form))
            finally:sql('DROP TRIGGER reject_hr_revision')
            assert snapshot()==before
        class CommitFailure:
            def __init__(self):self.inner=connect()
            def __getattr__(self,name):return getattr(self.inner,name)
            def commit(self):raise RuntimeError('synthetic failed commit')
        for repo,operation in [(employees,lambda:employees.update_employee(1,expected_revision=current('employees'),**employee_values(employee_form(1),True))),
                               (departments,lambda:departments.update_department(1,expected_revision=current('departments'),**DEPARTMENT))]:
            before=snapshot()
            with patch.object(repo,'get_connection',side_effect=CommitFailure):expect(RuntimeError,operation)
            assert snapshot()==before
        sql('UPDATE employees SET revision=%s WHERE employee_id=1',(MAX_REVISION-1,))
        sql('UPDATE departments SET revision=%s WHERE department_id=1',(MAX_REVISION-1,))
        assert post('/employees/1/edit',employee_form(MAX_REVISION-1)).status_code==302
        assert current('employees')==MAX_REVISION
        assert post('/departments/1/edit',dict(DEPARTMENT,expected_revision=str(MAX_REVISION-1))).status_code==302
        assert current('departments')==MAX_REVISION
        for mode in ['STRICT_TRANS_TABLES','']:
            options['init_command']="SET SESSION sql_mode='"+mode+"'"
            sql('UPDATE employees SET revision=%s',(MAX_REVISION,));sql('UPDATE departments SET revision=%s',(MAX_REVISION,))
            before=snapshot()
            assert post('/employees/1/edit',employee_form(MAX_REVISION)).status_code==503
            assert post('/departments/1/edit',dict(DEPARTMENT,expected_revision=str(MAX_REVISION))).status_code==503
            assert post('/departments/1/status',{'expected_revision':str(MAX_REVISION),'is_active':'0'}).status_code==503
            assert snapshot()==before
            assert post('/departments/1/status',{'expected_revision':str(MAX_REVISION),'is_active':'1'}).status_code==302
            assert snapshot()==before
        before=snapshot()
        assert post('/employees/1/edit',employee_form(MAX_REVISION),uid=2).location.endswith('/dashboard')
        assert erp.app.test_client().post('/employees/1/edit',data=employee_form(1)).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND p.permission_code='employees.edit'")
        assert post('/employees/1/edit',employee_form(MAX_REVISION)).location.endswith('/dashboard')
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert client().get('/employees/1/edit').location.endswith('/login')
        assert snapshot()==before
        print('PASS observed stale lock wait, missing targets, SQL/commit rollback, BIGINT exhaustion, CSRF and fresh account/permission checks')
    print('SUCCESS: revision migration and stale-write tests used synthetic disposable databases only')


if __name__=='__main__':
    harness.run=run
    harness.main()
