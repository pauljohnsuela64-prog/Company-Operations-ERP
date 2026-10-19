"""Session authorization and deployment configuration regressions, without MySQL."""
from contextlib import ExitStack
import importlib
import unittest
import time
from unittest.mock import patch, Mock

from flask import Flask, g
from security import configure_security, credential_marker
from security_helpers import user_state, stamp_session, csrf_client


class SessionSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack=ExitStack()
        cls.addClassCleanup(cls.stack.close)
        cls.stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-session-test',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.stack.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Real database access forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True,SESSION_IDLE_SECONDS=1800,SESSION_ABSOLUTE_SECONDS=28800))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state=user_state(permissions=['procurement.view','inventory.view'])
        self.loader=self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.suppliers=self.stack.enter_context(patch.object(self.erp,'get_all_suppliers',return_value=[]))
        self.client=csrf_client(self.erp.app)
        self.signin(self.client)

    def signin(self,client):
        with client.session_transaction() as session:
            stamp_session(self.erp.app,session,self.state)

    def request(self,client=None):
        return (client or self.client).get('/procurement/suppliers')

    def test_one_loader_per_request_shared_by_navigation_and_guard(self):
        html=self.request().get_data(as_text=True)
        self.loader.assert_called_once_with(7)
        self.assertIn('id="nav-procurement"',html)
        self.request()
        self.assertEqual(self.loader.call_count,2)

    def test_cookie_permissions_are_ignored_and_removed(self):
        self.state['permissions']=frozenset()
        with self.client.session_transaction() as session:
            session['permissions']=['procurement.view','users.manage']
        response=self.request()
        self.assertTrue(response.location.endswith('/dashboard'))
        self.suppliers.assert_not_called()
        with self.client.session_transaction() as session:
            self.assertNotIn('permissions',session)

    def test_disable_delete_missing_role_and_mismatched_identity_clear_sessions(self):
        for change in ('disable','delete','missing_role','identity'):
            with self.subTest(change=change):
                self.state=user_state(permissions=['procurement.view'])
                self.signin(self.client)
                if change=='disable': self.state['is_active']=False
                elif change=='delete': self.state=None
                elif change=='missing_role':self.state['role_name']=None
                else:self.state['user_id']=999
                response=self.request()
                self.assertTrue(response.location.endswith('/login'))
                with self.client.session_transaction() as session:self.assertNotIn('user_id',session)

    def test_permission_revocation_and_role_changes_affect_all_clients(self):
        second=csrf_client(self.erp.app)
        self.signin(second)
        self.assertEqual(self.request().status_code,200)
        self.assertEqual(self.request(second).status_code,200)
        self.state.update(role_id=43,role_name='Restricted',permissions=frozenset())
        for client in (self.client,second):
            self.assertTrue(self.request(client).location.endswith('/dashboard'))
            with client.session_transaction() as session:self.assertEqual(session['role_name'],'Restricted')
        self.state['permissions']=frozenset(['procurement.view'])
        self.assertEqual(self.request().status_code,200)

    def test_password_change_invalidates_all_clients_without_exposing_hash(self):
        second=csrf_client(self.erp.app)
        self.signin(second)
        with self.client.session_transaction() as session:
            self.assertNotIn('password_hash',session)
            self.assertNotIn('test-only',str(dict(session)))
        self.state['password_hash']='changed-secret-hash'
        for client in (self.client,second):self.assertTrue(self.request(client).location.endswith('/login'))
        self.signin(self.client)
        self.assertEqual(self.request().status_code,200)

    def test_marker_uses_secret_and_identity(self):
        with self.erp.app.app_context():
            first=credential_marker(self.state)
            self.assertNotEqual(first,credential_marker(dict(self.state,user_id=99)))
            with patch.dict(self.erp.app.config,SECRET_KEY='a-different-secret'):
                self.assertNotEqual(first,credential_marker(self.state))

    def test_legacy_and_malformed_metadata_require_reauthentication(self):
        for overrides in ({'auth_version':0},{'credential_marker':''},{'credential_marker':'\u00e9'*64},{'auth_started':None},{'auth_seen':'1'},{'auth_seen':float('inf')},{'auth_started':True},{'auth_started':300,'auth_seen':200}):
            with self.subTest(overrides=overrides):
                self.signin(self.client)
                with self.client.session_transaction() as session:session.update(overrides)
                self.assertTrue(self.request().location.endswith('/login'))
        with self.client.session_transaction() as session:
            session.clear();session.update(user_id=7,permissions=['users.manage'])
        self.assertTrue(self.request().location.endswith('/login'))
        self.loader.assert_not_called()

    def test_idle_expiry_boundary(self):
        base=time.time()
        with self.client.session_transaction() as session:session.update(auth_started=base,auth_seen=base)
        with patch('security._now',return_value=base+1800):
            self.assertTrue(self.request().location.endswith('/login'))
        self.loader.assert_not_called()

    def test_activity_refreshes_idle_but_not_absolute_start(self):
        base=time.time()
        with self.client.session_transaction() as session:session.update(auth_started=base,auth_seen=base)
        with patch('security._now',return_value=base+1000):self.assertEqual(self.request().status_code,200)
        with self.client.session_transaction() as session:
            self.assertEqual(session['auth_seen'],base+1000)
            self.assertEqual(session['auth_started'],base)
        with self.client.session_transaction() as session:session['auth_seen']=base+28799
        with patch('security._now',return_value=base+28800):self.assertTrue(self.request().location.endswith('/login'))

    def test_outage_fails_closed_preserves_session_and_prevents_business_actions(self):
        self.loader.side_effect=RuntimeError('outage')
        operation=self.stack.enter_context(patch.object(self.erp,'cancel_purchase_order'))
        self.assertEqual(self.client.post('/procurement/orders/1/cancel').status_code,503)
        operation.assert_not_called()
        self.assertEqual(self.client.get('/procurement/suppliers',headers={'Accept':'application/json'}).status_code,503)
        with self.client.session_transaction() as session:self.assertEqual(session['user_id'],7)
        self.loader.side_effect=lambda _:self.state
        self.assertEqual(self.request().status_code,200)

    def test_logout_audits_and_works_during_outage(self):
        for outage in (False,True):
            with self.subTest(outage=outage):
                self.signin(self.client)
                self.loader.side_effect=RuntimeError('outage') if outage else lambda _:self.state
                with patch.object(self.erp,'create_audit_log') as audit:
                    self.assertTrue(self.client.post('/logout').location.endswith('/login'))
                    self.assertEqual(audit.call_args.kwargs['action'],'LOGOUT')
                with self.client.session_transaction() as session:self.assertNotIn('user_id',session)

    def test_static_and_anonymous_requests_do_not_query_authorization(self):
        anonymous=csrf_client(self.erp.app)
        self.assertEqual(anonymous.get('/login').status_code,200)
        response=self.client.get('/static/js/navigation.js')
        self.assertEqual(response.status_code,200)
        response.close()
        self.loader.assert_not_called()

    def test_all_existing_business_post_routes_deny_revoked_permissions(self):
        self.state['permissions']=frozenset()
        import re
        count=0
        for rule in self.erp.app.url_map.iter_rules():
            if 'POST' not in rule.methods or rule.endpoint in ('login', 'logout'):
                continue
            with self.subTest(endpoint=rule.endpoint):
                path=re.sub(r'<int:[^>]+>', '1', rule.rule)
                response=self.client.post(path)
                self.assertEqual(response.status_code,302)
                self.assertTrue(response.location.endswith('/dashboard'))
                count+=1
        self.assertGreater(count,50)

    def test_invalid_session_json_returns_401(self):
        self.state=None
        response=self.client.get('/procurement/suppliers',headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,401)

    def test_real_login_rotates_session_and_stamps_security_metadata(self):
        anonymous=csrf_client(self.erp.app)
        with anonymous.session_transaction() as session:session['old']='discard'
        with patch.object(self.erp,'get_user_by_username',return_value=self.state), patch.object(self.erp,'check_password_hash',return_value=True), patch.object(self.erp,'update_last_login') as last:
            response=anonymous.post('/login',data={'username':'test','password':'test'})
        self.assertTrue(response.location.endswith('/dashboard'))
        last.assert_called_once_with(7)
        with anonymous.session_transaction() as session:
            self.assertNotIn('old',session)
            self.assertNotIn('permissions',session)
            self.assertIn('auth_started',session)
            self.assertIn('credential_marker',session)
        self.assertEqual(self.request(anonymous).status_code,200)

    def test_authorization_repository_uses_one_query_and_handles_empty_permissions(self):
        repository=importlib.import_module('user_repository')
        connection=Mock()
        cursor=connection.cursor.return_value
        cursor.fetchall.return_value=[dict(self.state,permission_code=None)]
        with patch.object(repository,'get_connection',return_value=connection):result=repository.get_authorization_state(7)
        cursor.execute.assert_called_once()
        self.assertEqual(result['permissions'],frozenset())
        connection.close.assert_called_once()


