"""Help Desk on a verified disposable MySQL server; no company settings/data."""
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
from test_help_desk import FORM


def run(port, data_dir):
    original_connect=mysql.connector.connect
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with original_connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_helpdesk_synthetic');cur.execute('USE erp_helpdesk_synthetic')
        for name in ('core','inventory','procurement','help_desk','help_desk_history','audit_logs'):
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        cur.execute("INSERT INTO permissions(permission_code) VALUES ('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage')")
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'IT Manager'),(2,'Synthetic viewer'),(3,'Super Admin')")
        password=generate_password_hash('synthetic-password')
        cur.executemany('INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES(%s,%s,%s,%s,%s)',[(1,1,'attendance-manager',password,1),(2,2,'attendance-viewer',password,1),(3,1,'attendance-disabled',password,0)])
        cur.execute('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
        cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='helpdesk.view'")
        cur.execute("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'OLD','Historical department',0)")
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id,employment_status) VALUES(1,'ATT%_!','Synthetic','Employee',1,'Inactive'),(2,'OTHER','Other','Employee',NULL,'Active')")
        db.commit();cur.close()
    options['database']='erp_helpdesk_synthetic'
    def connect():
        db=original_connect(**options)
        cur=db.cursor();cur.execute("SET SESSION sql_mode='' ");cur.close()
        return db
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();cur.close();return result
    def snapshot():return tuple(sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('helpdesk_tickets','helpdesk_ticket_history','audit_logs'))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-helpdesk-sql',ERP_ENV='testing',DB_HOST='127.0.0.1',DB_PORT=str(port),DB_USER='root',DB_PASSWORD='synthetic-configuration',DB_NAME=options['database']))
        stack.enter_context(patch('mysql.connector.connect',side_effect=lambda **kw:connect()))
        erp=importlib.import_module('app');repo=importlib.import_module('help_desk_repository')
        import database
        database.invalidate_compatibility();stack.callback(database.invalidate_compatibility)
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=csrf_client(erp.app)
            if uid:
                with c.session_transaction() as session:stamp_session(erp.app,session,user_state(user_id=uid,role_id=2 if uid==2 else 1,username='attendance-viewer' if uid==2 else 'attendance-manager',password_hash=password))
            return c
        sql("INSERT INTO users(user_id,role_id,username,password_hash,is_active) SELECT 4,2,'wrong-role',password_hash,1 FROM users WHERE user_id=1")
        sql("INSERT INTO users(user_id,role_id,username,password_hash,is_active) SELECT 5,3,'super-technician',password_hash,1 FROM users WHERE user_id=1")
        sql("INSERT INTO users(user_id,role_id,username,password_hash,is_active) SELECT 6,1,'other-technician',password_hash,1 FROM users WHERE user_id=1")
        sql("INSERT INTO helpdesk_categories(category_id,category_code,category_name,is_active) VALUES(1,'ACTIVE','Active category',1),(2,'OLD','Historical category',0)")
        with connect() as db:
            cur=db.cursor()
            cur.executemany("INSERT INTO helpdesk_tickets(ticket_number,employee_id,department_id,category_id,subject,description,priority,status,assigned_to,created_by,created_at) VALUES(%s,1,1,2,'Historical subject','Historical description','HIGH','CANCELLED',3,1,'2020-01-01')",[(f'ARCH-{i}',) for i in range(63)])
            cur.execute("INSERT INTO helpdesk_ticket_history(ticket_id,action_type,old_status,new_status,details,changed_by,created_at) SELECT ticket_id,'STATUS_CHANGE','OPEN','CANCELLED','Historical fixture',1,'2020-01-01' FROM helpdesk_tickets")
            db.commit()
        before=snapshot()
        for size,count in ((25,25),(50,50),(100,63)):
            page=repo.get_helpdesk_ticket_page(dict(search='ATT%_!',status='CANCELLED',priority='HIGH',category_id='2',assigned_to='3',page_size=str(size)))
            assert len(page['records'])==count and page['summary']['total_tickets']==63
            assert page['summary']['cancelled_count']==63 and page['summary']['open_count']==0
        assert repo.get_helpdesk_ticket_page(dict(search='ATT_'))['summary']['total_tickets']==0
        assert len(repo.get_helpdesk_ticket_page(dict(search='ARCH-',page='2147483647'))['records'])==13
        assert len(repo.get_filtered_helpdesk_tickets(search_text='Historical description',status='CANCELLED',priority='HIGH',category_id=2))==63
        old_id=sql("SELECT ticket_id FROM helpdesk_tickets WHERE ticket_number='ARCH-0'",fetch=True)[0][0]
        assert repo.get_helpdesk_ticket_history(old_id)[0]['details']=='Historical fixture'
        assert any(user['user_id']==3 and not user['is_active'] for user in repo.get_helpdesk_filter_users())
        assert client(2).get('/it/help-desk?category_id=2&assigned_to=3').status_code==200
        for bad in ({'page_size':'26'},{'assigned_to':'1e2'},{'priority':'OTHER'},{'status':'INVALID'},{'search':'x'*101}):
            assert client().get('/it/help-desk',query_string=bad).status_code==400
        for bad in (dict(FORM,employee_id='0'),dict(FORM,employee_id='999'),dict(FORM,category_id='2'),dict(FORM,category_id='999'),dict(FORM,subject='X'*151),dict(FORM,description='\U0001f642'*16384),dict(FORM,priority='OTHER')):
            assert client().post('/it/help-desk/add',data=bad).status_code==400
        from werkzeug.datastructures import MultiDict
        duplicate=MultiDict(FORM);duplicate.add('employee_id','2')
        assert client().post('/it/help-desk/add',data=duplicate).status_code==400
        assert client(2).post('/it/help-desk/add',data=FORM).status_code==302
        assert client(3).post('/it/help-desk/add',data=FORM).status_code==302
        assert client().post('/it/help-desk/add',data=FORM,headers={'X-CSRFToken':'bad'}).status_code==400
        assert snapshot()==before
        print('PASS exact 25/50/100 pages, full filtered counts, literal search, stable ordering, legacy filter/history APIs and inactive historical references; rejected requests preserve snapshots')
        assert client().post('/it/help-desk/add',data=dict(FORM,department_id='999')).status_code==302
        identity,number,department=sql("SELECT ticket_id,ticket_number,department_id FROM helpdesk_tickets WHERE status='OPEN'",fetch=True)[0]
        assert department==1 and number==f'HD-{identity:06d}'
        assert repo.get_helpdesk_ticket_page(dict(assigned_to='unassigned'))['summary']['total_tickets']==1
        events=sql("SELECT action,entity_id,description FROM audit_logs WHERE module='HELP_DESK'",fetch=True)
        assert events==[('CREATE',str(identity),f'Help Desk ticket {identity}: create committed.')]
        history=repo.get_helpdesk_ticket_history(identity)
        assert len(history)==1 and history[0]['action_type']=='CREATED'
        for target in ('0','999','3','4'):
            after=snapshot()
            assert client().post(f'/it/help-desk/{identity}/assign',data={'assigned_to':target}).status_code==400
            assert snapshot()==after
        after=snapshot();assert client().post(f'/it/help-desk/{identity}/start').status_code==409;assert snapshot()==after
        import threading,time
        def race(path,forms):
            barrier=threading.Barrier(2)
            def send(form):
                c=client();barrier.wait(timeout=10)
                return c.post(path,data=form).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:return sorted(pool.map(send,forms))
        assert race(f'/it/help-desk/{identity}/assign',[{'assigned_to':'5'}]*2)==[302,302]
        assert sql("SELECT COUNT(*) FROM helpdesk_ticket_history WHERE ticket_id=%s AND action_type='ASSIGNED'",(identity,),True)==[(1,)]
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE module='HELP_DESK' AND action='ASSIGN'",fetch=True)==[(1,)]
        assert race(f'/it/help-desk/{identity}/start',[{},{}])==[302,409]
        assert race(f'/it/help-desk/{identity}/resolve',[{'resolution':'PRIVATE '+('x'*400)},{'resolution':'PRIVATE alternative'}])==[302,409]
        resolved=sql('SELECT resolution,resolved_at FROM helpdesk_tickets WHERE ticket_id=%s',(identity,),True)[0]
        assert resolved[1] is not None
        assert sql("SELECT details FROM helpdesk_ticket_history WHERE ticket_id=%s AND action_type='RESOLVED'",(identity,),True)==[(resolved[0][:255],)]
        assert race(f'/it/help-desk/{identity}/close',[{},{}])==[302,409]
        assert sql('SELECT status FROM helpdesk_tickets WHERE ticket_id=%s',(identity,),True)==[('CLOSED',)]
        history=repo.get_helpdesk_ticket_history(identity)
        assert [h['action_type'] for h in history]==['STATUS_CHANGE','RESOLVED','STATUS_CHANGE','ASSIGNED','CREATED']
        assert len(sql("SELECT * FROM audit_logs WHERE module='HELP_DESK'",fetch=True))==5
        after=snapshot()
        assert client().post(f'/it/help-desk/{identity}/assign',data={'assigned_to':'1'}).status_code==409
        assert client().post('/it/help-desk/2147483647/start').status_code==404
        assert snapshot()==after
        print('PASS locked workflow races: same assignment is one history/audit; start/resolve/close one winner; exact committed statuses, history prefix and timestamps')
        def create(subject='Another synthetic'):
            return repo.create_helpdesk_ticket(1,None,1,subject,'PRIVATE description','MEDIUM',1)[0]
        other=create()
        def observe_wait(future):
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if sql('SELECT COUNT(*) FROM performance_schema.data_lock_waits',fetch=True)[0][0]:return
                if future.done():raise AssertionError('Expected a real eligibility lock wait')
                time.sleep(.05)
            raise AssertionError('No lock wait observed')
        # Deactivation commits while the waiting request still has to recheck the
        # same locked eligibility row. No mocked precheck substitutes for SQL.
        with connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            cur=blocker.cursor();cur.execute('SELECT category_id FROM helpdesk_categories WHERE category_id=1 FOR UPDATE');cur.fetchall()
            future=pool.submit(lambda:client().post('/it/help-desk/add',data=FORM).status_code)
            observe_wait(future)
            cur.execute('UPDATE helpdesk_categories SET is_active=0 WHERE category_id=1');blocker.commit()
            assert future.result(timeout=15)==400
        sql('UPDATE helpdesk_categories SET is_active=1 WHERE category_id=1')
        with connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            cur=blocker.cursor();cur.execute('SELECT user_id FROM users WHERE user_id=6 FOR UPDATE');cur.fetchall()
            future=pool.submit(lambda:client().post(f'/it/help-desk/{other}/assign',data={'assigned_to':'6'}).status_code)
            observe_wait(future)
            cur.execute('UPDATE users SET is_active=0 WHERE user_id=6');blocker.commit()
            assert future.result(timeout=15)==400
        sql('UPDATE users SET is_active=1 WHERE user_id=6')
        with connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            cur=blocker.cursor();cur.execute('SELECT role_id FROM roles WHERE role_id=3 FOR UPDATE');cur.fetchall()
            future=pool.submit(lambda:client().post(f'/it/help-desk/{other}/assign',data={'assigned_to':'5'}).status_code)
            observe_wait(future)
            cur.execute("UPDATE roles SET role_name='No longer assignable' WHERE role_id=3");blocker.commit()
            assert future.result(timeout=15)==400
        sql("UPDATE roles SET role_name='Super Admin' WHERE role_id=3")
        print('PASS observed MySQL lock waits: category deactivation, user disable and role rename cannot race into stale eligibility')
        sql("CREATE TRIGGER reject_helpdesk_history BEFORE INSERT ON helpdesk_ticket_history FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic history failure'")
        after=snapshot()
        assert client().post('/it/help-desk/add',data=FORM).status_code==503
        assert snapshot()==after
        assert client().post(f'/it/help-desk/{other}/assign',data={'assigned_to':'5'}).status_code==503
        assert snapshot()==after
        sql('DROP TRIGGER reject_helpdesk_history')
        assert client().post(f'/it/help-desk/{other}/assign',data={'assigned_to':'5'}).status_code==302
        sql("CREATE TRIGGER reject_helpdesk_history BEFORE INSERT ON helpdesk_ticket_history FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic history failure'")
        after=snapshot();assert client().post(f'/it/help-desk/{other}/start').status_code==503;assert snapshot()==after
        sql('DROP TRIGGER reject_helpdesk_history')
        factory=repo.get_connection
        class CommitFailure:
            def __init__(self,committed=False):self.db=factory();self.committed=committed
            def __getattr__(self,name):return getattr(self.db,name)
            def commit(self):
                if self.committed:self.db.commit()
                raise mysql.connector.Error('synthetic lost acknowledgment',errno=2013)
        after=snapshot()
        with patch.object(repo,'get_connection',side_effect=CommitFailure):
            assert client().post(f'/it/help-desk/{other}/start').status_code==503
        assert snapshot()==after
        with patch.object(repo,'get_connection',side_effect=lambda:CommitFailure(True)):
            assert client().post(f'/it/help-desk/{other}/start').status_code==503
        assert sql('SELECT status FROM helpdesk_tickets WHERE ticket_id=%s',(other,),True)==[('IN_PROGRESS',)]
        assert snapshot()[2]==after[2]
        assert len(snapshot()[1])==len(after[1])+1
        print('PASS CREATE/ASSIGN/START history failures roll back; precommit failure preserves snapshots; lost committed acknowledgment retains atomic history without success audit or replay')
        sql("CREATE TRIGGER reject_helpdesk_history BEFORE INSERT ON helpdesk_ticket_history FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic history failure'")
        after=snapshot()
        assert client().post(f'/it/help-desk/{other}/resolve',data={'resolution':'PRIVATE failed resolution'}).status_code==503
        assert snapshot()==after
        sql('DROP TRIGGER reject_helpdesk_history')
        # A central audit failure is intentionally independent of the business transaction.
        sql("CREATE TRIGGER reject_helpdesk_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic audit failure'")
        try:assert client().post(f'/it/help-desk/{other}/resolve',data={'resolution':'PRIVATE audit-outage resolution'}).status_code==302
        finally:sql('DROP TRIGGER reject_helpdesk_audit')
        assert sql('SELECT status FROM helpdesk_tickets WHERE ticket_id=%s',(other,),True)==[('RESOLVED',)]
        sql("CREATE TRIGGER reject_helpdesk_history BEFORE INSERT ON helpdesk_ticket_history FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic history failure'")
        after=snapshot();assert client().post(f'/it/help-desk/{other}/close').status_code==503;assert snapshot()==after
        sql('DROP TRIGGER reject_helpdesk_history')
        # Final-number collision must roll back the temporary-number insert too.
        next_id=sql("SELECT AUTO_INCREMENT FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='helpdesk_tickets'",fetch=True)[0][0]
        sql("UPDATE helpdesk_tickets SET ticket_number=%s WHERE ticket_number='ARCH-0'",(f'HD-{next_id:06d}',))
        after=snapshot();assert client().post('/it/help-desk/add',data=FORM).status_code==409;assert snapshot()==after
        sql("UPDATE helpdesk_tickets SET ticket_number='ARCH-0' WHERE ticket_number=%s",(f'HD-{next_id:06d}',))
        assert sql("SELECT COUNT(*) FROM helpdesk_tickets WHERE ticket_number LIKE 'TMP-%'",fetch=True)==[(0,)]
        # TEXT accepts its exact byte boundary without non-strict coercion.
        boundary=repo.create_helpdesk_ticket(2,None,1,'Boundary','x'*65535,'LOW',1)[0]
        assert sql('SELECT OCTET_LENGTH(description) FROM helpdesk_tickets WHERE ticket_id=%s',(boundary,),True)==[(65535,)]
        after=snapshot()
        sql('ALTER TABLE helpdesk_tickets DROP INDEX ticket_number')
        assert client().post('/it/help-desk/add',data=FORM).status_code==503
        assert snapshot()==after
        sql('ALTER TABLE helpdesk_tickets ADD UNIQUE INDEX ticket_number(ticket_number)')
        # Keep the live historical table unchanged while testing engine admission.
        sql('CREATE TABLE unsupported_history LIKE helpdesk_ticket_history');sql('ALTER TABLE unsupported_history ENGINE=MyISAM')
        sql('RENAME TABLE helpdesk_ticket_history TO saved_history, unsupported_history TO helpdesk_ticket_history')
        try:
            empty=snapshot();assert client().post(f'/it/help-desk/{boundary}/assign',data={'assigned_to':'5'}).status_code==503;assert snapshot()==empty
        finally:
            sql('RENAME TABLE helpdesk_ticket_history TO unsupported_history, saved_history TO helpdesk_ticket_history');sql('DROP TABLE unsupported_history')
        after=snapshot()
        sql('RENAME TABLE helpdesk_ticket_history TO missing_history_fixture')
        try:
            assert client().post(f'/it/help-desk/{boundary}/assign',data={'assigned_to':'5'}).status_code==503
            assert client().get(f'/it/help-desk/{boundary}').status_code==503
        finally:sql('RENAME TABLE missing_history_fixture TO helpdesk_ticket_history')
        assert snapshot()==after
        assert sql("SELECT COUNT(*) FROM helpdesk_tickets WHERE ticket_number LIKE 'ARCH-%'",fetch=True)==[(63,)]
        events=sql("SELECT action,entity_id,description FROM audit_logs WHERE module='HELP_DESK'",fetch=True)
        assert len(events)==6,events
        assert all('PRIVATE' not in event[2] and 'Synthetic' not in event[2] for event in events)
        assert client(2).get(f'/it/help-desk/{identity}').status_code==200
        after=snapshot()
        for action,form in (('assign',{'assigned_to':'5'}),('start',{}),('resolve',{'resolution':'denied'}),('close',{})):
            assert client(2).post(f'/it/help-desk/{identity}/{action}',data=form).status_code==302
        assert snapshot()==after
        print('PASS audit outage cannot reverse commit; all workflow history failures roll back; number collision, exact TEXT bytes, missing uniqueness/nontransactional/missing history, safe 503 and viewer denials')
        print('SUCCESS: Help Desk reliability used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
