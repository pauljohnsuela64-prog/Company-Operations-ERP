"""Fresh authorization and credential/session security on disposable MySQL only."""
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash
import mysql_audit_smoke as harness


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur=connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_security_test')
        cur.execute('USE erp_security_test')
        for name in ('core','inventory','procurement','audit_logs'):
            text=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',text).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        connection.commit()
    options['database']='erp_security_test'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as connection:
            cur=connection.cursor()
            cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            return result
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Operator'),(2,'Restricted'),(3,'Administrator')")
    for uid,role,name in ((1,1,'operator'),(3,3,'administrator'),(4,1,'deleted-user')):
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES (%s,%s,%s,%s)',(uid,role,name,generate_password_hash('original-test-password')))
    for role,code in ((1,'procurement.view'),(1,'procurement.suppliers.manage'),(3,'users.manage')):
        pid=sql('INSERT INTO permissions(permission_code) VALUES (%s)',(code,))
        sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (%s,%s)',(role,pid))
    supplier=sql("INSERT INTO suppliers(supplier_code,supplier_name) VALUES ('SECURITY','Synthetic Supplier')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-security-integration-key',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database')
        stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        stack.enter_context(patch.object(erp.app.logger,'exception'))
        def login(name='operator',password='original-test-password'):
            client=erp.app.test_client()
            response=client.post('/login',data={'username':name,'password':password})
            assert response.status_code==302 and response.location.endswith('/dashboard')
            return client
        clients=[login(),login()]
        for client in clients:
            assert client.get('/procurement/suppliers').status_code==200
            with client.session_transaction() as session:
                assert 'permissions' not in session and 'password_hash' not in session
        assert sql('SELECT last_login_at IS NOT NULL FROM users WHERE user_id=1',fetch=True)==[(1,)]
        print('PASS actual login, concurrent client sessions, last-login update, minimal signed session')
        sql('DELETE FROM role_permissions WHERE role_id=1')
        for client in clients:
            assert client.get('/procurement/suppliers').location.endswith('/dashboard')
            assert client.post(f'/procurement/suppliers/{supplier}/status').location.endswith('/dashboard')
        assert sql('SELECT is_active FROM suppliers WHERE supplier_id=%s',(supplier,),True)==[(1,)]
        for pid, in sql("SELECT permission_id FROM permissions WHERE permission_code LIKE 'procurement.%'",fetch=True):
            sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(pid,))
        assert clients[0].get('/procurement/suppliers').status_code==200
        sql('UPDATE users SET role_id=2 WHERE user_id=1')
        for client in clients:
            assert client.get('/procurement/suppliers').location.endswith('/dashboard')
            with client.session_transaction() as session:assert session['role_name']=='Restricted'
        sql('UPDATE users SET role_id=1 WHERE user_id=1')
        assert clients[1].get('/procurement/suppliers').status_code==200
        print('PASS real committed permission revocation and role changes affect both existing clients without logout')
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        for client in clients:
            assert client.get('/procurement/suppliers').location.endswith('/login')
            with client.session_transaction() as session:assert 'user_id' not in session
        sql('UPDATE users SET is_active=1 WHERE user_id=1')
        deleted=login('deleted-user')
        sql('DELETE FROM users WHERE user_id=4')
        assert deleted.get('/procurement/suppliers').location.endswith('/login')
        print('PASS disabled and deleted users rejected on subsequent requests')
        clients=[login(),login()]
        admin=login('administrator')
        assert admin.post('/admin/users/1/reset-password',data={'password':'new-test-password','confirm_password':'new-test-password'}).status_code==302
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE action='RESET_PASSWORD'",fetch=True)==[(1,)]
        for client in clients:assert client.get('/procurement/suppliers').location.endswith('/login')
        clients=[login(password='new-test-password'),login(password='new-test-password')]
        assert clients[0].get('/procurement/suppliers').status_code==200
        print('PASS real audited password reset invalidates both old sessions and permits new login')
        for field,age in (('auth_seen',1801),('auth_started',28801)):
            client=login(password='new-test-password')
            with client.session_transaction() as session:session[field]-=age
            assert client.get('/procurement/suppliers').location.endswith('/login')
        with patch.object(erp,'get_authorization_state',side_effect=mysql.connector.InterfaceError('isolated outage')):
            assert clients[0].post(f'/procurement/suppliers/{supplier}/status').status_code==503
            assert clients[0].get('/logout').status_code==302
        assert clients[1].get('/procurement/suppliers').status_code==200
        assert sql('SELECT is_active FROM suppliers WHERE supplier_id=%s',(supplier,),True)==[(1,)]
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE action='LOGOUT'",fetch=True)==[(1,)]
        assert clients[1].get('/logout').status_code==302
        assert sql("SELECT COUNT(*) FROM audit_logs WHERE action='LOGOUT'",fetch=True)==[(2,)]
        print('PASS idle/absolute expiry, fail-closed outage, logout isolation, and logout audit preservation')
    print('SUCCESS: security integration passed; no company database accessed')


if __name__=='__main__':
    harness.run=run
    harness.main()