class SecurityConfigurationTests(unittest.TestCase):
    def test_development_and_production_profiles(self):
        for mode in ('development','production'):
            app=Flask(__name__)
            configure_security(app,{'SECRET_KEY':'a'*40,'ERP_ENV':mode})
            self.assertEqual(app.config['SESSION_COOKIE_SECURE'],mode=='production')
            self.assertTrue(app.config['SESSION_COOKIE_HTTPONLY'])
            self.assertEqual(app.config['SESSION_COOKIE_SAMESITE'],'Lax')
            self.assertFalse(app.debug)
            self.assertEqual(app.config['SESSION_IDLE_SECONDS'],1800)
            self.assertEqual(app.config['SESSION_ABSOLUTE_SECONDS'],28800)
            with app.test_request_context():
                from flask import session
                session['test']=1
                response=app.process_response(app.response_class('ok'))
                cookie=response.headers['Set-Cookie']
                self.assertIn('HttpOnly',cookie)
                self.assertIn('SameSite=Lax',cookie)
                self.assertEqual('Secure' in cookie,mode=='production')

    def test_rejects_invalid_or_unsafe_configuration(self):
        for env in ({},{'SECRET_KEY':'short','ERP_ENV':'production'}, {'SECRET_KEY':'x'*40,'ERP_ENV':'production','ERP_DEBUG':'true'}, {'SECRET_KEY':'x','ERP_ENV':'typo'}, {'SECRET_KEY':'x','ERP_SESSION_IDLE_SECONDS':'0'}, {'SECRET_KEY':'x','ERP_SESSION_ABSOLUTE_SECONDS':'invalid'}, {'SECRET_KEY':'x','ERP_DEBUG':'maybe'}):
            with self.subTest(env=env),self.assertRaises(RuntimeError):configure_security(Flask(__name__),env)

    def test_explicit_development_debug_and_lifetime_configuration(self):
        app=Flask(__name__)
        configure_security(app,{'SECRET_KEY':'local','ERP_DEBUG':'true','ERP_SESSION_IDLE_SECONDS':'60','ERP_SESSION_ABSOLUTE_SECONDS':'600'})
        self.assertTrue(app.debug)
        self.assertEqual(app.config['SESSION_IDLE_SECONDS'],60)
        self.assertEqual(app.config['SESSION_ABSOLUTE_SECONDS'],600)


if __name__=='__main__':unittest.main()
