"""Attendance on a verified disposable MySQL server; no company settings/data."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date, timedelta
import importlib
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session, user_state
from test_attendance import FORM


def run(port, data_dir):
    original_connect=mysql.connector.connect
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with original_connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_attendance_synthetic');cur.execute('USE erp_attendance_synthetic')
        for name in ('core','inventory','procurement','attendance','leave','audit_logs'):
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        cur.execute("INSERT INTO permissions(permission_code) VALUES ('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage')")
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic manager'),(2,'Synthetic viewer')")
        password=generate_password_hash('synthetic-password')
        cur.executemany('INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES(%s,%s,%s,%s,%s)',[(1,1,'attendance-manager',password,1),(2,2,'attendance-viewer',password,1),(3,1,'attendance-disabled',password,0)])
        cur.execute('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
        cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='attendance.view'")
        cur.execute("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'OLD','Historical department',0)")
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id,employment_status) VALUES(1,'ATT%_!','Synthetic','Employee',1,'Inactive'),(2,'OTHER','Other','Employee',NULL,'Active')")
        cur.executemany("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(1,%s,%s,1)",[(date(2024,1,1)+timedelta(days=i),'LATE' if i%2 else 'PRESENT') for i in range(63)])
        db.commit();cur.close()
    options['database']='erp_attendance_synthetic'
    def connect():
        db=original_connect(**options)
        cur=db.cursor();cur.execute("SET SESSION sql_mode='' ");cur.close()
        return db
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();cur.close();return result
    def snapshot():return tuple(sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('attendance_records','audit_logs'))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-attendance-sql',ERP_ENV='testing',DB_HOST='127.0.0.1',DB_PORT=str(port),DB_USER='root',DB_PASSWORD='synthetic-configuration',DB_NAME=options['database']))
        stack.enter_context(patch('mysql.connector.connect',side_effect=lambda **kw:connect()))
        erp=importlib.import_module('app');repo=importlib.import_module('attendance_repository')
        import database
        database.invalidate_compatibility();stack.callback(database.invalidate_compatibility)
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=csrf_client(erp.app)
            if uid:
                with c.session_transaction() as session:stamp_session(erp.app,session,user_state(user_id=uid,role_id=2 if uid==2 else 1,username='attendance-viewer' if uid==2 else 'attendance-manager',password_hash=password))
            return c
        before=snapshot()
        for size,expected in ((25,25),(50,50),(100,63)):
            page=repo.get_attendance_page(dict(search='ATT%_!',department_id='1',page_size=str(size)))
            assert len(page['records'])==expected and page['summary']['total']==63
            assert page['summary']['present']==32 and page['summary']['late']==31
        first=repo.get_attendance_page(dict(page='1'));second=repo.get_attendance_page(dict(page='2'))
        assert not {r['attendance_id'] for r in first['records']} & {r['attendance_id'] for r in second['records']}
        assert repo.get_attendance_page(dict(page='999'))['page']==3
        assert not repo.get_attendance_page(dict(search="' OR 1=1 --"))['records']
        assert repo.get_attendance_page(dict(date='2024-01-01'))['summary']['total']==1
        assert client().get('/attendance?page=2&page_size=25&search=ATT%25_%21&department_id=1').status_code==200
        assert snapshot()==before
        print('PASS bounded 25/50/100 pages, filtered totals, unique order, inactive Department history, literal search and unchanged data')
        for key,bad in [('employee_id','0'),('employee_id','2147483648'),('employee_id','999'),('attendance_date','2026-02-29'),('attendance_date','0999-01-01'),('attendance_date','20260101'),('time_in','24:00'),('time_out','08:60'),('status','UNKNOWN'),('notes','X'*256),('notes','\x00bad')]:
            response=client().post('/attendance/add',data=dict(FORM,**{key:bad}))
            assert response.status_code==400,(key,bad,response.status_code)
            assert snapshot()==before
        for uid in (None,2,3):
            assert client(uid).post('/attendance/add',data=FORM).status_code==302
        assert client().post('/attendance/add',data=FORM,headers={'X-CSRFToken':'invalid'}).status_code==400
        assert snapshot()==before
        print('PASS strict boundaries with non-strict SQL, invalid references, authorization/disabled/anonymous and CSRF: zero writes/audits')
        form=dict(FORM,notes='PRIVATE <notes> ?')
        assert client().post('/attendance/add',data=form).status_code==302
        identity=sql("SELECT attendance_id FROM attendance_records WHERE attendance_date='2026-01-02'",fetch=True)[0][0]
        assert sql('SELECT time_in,time_out,notes FROM attendance_records WHERE attendance_id=%s',(identity,),True)==[(timedelta(hours=8,minutes=1,seconds=2),timedelta(hours=17,minutes=2,seconds=3),form['notes'])]
        audit=sql("SELECT action,entity_id,description FROM audit_logs WHERE module='ATTENDANCE'",fetch=True)
        assert audit==[('CREATE',str(identity),f'Attendance {identity} created.')]
        after=snapshot()
        assert client().post('/attendance/add',data=form).status_code==409
        assert snapshot()==after
        assert client().post(f'/attendance/{identity}/edit',data=dict(form,status='ON_LEAVE',time_in='',time_out='')).status_code==302
        assert sql('SELECT status,time_in,time_out FROM attendance_records WHERE attendance_id=%s',(identity,),True)==[('ON_LEAVE',None,None)]
        after=snapshot()
        assert client().post(f'/attendance/{identity}/edit',data=dict(form,attendance_date='2024-01-01')).status_code==409
        assert snapshot()==after
        print('PASS create/update commits, exact seconds/Unicode, duplicate create/edit rollback and numeric confidential audit metadata')
        # Execute a real UPDATE, then inject a downstream failure before commit.
        original_factory=repo.get_connection
        class FailedCursor:
            def __init__(self,cursor):self.cursor=cursor
            def __getattr__(self,name):return getattr(self.cursor,name)
            def execute(self,query,params=()):
                result=self.cursor.execute(query,params)
                if query.startswith('UPDATE attendance_records SET'):
                    raise mysql.connector.Error('synthetic failure after real UPDATE',errno=1644)
                return result
        class FailedUpdate:
            def __init__(self):self.db=original_factory()
            def __getattr__(self,name):return getattr(self.db,name)
            def cursor(self,**kwargs):return FailedCursor(self.db.cursor(**kwargs))
        after=snapshot()
        with patch.object(repo,'get_connection',side_effect=FailedUpdate):
            assert client().post(f'/attendance/{identity}/edit',data=dict(form,status='ABSENT')).status_code==503
        assert snapshot()==after
        print('PASS actual UPDATE followed by SQL failure: original fields and audits preserved')
        parallel=dict(form,attendance_date='2026-01-03')
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes=list(pool.map(lambda _:client().post('/attendance/add',data=parallel).status_code,range(2)))
        assert sorted(codes)==[302,409],codes
        assert sql("SELECT COUNT(*) FROM attendance_records WHERE attendance_date='2026-01-03'",fetch=True)==[(1,)]
        assert len(sql("SELECT * FROM audit_logs WHERE module='ATTENDANCE' AND action='CREATE'",fetch=True))==2
        print('PASS concurrent duplicate submissions: one committed record, one success audit, one useful rejection')
        # A target disappearing between route read and the locked write cannot produce a success audit.
        saved=repo.get_attendance_record_by_id(identity)
        sql('DELETE FROM attendance_records WHERE attendance_id=%s',(identity,));after=snapshot()
        with patch.object(erp,'get_attendance_record_by_id',return_value=saved):
            assert client().post(f'/attendance/{identity}/edit',data=form).status_code==404
        assert snapshot()==after
        original_factory=repo.get_connection
        class CommitFailure:
            def __init__(self,committed=False):self.db=original_factory();self.committed=committed
            def __getattr__(self,name):return getattr(self.db,name)
            def commit(self):
                if self.committed:self.db.commit()
                raise mysql.connector.Error('synthetic lost acknowledgment',errno=2013)
        after=snapshot()
        with patch.object(repo,'get_connection',side_effect=CommitFailure):
            assert client().post('/attendance/add',data=dict(form,attendance_date='2026-01-04')).status_code==503
        assert snapshot()==after
        with patch.object(repo,'get_connection',side_effect=lambda:CommitFailure(True)):
            assert client().post('/attendance/add',data=dict(form,attendance_date='2026-01-05')).status_code==503
        assert sql("SELECT COUNT(*) FROM attendance_records WHERE attendance_date='2026-01-05'",fetch=True)==[(1,)]
        assert snapshot()[1]==after[1]
        print('PASS deleted target, precommit rollback and committed-but-lost acknowledgment: no false success audits or auto retry')
        sql("CREATE TRIGGER reject_attendance_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic audit failure'")
        try:
            assert client().post('/attendance/add',data=dict(form,attendance_date='2026-01-06')).status_code==302
            assert sql("SELECT COUNT(*) FROM attendance_records WHERE attendance_date='2026-01-06'",fetch=True)==[(1,)]
        finally:sql('DROP TRIGGER reject_attendance_audit')
        after=snapshot()
        sql('ALTER TABLE attendance_records ADD INDEX ix_attendance_employee(employee_id)')
        sql('ALTER TABLE attendance_records DROP INDEX uq_attendance_employee_date')
        assert client().post('/attendance/add',data=dict(form,attendance_date='2026-01-07')).status_code==503
        assert snapshot()==after
        sql('ALTER TABLE attendance_records ADD CONSTRAINT uq_attendance_employee_date UNIQUE(employee_id,attendance_date)')
        sql('CREATE TABLE unsupported_attendance LIKE attendance_records');sql('ALTER TABLE unsupported_attendance ENGINE=MyISAM')
        sql('RENAME TABLE attendance_records TO saved_attendance, unsupported_attendance TO attendance_records')
        try:
            empty=snapshot()
            assert client().post('/attendance/add',data=dict(form,attendance_date='2026-01-07')).status_code==503
            assert snapshot()==empty
        finally:
            sql('RENAME TABLE attendance_records TO unsupported_attendance, saved_attendance TO attendance_records');sql('DROP TABLE unsupported_attendance')
        assert snapshot()==after
        print('PASS audit failure cannot reverse commit; missing uniqueness/non-InnoDB fails closed; historical records preserved')
        # Existing Leave approval creates Attendance in its own transaction; keep that API and policy intact.
        leave=importlib.import_module('leave_repository')
        leave_type=sql("INSERT INTO leave_types(leave_code,leave_name,annual_entitlement,is_paid,is_active) VALUES('SYN','Synthetic',10,1,1)")
        lid=sql("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES('SYN-LEAVE',1,%s,'2026-02-01','2026-02-01',1,'Synthetic','PENDING',1)",(leave_type,))
        leave.approve_leave_request(lid,1)
        assert sql("SELECT status FROM attendance_records WHERE attendance_date='2026-02-01'",fetch=True)==[('ON_LEAVE',)]
        assert repo.get_filtered_attendance_records(attendance_date=date(2026,2,1))[0]['status']=='ON_LEAVE'
        assert client(2).get('/attendance').status_code==200
        print('PASS existing Leave-generated attendance and legacy readers remain compatible; no Payroll policy changes')
        print('SUCCESS Attendance regression used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
