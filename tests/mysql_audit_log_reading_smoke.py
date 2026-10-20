"""Audit Logs on a verified disposable MySQL server; no company settings/data."""
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session, user_state


def run(port, data_dir):
    original_connect=mysql.connector.connect
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with original_connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_audit_reading_synthetic');cur.execute('USE erp_audit_reading_synthetic')
        for name in ('core','inventory','procurement','audit_logs'):
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        cur.execute("INSERT INTO permissions(permission_code) VALUES ('it_assets.view'),('it_assets.manage'),('helpdesk.view'),('helpdesk.manage'),('audit_logs.view')")
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'IT Manager'),(2,'Synthetic viewer'),(3,'Super Admin')")
        password=generate_password_hash('synthetic-password')
        cur.executemany('INSERT INTO users(user_id,role_id,username,password_hash,is_active) VALUES(%s,%s,%s,%s,%s)',[(1,1,'audit-manager',password,1),(2,2,'audit-viewer',password,1),(3,1,'audit-disabled',password,0)])
        cur.execute('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
        cur.execute("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='helpdesk.view'")
        cur.execute("INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(1,'OLD','Historical department',0)")
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id,employment_status) VALUES(1,'ATT%_!','Synthetic','Employee',1,'Inactive'),(2,'OTHER','Other','Employee',NULL,'Active')")
        db.commit();cur.close()
    options['database']='erp_audit_reading_synthetic'
    def connect():
        db=original_connect(**options)
        cur=db.cursor();cur.execute("SET SESSION sql_mode='' ");cur.close()
        return db
    def sql(query,params=(),fetch=False):
        with connect() as db:
            cur=db.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();cur.close();return result
    def snapshot():return tuple(sql('SELECT * FROM '+table+' ORDER BY 1,2',fetch=True) for table in ('audit_logs','employees','departments','users','roles','permissions','role_permissions'))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-audit-reading-sql',ERP_ENV='testing',DB_HOST='127.0.0.1',DB_PORT=str(port),DB_USER='root',DB_PASSWORD='synthetic-configuration',DB_NAME=options['database']))
        stack.enter_context(patch('mysql.connector.connect',side_effect=lambda **kw:connect()))
        erp=importlib.import_module('app');repo=importlib.import_module('audit_log_repository')
        import database
        database.invalidate_compatibility();stack.callback(database.invalidate_compatibility)
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=csrf_client(erp.app)
            if uid:
                with c.session_transaction() as session:stamp_session(erp.app,session,user_state(user_id=uid,role_id=2 if uid==2 else 1,username='audit-viewer' if uid==2 else 'audit-manager',password_hash=password))
            return c
        # Prove the empty database state before seeding historical synthetic rows.
        empty=client().get('/admin/audit-logs')
        assert empty.status_code==200 and 'No audit log records found.' in empty.get_data(as_text=True)
        with connect() as db:
            cur=db.cursor()
            cur.executemany("INSERT INTO audit_logs(user_id,username,module,action,entity_type,entity_id,description,created_at) VALUES(NULL,'Archived user','Legacy Ops','Read / Inspect','RECORD',%s,%s,'2001-02-03 12:00:00')",[(f'HIST-{i:05d}',f'Synthetic historical event {i}') for i in range(5005)])
            cur.execute("INSERT INTO audit_logs(user_id,username,module,action,entity_type,entity_id,description,created_at) VALUES(1,'Synthetic','LITERAL','READ','RECORD','SPECIAL','Literal needle%_! <img src=x onerror=alert(1)>','2026-01-02 12:00:00')")
            cur.executemany("INSERT INTO audit_logs(user_id,username,module,action,description,created_at) VALUES(1,'Synthetic','DATES','READ','Date boundary',%s)",[('2026-01-02 00:00:00',),('2026-01-02 23:59:59',),('2026-01-03 00:00:00',)])
            db.commit()
        before=snapshot()
        for size in (25,50,100):
            page=repo.get_audit_log_page(dict(module='Legacy Ops',action='Read / Inspect',page_size=str(size)))
            assert len(page['records'])==size and page['total']==5005
            assert all(row['user_id'] is None and row['username']=='Archived user' for row in page['records'])
            assert [row['audit_log_id'] for row in page['records']]==sorted((row['audit_log_id'] for row in page['records']),reverse=True)
        ids=[]
        for number in range(1,52):
            page=repo.get_audit_log_page(dict(module='Legacy Ops',page_size='100',page=str(number)),include_options=False)
            assert page['total']==5005
            ids.extend(row['audit_log_id'] for row in page['records'])
        assert len(ids)==len(set(ids))==5005 and ids==sorted(ids,reverse=True)
        final=repo.get_audit_log_page(dict(module='Legacy Ops',page_size='100',page='2147483647'))
        assert (final['filters']['page'],final['first'],final['last'],len(final['records']))==(51,5001,5005,5)
        assert len(repo.get_filtered_audit_logs(module='Legacy Ops'))==25
        assert repo.get_filtered_audit_logs(module='Legacy Ops',page=51,page_size=100)[-1]['audit_log_id']==ids[-1]
        response=client().get('/admin/audit-logs?module=Legacy+Ops&action=Read+%2F+Inspect&page=51&page_size=100')
        assert response.status_code==200 and 'Showing 5001-5005 of 5005 matching records' in response.get_data(as_text=True)
        assert 'no-store' in response.headers['Cache-Control'] and response.headers['Referrer-Policy']=='no-referrer'
        print('PASS 5005 historical records beyond old cap: complete traversal, stable timestamp/ID ties, 25/50/100 pages, precise totals, NULL actors and bounded compatibility API')
        for needle,count in (('needle%',1),('needle_',0),('needle%_!',1),("' OR 1=1 --",0),('\u2603',0)):
            assert repo.get_audit_log_page(dict(search=needle))['total']==count
        result=client().get('/admin/audit-logs?search=needle%25_%21')
        assert result.status_code==200
        assert '&lt;img src=x' in result.get_data(as_text=True) and '<img src=x' not in result.get_data(as_text=True)
        dates=dict(module='DATES',start_date='2026-01-02',end_date='2026-01-02')
        assert repo.get_audit_log_page(dates)['total']==2
        assert repo.get_audit_log_page(dict(start_date='1000-01-01',end_date='9999-12-31'))['total']==5009
        assert repo.get_audit_log_page(dict(start_date='9999-12-31',end_date='9999-12-31'))['total']==0
        assert repo.get_audit_log_page(dict(end_date='1000-01-01'))['total']==0
        assert repo.get_audit_log_page(dict(module='UNKNOWN'))['total']==0
        unknown=client().get('/admin/audit-logs?module=UNKNOWN&action=NO_SUCH_ACTION')
        assert unknown.status_code==200 and 'No audit log records match these filters.' in unknown.get_data(as_text=True)
        assert 'value="UNKNOWN" selected' in unknown.get_data(as_text=True)
        invalid=({'start_date':'2026-02-29'},{'start_date':'2026-02-01','end_date':'2026-01-01'},
                 {'page_size':'500'},{'page':'0'},{'module':'X'*51},{'search':'X'*101},{'date_from':'2026-01-01'}, {'search':'\x00'})
        for fields in invalid:
            result=client().get('/admin/audit-logs',query_string=fields)
            assert result.status_code==400 and 'Audit logs were not loaded.' in result.get_data(as_text=True)
            assert 'Showing 0' not in result.get_data(as_text=True)
        from werkzeug.datastructures import MultiDict
        assert client().get('/admin/audit-logs',query_string=MultiDict([('module','LITERAL'),('module','DATES')])).status_code==400
        assert client(0).get('/admin/audit-logs').location.endswith('/login')
        assert client(2).get('/admin/audit-logs').location.endswith('/dashboard')
        assert client(3).get('/admin/audit-logs').location.endswith('/login')
        for method in ('POST','PUT','PATCH','DELETE'):
            assert client().open('/admin/audit-logs',method=method).status_code==405
        assert snapshot()==before
        print('PASS literal wildcard/injection search, inclusive date boundaries/max date, empty/unknown filters, escaped HTML, invalid/denied/mutation requests and all audit/business/grant snapshots unchanged')
        # Inspect exactly what the repository issues; database also enforces the
        # READ ONLY transaction. No INSERT/UPDATE/DDL/commit may be added here.
        factory=repo.get_connection
        statements=[]
        class ReadCursor:
            def __init__(self,cursor):self.cursor=cursor
            def __getattr__(self,name):return getattr(self.cursor,name)
            def execute(self,query,params=()):
                assert query.lstrip().upper().startswith('SELECT'),query
                statements.append(query)
                return self.cursor.execute(query,params)
        class ReadConnection:
            def __init__(self):self.db=factory()
            def __getattr__(self,name):return getattr(self.db,name)
            def cursor(self,**kwargs):return ReadCursor(self.db.cursor(**kwargs))
            def commit(self):raise AssertionError('Read-only Audit Logs must never commit')
        with patch.object(repo,'get_connection',side_effect=ReadConnection):
            assert repo.get_audit_log_page(dates)['total']==2
        assert len(statements)==6 and snapshot()==before
        # Deterministic concurrent insert between COUNT and row/options reads.
        inserted=False
        class ConcurrentCursor(ReadCursor):
            def execute(self,query,params=()):
                nonlocal inserted
                result=super().execute(query,params)
                if query.startswith('SELECT COUNT(*) AS total') and not inserted:
                    inserted=True
                    sql("INSERT INTO audit_logs(username,module,action,description,created_at) VALUES('Synthetic concurrent','AFTER_SNAPSHOT','AFTER_SNAPSHOT','Explicit test writer','2030-01-01')")
                return result
        class ConcurrentConnection(ReadConnection):
            def cursor(self,**kwargs):return ConcurrentCursor(self.db.cursor(**kwargs))
        with patch.object(repo,'get_connection',side_effect=ConcurrentConnection):
            old=repo.get_audit_log_page({})
        assert old['total']==5009 and 'AFTER_SNAPSHOT' not in old['modules']
        assert all(row['module']!='AFTER_SNAPSHOT' for row in old['records'])
        assert repo.get_audit_log_page({})['total']==5010
        after=snapshot()
        assert len(after[0])==len(before[0])+1 and after[1:]==before[1:]
        assert after[0][:-1]==before[0]
        print('PASS observed SELECT-only reads, no commit, and real concurrent insert: total/page/options stay in one snapshot; fresh request sees only the explicit test writer addition')
        # Failures never return a partially read page or modify history.
        class FailedCursor(ReadCursor):
            def execute(self,query,params=()):
                if query.startswith('SELECT audit_log_id,'):raise mysql.connector.Error('PRIVATE injected read failure',errno=2013)
                return super().execute(query,params)
        class FailedConnection(ReadConnection):
            def cursor(self,**kwargs):return FailedCursor(self.db.cursor(**kwargs))
        with patch.object(repo,'get_connection',side_effect=FailedConnection):
            result=client().get('/admin/audit-logs')
            assert result.status_code==503 and 'PRIVATE' not in result.get_data(as_text=True)
        assert snapshot()==after
        # Capability checks do not convert/repair a legacy nontransactional table.
        sql('CREATE TABLE unsupported_audit LIKE audit_logs');sql('ALTER TABLE unsupported_audit ENGINE=MyISAM')
        sql('RENAME TABLE audit_logs TO saved_audit, unsupported_audit TO audit_logs')
        try:
            result=client().get('/admin/audit-logs')
            assert result.status_code==503 and 'Showing 0' not in result.get_data(as_text=True)
            assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(0,)]
        finally:
            sql('RENAME TABLE audit_logs TO unsupported_audit, saved_audit TO audit_logs');sql('DROP TABLE unsupported_audit')
        sql('RENAME TABLE audit_logs TO missing_audit_fixture')
        try:assert client().get('/admin/audit-logs').status_code==503
        finally:sql('RENAME TABLE missing_audit_fixture TO audit_logs')
        assert snapshot()==after
        # Actual permission revocation, existing session, no audit-history write.
        revoked=client()
        assert revoked.get('/admin/audit-logs').status_code==200
        sql("DELETE rp FROM role_permissions rp JOIN permissions p ON p.permission_id=rp.permission_id WHERE rp.role_id=1 AND p.permission_code='audit_logs.view'")
        assert revoked.get('/admin/audit-logs').location.endswith('/dashboard')
        assert snapshot()[0]==after[0]
        print('PASS read failure, missing/non-InnoDB audit table and same-session permission revocation fail closed without rewriting history')
        print('SUCCESS: Audit Logs read-only regression used only verified disposable MySQL')


if __name__=='__main__':
    harness.run=run
    harness.main()
