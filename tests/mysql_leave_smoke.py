"""Leave on a verified disposable MySQL server; no company settings/data."""
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
from test_leave import FORM, TYPE


def run(port, data_dir):
    original_connect=mysql.connector.connect
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with original_connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_leave_synthetic');cur.execute('USE erp_leave_synthetic')
        for name in ('core','inventory','procurement','attendance','leave','audit_logs'):
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        cur.execute("INSERT INTO permissions(permission_code) VALUES ('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage')")
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic manager'),(2,'Synthetic viewer')")
        password=generate_password_hash('synthetic-password')
        cur.executemany('INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES(%s,%s,%s,%s,%s)',[(1,1,'attendance-manager',password,1),(2,2,'attendance-viewer',password,1),(3,1,'attendance-disabled',password,0)])
        cur.execute('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
        cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='leave.view'")
        cur.execute("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'OLD','Historical department',0)")
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id,employment_status) VALUES(1,'ATT%_!','Synthetic','Employee',1,'Inactive'),(2,'OTHER','Other','Employee',NULL,'Active')")
        cur.executemany("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(1,%s,%s,1)",[(date(2024,1,1)+timedelta(days=i),'LATE' if i%2 else 'PRESENT') for i in range(63)])
        db.commit();cur.close()
    options['database']='erp_leave_synthetic'
    def connect():
        db=original_connect(**options)
        cur=db.cursor();cur.execute("SET SESSION sql_mode='' ");cur.close()
        return db
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();cur.close();return result
    def snapshot():return tuple(sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('leave_requests','attendance_records','audit_logs','leave_types'))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-leave-sql',ERP_ENV='testing',DB_HOST='127.0.0.1',DB_PORT=str(port),DB_USER='root',DB_PASSWORD='synthetic-configuration',DB_NAME=options['database']))
        stack.enter_context(patch('mysql.connector.connect',side_effect=lambda **kw:connect()))
        erp=importlib.import_module('app');repo=importlib.import_module('leave_repository')
        import database
        database.invalidate_compatibility();stack.callback(database.invalidate_compatibility)
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=csrf_client(erp.app)
            if uid:
                with c.session_transaction() as session:stamp_session(erp.app,session,user_state(user_id=uid,role_id=2 if uid==2 else 1,username='attendance-viewer' if uid==2 else 'attendance-manager',password_hash=password))
            return c
        sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(3,'BALANCE','Balance','Fixture'),(4,'EMPTY','Empty','Fixture')")
        # Historical rows, including an inactive type/department, stay visible.
        sql("INSERT INTO leave_types(leave_type_id,leave_code,leave_name,annual_entitlement,is_paid,is_active) VALUES(50,'HISTORY','Historical type',NULL,0,0)")
        with connect() as db:
            cur=db.cursor()
            cur.executemany("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(%s,1,50,%s,%s,1,'Historical reason','REJECTED',1)",[(f'HIST-{i}',date(2020,1,1)+timedelta(days=i),date(2020,1,1)+timedelta(days=i)) for i in range(63)])
            db.commit()
        before=snapshot()
        assert client(2).get('/leave/requests').status_code==200
        for size,count in ((25,25),(50,50),(100,63)):
            page=repo.get_leave_request_page(dict(search='ATT%_!',department_id='1',leave_type_id='50',page_size=str(size)))
            assert len(page['records'])==count and page['summary']['total']==63
            assert page['summary']['rejected']==63 and page['summary']['pending']==0
        assert repo.get_leave_request_page(dict(search='ATT%'))['summary']['total']==63
        assert repo.get_leave_request_page(dict(search='ATT_'))['summary']['total']==0
        assert len(repo.get_leave_request_page(dict(search='HIST-',page='2147483647'))['records'])==13
        assert repo.get_leave_request_page(dict(date_from='2020-01-02',date_to='2020-01-02'))['summary']['total']==1
        assert client().get('/leave/requests?leave_type_id=50&department_id=1').status_code==200
        for bad in ({'page_size':'26'},{'date_from':'2027-02-29'},{'status':'OTHER'},{'search':'x'*101}):
            assert client().get('/leave/requests',query_string=bad).status_code==400
        for bad in (dict(FORM,employee_id='0'),dict(FORM,leave_type_id='50'),dict(FORM,reason='x'*501),dict(FORM,end_date='2030-01-01'),dict(FORM,reason='\x00')):
            assert client().post('/leave/requests/add',data=bad).status_code==400
        assert client(2).post('/leave/requests/add',data=FORM).status_code==302
        assert client(3).post('/leave/requests/add',data=FORM).status_code==302
        assert client().post('/leave/requests/add',data=FORM,headers={'X-CSRFToken':'invalid'}).status_code==400
        from werkzeug.datastructures import MultiDict
        duplicate=MultiDict(FORM);duplicate.add('employee_id','2')
        assert client().post('/leave/requests/add',data=duplicate).status_code==400
        for action in ('approve','reject','cancel'):
            assert client(2).post('/leave/requests/1/'+action,data={'rejection_reason':'Denied'}).status_code==302
        assert snapshot()==before
        print('PASS 25/50/100 snapshot pages, full counts, literal search, date intersection and historical inactive filters; malformed/denied writes preserve snapshots')
        barrier=__import__('threading').Barrier(2)
        def submit(_):
            c=client();barrier.wait(timeout=10)
            return c.post('/leave/requests/add',data=FORM).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(submit,range(2)))
        assert sorted(codes)==[302,409],codes
        requests=sql("SELECT leave_request_id,request_number,total_days FROM leave_requests WHERE status='PENDING'",fetch=True)
        assert len(requests)==1 and requests[0][2]==2
        identity,number,_=requests[0]
        assert client().post('/leave/requests/add',data=dict(FORM,start_date='2027-01-02',end_date='2027-01-03',leave_type_id='2')).status_code==409
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE module='LEAVE'",fetch=True)==[(0,)]
        assert client().post(f'/leave/requests/{identity}/approve').status_code==302
        assert sql("SELECT attendance_date,status FROM attendance_records WHERE attendance_date BETWEEN '2027-01-01' AND '2027-01-02' ORDER BY attendance_date",fetch=True)==[(date(2027,1,1),'ON_LEAVE'),(date(2027,1,2),'ON_LEAVE')]
        after=snapshot()
        for action,data in (('approve',{}),('reject',{'rejection_reason':'not pending'}),('cancel',{})):
            assert client().post(f'/leave/requests/{identity}/{action}',data=data).status_code==409
        assert snapshot()==after
        print('PASS concurrent/overlapping requests: one commit, one conflict, existing calendar days, pending-only transitions and unchanged no-CREATE-audit behavior')
        def create(employee,start,end,leave_type=1):
            return repo.create_leave_request(employee,leave_type,date.fromisoformat(start),date.fromisoformat(end),(date.fromisoformat(end)-date.fromisoformat(start)).days+1,'PRIVATE synthetic',1)[0]
        first=create(3,'2028-01-01','2028-01-04');second=create(3,'2028-02-01','2028-02-04')
        barrier=__import__('threading').Barrier(2)
        def approve(target):
            c=client();barrier.wait(timeout=10)
            return c.post(f'/leave/requests/{target}/approve').status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(approve,(first,second)))
        assert sorted(codes)==[302,409],codes
        assert sql("SELECT COUNT(*) FROM leave_requests WHERE employee_id=3 AND status='APPROVED'",fetch=True)==[(1,)]
        assert sql('SELECT COUNT(*) FROM attendance_records WHERE employee_id=3',fetch=True)==[(4,)]
        # Conflicting manual Attendance blocks the entire approval, preserving all dates.
        conflict=create(4,'2029-01-01','2029-01-02')
        sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(4,'2029-01-02','PRESENT',1)")
        after=snapshot();assert client().post(f'/leave/requests/{conflict}/approve').status_code==409;assert snapshot()==after
        sql("UPDATE attendance_records SET status='ON_LEAVE',notes='Existing history' WHERE employee_id=4")
        sql("CREATE TRIGGER reject_leave_attendance BEFORE INSERT ON attendance_records FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic failure'")
        after=snapshot();assert client().post(f'/leave/requests/{conflict}/approve').status_code==503;assert snapshot()==after
        sql('DROP TRIGGER reject_leave_attendance')
        assert client().post(f'/leave/requests/{conflict}/approve').status_code==302
        assert sql("SELECT notes FROM attendance_records WHERE employee_id=4 AND attendance_date='2029-01-02'",fetch=True)==[('Existing history',)]
        print('PASS competing approvals cannot overspend existing entitlement; Attendance conflicts/failures rollback, existing ON_LEAVE history retained')
        # Failure after the first real Attendance insert rolls the entire transaction back.
        partial=create(4,'2030-01-01','2030-01-02')
        sql("CREATE TRIGGER reject_second_leave_day BEFORE INSERT ON attendance_records FOR EACH ROW BEGIN IF NEW.attendance_date='2030-01-02' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic second-day failure'; END IF; END")
        after=snapshot();assert client().post(f'/leave/requests/{partial}/approve').status_code==503;assert snapshot()==after
        sql('DROP TRIGGER reject_second_leave_day')
        factory=repo.get_connection
        class CommitFailure:
            def __init__(self,committed=False):self.db=factory();self.committed=committed
            def __getattr__(self,name):return getattr(self.db,name)
            def commit(self):
                if self.committed:self.db.commit()
                raise mysql.connector.Error('synthetic lost acknowledgment',errno=2013)
        after=snapshot()
        with patch.object(repo,'get_connection',side_effect=CommitFailure):
            assert client().post(f'/leave/requests/{partial}/approve').status_code==503
        assert snapshot()==after
        with patch.object(repo,'get_connection',side_effect=lambda:CommitFailure(True)):
            assert client().post(f'/leave/requests/{partial}/approve').status_code==503
        assert sql('SELECT status FROM leave_requests WHERE leave_request_id=%s',(partial,),True)==[('APPROVED',)]
        assert snapshot()[2]==after[2]
        print('PASS partial Attendance writes/precommit errors rollback; lost committed acknowledgment returns uncertainty without success audit or retry')
        malformed=create(2,'2036-01-01','2036-01-01')
        sql("UPDATE leave_requests SET start_date='0000-00-00' WHERE leave_request_id=%s",(malformed,))
        after=snapshot()
        assert client().post(f'/leave/requests/{malformed}/approve').status_code==409
        assert snapshot()==after
        # Retain the synthetic corrupt record as cancelled history; never repair
        # real records automatically or allow its wide range to block new fixtures.
        assert client().post(f'/leave/requests/{malformed}/cancel').status_code==302
        rejected=create(2,'2031-01-01','2031-01-01')
        response=client().post(f'/leave/requests/{rejected}/reject',data={'rejection_reason':'X'*501})
        assert response.status_code==400 and 'X'*501 in response.get_data(as_text=True)
        assert client().post(f'/leave/requests/{rejected}/reject',data={'rejection_reason':'PRIVATE rejected reason'}).status_code==302
        assert sql('SELECT status,rejection_reason FROM leave_requests WHERE leave_request_id=%s',(rejected,),True)==[('REJECTED','PRIVATE rejected reason')]
        cancelled=create(2,'2031-01-01','2031-01-01')
        assert client().post(f'/leave/requests/{cancelled}/cancel').status_code==302
        # NULL entitlement and cross-year days retain the existing approval behavior.
        cross=create(2,'2032-12-31','2033-01-01',4)
        sql("CREATE TRIGGER reject_leave_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic audit failure'")
        try:assert client().post(f'/leave/requests/{cross}/approve').status_code==302
        finally:sql('DROP TRIGGER reject_leave_audit')
        assert sql('SELECT status FROM leave_requests WHERE leave_request_id=%s',(cross,),True)==[('APPROVED',)]
        finite_cross=create(4,'2034-12-31','2035-01-01')
        assert client().post(f'/leave/requests/{finite_cross}/approve').status_code==302
        balances=repo.get_employee_leave_balances(4,2034)
        assert next(b for b in balances if b['leave_type_id']==1)['used_days']==1
        assert next(b for b in repo.get_employee_leave_balances(4,2035) if b['leave_type_id']==1)['used_days']==1
        # Maximum DATE no longer overflows after the final day.
        maximum=create(2,'9999-12-31','9999-12-31',4)
        assert client().post(f'/leave/requests/{maximum}/approve').status_code==302
        events=sql("SELECT action,entity_id,description FROM audit_logs WHERE module='LEAVE'",fetch=True)
        assert len(events)==8,events
        assert not any('PRIVATE' in str(event) or 'reason' in event[2] for event in events)
        print('PASS reject/cancel release overlap; null entitlement/cross-year/maximum dates, private-reason exclusion and best-effort audit failure isolation')
        # Physical type limits are enforced even with non-strict SQL mode.
        after=snapshot()
        for value in ('NaN','Infinity','1000','-1','.001'):
            assert client().post('/leave/types/add',data=dict(TYPE,annual_entitlement=value)).status_code==400
        assert snapshot()==after
        assert client().post('/leave/types/add',data=TYPE).status_code==302
        type_id=sql("SELECT leave_type_id FROM leave_types WHERE leave_code='SYN'",fetch=True)[0][0]
        assert client().post('/leave/types/add',data=TYPE).status_code==409
        assert client().post(f'/leave/types/{type_id}/edit',data=dict(TYPE,leave_name='Changed synthetic')).status_code==302
        assert sql('SELECT annual_entitlement,is_paid FROM leave_types WHERE leave_type_id=%s',(type_id,),True)==[(5,1)]
        repo.set_leave_type_active_status(type_id,False)
        assert client().post('/leave/requests/add',data=dict(FORM,employee_id='2',leave_type_id=str(type_id),start_date='2040-01-01',end_date='2040-01-01')).status_code==400
        next_id=sql("SELECT AUTO_INCREMENT FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='leave_requests'",fetch=True)[0][0]
        sql("UPDATE leave_requests SET request_number=%s WHERE request_number='HIST-0'",(f'LR-{next_id:06d}',))
        after=snapshot()
        assert client().post('/leave/requests/add',data=dict(FORM,employee_id='2',start_date='2042-01-01',end_date='2042-01-01')).status_code==409
        assert snapshot()==after
        sql("UPDATE leave_requests SET request_number='HIST-0' WHERE request_number=%s",(f'LR-{next_id:06d}',))
        # Capability rejection doesn't silently write to a nontransactional table.
        sql('CREATE TABLE unsupported_leave LIKE leave_requests');sql('ALTER TABLE unsupported_leave ENGINE=MyISAM')
        sql('RENAME TABLE leave_requests TO saved_leave, unsupported_leave TO leave_requests')
        try:
            empty=snapshot()
            assert client().post('/leave/requests/add',data=dict(FORM,start_date='2041-01-01',end_date='2041-01-01')).status_code==503
            assert snapshot()==empty
        finally:
            sql('RENAME TABLE leave_requests TO unsupported_leave, saved_leave TO leave_requests');sql('DROP TABLE unsupported_leave')
        assert sql("SELECT COUNT(*) FROM leave_requests WHERE request_number LIKE 'HIST-%'",fetch=True)==[(63,)]
        assert sql("SELECT COUNT(*) FROM leave_requests WHERE request_number LIKE 'TMP-%'",fetch=True)==[(0,)]
        print('PASS type overflow/duplicate/activation validation, transactional storage admission and historical records preserved')
        print('SUCCESS: Leave regression verified only synthetic disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
