"""Migration 009 structural guarantees; synthetic records on fresh MySQL only."""
import importlib.util
from pathlib import Path
import re

import mysql.connector
import mysql_audit_smoke as harness


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='')
    with mysql.connector.connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
    spec=importlib.util.spec_from_file_location('hr009',harness.ROOT/'database/migrations/009_hr_employment_lifecycle.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)

    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();return result
    def initialize(label,legacy=False):
        options.pop('database',None)
        sql('CREATE DATABASE lifecycle_'+label)
        options['database']='lifecycle_'+label
        text=(harness.ROOT/'database/core_schema.sql').read_text()
        if legacy:
            text=re.sub(r'^\s*revision BIGINT NOT NULL DEFAULT 1,\s*$','',text,flags=re.M)
            text=re.sub(r'^\s*CONSTRAINT ck_(employees|departments)_revision_positive CHECK \(revision >= 1\),\s*$','',text,flags=re.M)
        for stmt in re.sub(r'--[^\n]*','',text).split(';'):
            if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',stmt,re.I):sql(stmt)
        sql("INSERT INTO departments(department_id,department_code,department_name) VALUES(1,'HR','Synthetic')")
        sql("INSERT INTO employees(employee_id,employee_number,department_id,first_name,last_name) VALUES(1,'SYN-1',1,'Synthetic','One'),(2,'SYN-2',1,'Synthetic','Two')")
        sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic')")
        sql("INSERT INTO users(user_id,username,password_hash,role_id,employee_id) VALUES(1,'synthetic','not-a-credential',1,1)")
        for filename in ('attendance_schema.sql','leave_schema.sql','it_assets_schema.sql',
                         'it_asset_assignment_schema.sql','it_asset_maintenance_schema.sql','audit_logs_schema.sql'):
            text=(harness.ROOT/'database'/filename).read_text()
            for stmt in re.sub(r'--[^\n]*','',text).split(';'):
                if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',stmt,re.I):sql(stmt)
        sql("INSERT INTO attendance_records(employee_id,attendance_date,created_by) VALUES(1,'2024-01-01',1)")
        sql("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,requested_by) VALUES('SYN-LEAVE',1,1,'2024-01-02','2024-01-02',1,'Synthetic',1)")
        sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES(1,'SYN','Synthetic')")
        sql("INSERT INTO it_assets(asset_id,asset_tag,asset_name,category_id,department_id,assigned_employee_id,status,created_by) VALUES(1,'SYN-ASSET','Synthetic',1,1,1,'MAINTENANCE',1)")
        sql("INSERT INTO it_asset_assignments(asset_id,employee_id,department_id,assigned_by) VALUES(1,1,1,1)")
        sql("INSERT INTO it_asset_maintenance(asset_id,maintenance_type,description,start_date,created_by) VALUES(1,'Synthetic','Synthetic','2024-01-03',1)")
        sql("INSERT INTO audit_logs(user_id,username,module,action) VALUES(1,'synthetic','SYNTHETIC','BASELINE')")
        if not legacy:sql('UPDATE employees SET revision=17')
    def upgrade():
        with mysql.connector.connect(**options) as db:migration.upgrade(db)
    def rejected(query,params=()):
        try:sql(query,params)
        except mysql.connector.Error:return
        raise AssertionError('Accepted invalid SQL: '+query)
    def fails_upgrade():
        try:upgrade()
        except RuntimeError:return
        raise AssertionError('Accepted incompatible schema')
    def snapshot():
        return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in
                ('employees','departments','users','roles','permissions','role_permissions',
                 'attendance_records','leave_types','leave_requests','it_asset_categories',
                 'it_assets','it_asset_assignments','it_asset_maintenance','audit_logs')]
    def request(employee=1,**kw):
        data=dict(employee_id=employee,event_type='HIRE',effective_date='2024-01-01',effective_order=1,
                  expected_employee_revision=17,proposal_data='{}',source_type='DOCUMENT',
                  source_reference='synthetic-only',reason='Synthetic schema test',submitted_by=1,decision_state='PENDING')
        data.update(kw)
        return sql('INSERT INTO employee_lifecycle_requests ('+','.join(data)+') VALUES ('+','.join(['%s']*len(data))+')',tuple(data.values()))
    def event(employee=1,revision=1,**kw):
        data=dict(employee_id=employee,request_id=request(employee),event_type='HIRE',effective_date='2024-01-01',
                  effective_order=1,publication_revision=revision,changes='{}',source_type='DOCUMENT',
                  source_reference='synthetic-only',reason='Synthetic schema test',recorded_by=1)
        data.update(kw)
        return sql('INSERT INTO employee_employment_events ('+','.join(data)+') VALUES ('+','.join(['%s']*len(data))+')',tuple(data.values()))
    def expect_db(operation):
        try:operation()
        except mysql.connector.Error:return
        raise AssertionError('Expected database rejection')

    initialize('missing008',True);before=snapshot();fails_upgrade();assert snapshot()==before
    for i,mode in enumerate(['STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE','']):
        options['init_command']="SET SESSION sql_mode='"+mode+"'"
        initialize('mode'+str(i));before=snapshot();upgrade();upgrade()
        after=snapshot()
        assert [[tuple(row[:-1]) for row in after[0]],*after[1:]]==before  # added flag is last
        assert sql('SELECT lifecycle_managed,revision FROM employees',fetch=True)==[(0,17),(0,17)]
        for table in migration.TABLES:assert sql('SELECT COUNT(*) FROM '+table,fetch=True)==[(0,)]
        p=sql("INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,publication_revision) VALUES(1,1,'2024-01-01',1)")
        for query in [
            "INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,publication_revision) VALUES(1,1,'2024-01-01',1)",
            "INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,end_exclusive_date,publication_revision) VALUES(1,2,'2024-02-01','2024-02-01',1)",
            "INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,publication_revision) VALUES(1,0,'2024-01-01',1)",
            "UPDATE employees SET lifecycle_managed=2",
        ]:rejected(query)
        expect_db(lambda:request(2,employment_period_id=p))
        for overrides in [dict(submitted_by=999),dict(source_reference=''),dict(reason='x'*256),
                          dict(source_type='x'*31),dict(source_version='x'*51),dict(proposal_data='[]'),
                          dict(proposal_data='{"x":"'+'x'*17000+'"}'),dict(payload_version=2),
                          dict(expected_employee_revision=0),dict(effective_date='0000-00-00'),
                          dict(effective_date='2024-00-01'),dict(effective_date='2024-01-00'),
                          dict(effective_order=0),dict(event_type='UNKNOWN'),dict(decision_state='APPROVED')]:
            expect_db(lambda overrides=overrides:request(**overrides))
        r=request(employment_period_id=p,submitted_at_utc='2000-01-01 00:00:00')
        assert sql('SELECT ABS(TIMESTAMPDIFF(SECOND,submitted_at_utc,UTC_TIMESTAMP()))<5 FROM employee_lifecycle_requests WHERE request_id=%s',(r,),True)==[(1,)]
        request(source_type='x'*30,source_reference='x'*255,source_version='x'*50,reason='x'*255)
        rejected('UPDATE employee_lifecycle_requests SET reason=%s WHERE request_id=%s',('changed',r))
        for field,value in [('proposal_data','{"x":1}'),('source_reference','changed'),
                            ('expected_employee_revision',18),('employee_id',2),
                            ('submitted_by',999),('effective_date','2024-02-01')]:
            rejected(f'UPDATE employee_lifecycle_requests SET {field}=%s WHERE request_id=%s',(value,r))
        sql("UPDATE employee_lifecycle_requests SET decision_state='APPROVED',decided_by=1,decision_reason='Synthetic decision' WHERE request_id=%s",(r,))
        assert sql('SELECT decided_at_utc IS NOT NULL FROM employee_lifecycle_requests WHERE request_id=%s',(r,),True)==[(1,)]
        rejected('UPDATE employee_lifecycle_requests SET decision_reason=%s WHERE request_id=%s',('changed',r))
        rejected('DELETE FROM employee_lifecycle_requests WHERE request_id=%s',(r,))
        e=event(employment_period_id=p,recorded_at_utc='2000-01-01 00:00:00')
        assert sql('SELECT ABS(TIMESTAMPDIFF(SECOND,recorded_at_utc,UTC_TIMESTAMP()))<5 FROM employee_employment_events WHERE employment_event_id=%s',(e,),True)==[(1,)]
        correction=event(revision=2,event_type='CORRECT',supersedes_event_id=e)
        event(revision=3,event_type='VOID',supersedes_event_id=correction)
        expect_db(lambda:event(revision=4,event_type='CORRECT',supersedes_event_id=e))
        expect_db(lambda:event(2,1,event_type='CORRECT',supersedes_event_id=e))
        expect_db(lambda:event(revision=1))
        expect_db(lambda:event(revision=5,request_id=sql('SELECT request_id FROM employee_employment_events WHERE employment_event_id=%s',(e,),True)[0][0]))
        expect_db(lambda:event(revision=5,recorded_by=999))
        expect_db(lambda:event(revision=5,event_type='CORRECT',supersedes_event_id=999))
        expect_db(lambda:event(revision=5,changes='[]'))
        expect_db(lambda:event(revision=5,reason='x'*256))
        expect_db(lambda:event(revision=5,event_type='HIRE',supersedes_event_id=e))
        rejected('UPDATE employee_employment_events SET reason=reason WHERE employment_event_id=%s',(e,))
        rejected('DELETE FROM employee_employment_events WHERE employment_event_id=%s',(e,))
        rejected('DELETE FROM employee_employment_periods WHERE employment_period_id=%s',(p,))
        rejected('DELETE FROM employees WHERE employee_id=1')
        rejected('DELETE FROM users WHERE user_id=1')
        upgrade();assert snapshot()==after
        count=sql('SELECT COUNT(*) FROM employee_lifecycle_requests',fetch=True)
        with mysql.connector.connect(**options) as db:
            cur=db.cursor()
            cur.execute('INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,publication_revision) VALUES(1,9,\'2024-01-01\',9)')
            db.rollback()
        assert sql('SELECT COUNT(*) FROM employee_employment_periods',fetch=True)==[(1,)]
        assert sql('SELECT COUNT(*) FROM employee_lifecycle_requests',fetch=True)==count
        print('PASS fresh/repeated migration, legacy/revision preservation, FK/checks, correction chains, immutable history/requests in',mode or 'NON-STRICT')

    initialize('interrupted')
    class InterruptCursor:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def execute(self,query,*args,**kwargs):
            if query.startswith('CREATE TABLE `employee_lifecycle_requests`'):raise RuntimeError('Synthetic interruption')
            return self.inner.execute(query,*args,**kwargs)
    class InterruptConnection:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def cursor(self,*args,**kwargs):return InterruptCursor(self.inner.cursor(*args,**kwargs))
    with mysql.connector.connect(**options) as db:
        try:migration.upgrade(InterruptConnection(db))
        except RuntimeError as exc:assert str(exc)=='Synthetic interruption'
    upgrade();upgrade()
    sql('DROP TRIGGER hr_event_no_update');upgrade()
    print('PASS interrupted table/trigger upgrade recovery')
    initialize('flag_only')
    sql('ALTER TABLE employees ADD COLUMN lifecycle_managed TINYINT(1) NOT NULL DEFAULT 0')
    sql('UPDATE employees SET lifecycle_managed=1 WHERE employee_id=1')
    before=snapshot();upgrade();upgrade();assert snapshot()==before
    initialize('bad008')
    sql('ALTER TABLE employees MODIFY COLUMN revision INT NOT NULL DEFAULT 1')
    before=snapshot();fails_upgrade();assert snapshot()==before
    assert not sql("SELECT COLUMN_NAME FROM information_schema.columns WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='employees' AND COLUMN_NAME='lifecycle_managed'",fetch=True)
    initialize('preflight')
    sql(migration.create_table(migration.P))
    sql('ALTER TABLE employee_employment_periods MODIFY COLUMN period_sequence BIGINT NOT NULL')
    before=snapshot();fails_upgrade();assert snapshot()==before
    assert not sql("SELECT COLUMN_NAME FROM information_schema.columns WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='employees' AND COLUMN_NAME='lifecycle_managed'",fetch=True)
    print('PASS flag-only recovery, compatible flag preservation, incompatible 008/partial schema preflight without new DDL')
    for label,mutation in [
        ('column', 'ALTER TABLE employee_employment_events ADD COLUMN unexpected INT'),
        ('collation', 'ALTER TABLE employee_employment_events MODIFY COLUMN reason TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL'),
        ('index', 'ALTER TABLE employee_employment_events DROP INDEX uq_event_revision'),
        ('check', 'ALTER TABLE employee_employment_events ALTER CHECK ck_event_revision NOT ENFORCED'),
        ('fk', 'ALTER TABLE employee_employment_events DROP FOREIGN KEY fk_event_recorder'),
        ('trigger', "CREATE TRIGGER unexpected BEFORE UPDATE ON employee_employment_events FOR EACH ROW SET NEW.reason=NEW.reason"),
    ]:
        initialize('bad_'+label);upgrade();sql(mutation);before=snapshot();fails_upgrade();assert snapshot()==before
    print('PASS incompatible columns/indexes/checks/FKs/triggers fail closed without data changes')


if __name__=='__main__':
    harness.run=run
    harness.main()
