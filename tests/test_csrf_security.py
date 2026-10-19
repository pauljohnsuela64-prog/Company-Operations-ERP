"""CSRF rejection, form coverage, expiry recovery and auth integration tests."""
import ast
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import time
import unittest
import uuid
from unittest.mock import patch

from flask import Flask, jsonify, render_template, request, session
from itsdangerous import URLSafeTimedSerializer
from werkzeug.datastructures import MultiDict
from csrf_security import init_csrf
from security_helpers import user_state, stamp_session

ROOT=Path(__file__).resolve().parents[1]


def form_token(response):
    matches=re.findall(r'name="csrf_token" value="([^"]+)"',response.get_data(as_text=True))
    assert matches, 'No rendered CSRF field'
    return matches[-1]


def expired_token(app,client):
    with client.session_transaction() as mapping:seed=mapping['csrf_token']
    with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())-3601):
        return URLSafeTimedSerializer(app.secret_key,salt='wtf-csrf-token').dumps(seed)


class CSRFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack=ExitStack()
        cls.addClassCleanup(cls.stack.close)
        cls.stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-csrf-tests',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.stack.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB access forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state=user_state(permissions=['procurement.suppliers.manage','procurement.view','inventory.view'])
        self.loader=self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.operation=self.stack.enter_context(patch.object(self.erp,'create_supplier'))
        self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.client=self.erp.app.test_client()  # Deliberately no automatic token fixture.
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        self.data={'supplier_code':'CSRF','supplier_name':'CSRF Test'}

    def token(self,client=None):return form_token((client or self.client).get('/logout'))

    def test_valid_field_and_both_header_names(self):
        token=self.token()
        for headers,data in (({},dict(self.data,csrf_token=token)),({'X-CSRFToken':token},self.data),({'X-CSRF-Token':token},self.data)):
            with self.subTest(headers=list(headers)):
                self.assertEqual(self.client.post('/procurement/suppliers/add',data=data,headers=headers).status_code,302)
        self.assertEqual(self.operation.call_count,3)

    def test_all_post_routes_reject_missing_and_invalid_tokens_without_writes(self):
        self.token()  # Also exercise invalid signatures with an existing session seed.
        count=0
        for rule in self.erp.app.url_map.iter_rules():
            if 'POST' not in rule.methods:continue
            path=re.sub(r'<int:[^>]+>','1',rule.rule)
            for token in (None,'invalid-token'):
                with self.subTest(endpoint=rule.endpoint,token=token):
                    data={} if token is None else {'csrf_token':token}
                    self.assertEqual(self.client.post(path,data=data).status_code,400)
            count+=1
        self.assertEqual(count,87)
        self.audit.assert_not_called()
        self.operation.assert_not_called()
        extension=self.erp.app.extensions['csrf']
        self.assertFalse(extension._exempt_views)
        self.assertFalse(extension._exempt_blueprints)

    def test_expired_token_from_another_session_has_no_recovery(self):
        self.token()
        old=expired_token(self.erp.app,self.client)
        other=self.erp.app.test_client()
        with other.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        self.token(other)
        html=other.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=old)).get_data(as_text=True)
        self.assertNotIn('Resubmit reviewed values',html)
        self.operation.assert_not_called()

    def test_session_mismatch_rejected(self):
        token=self.token()
        other=self.erp.app.test_client()
        with other.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        self.token(other)
        self.assertEqual(other.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=token)).status_code,400)
        self.operation.assert_not_called()

    def test_expired_form_has_explicit_recovery_with_original_values(self):
        self.token()
        old=expired_token(self.erp.app,self.client)
        response=self.client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=old))
        self.assertEqual(response.status_code,400)
        html=response.get_data(as_text=True)
        self.assertIn('Resubmit reviewed values',html)
        self.assertNotIn('onload=',html)
        self.assertNotIn('requestSubmit',html)
        self.operation.assert_not_called()
        self.audit.assert_not_called()
        renewed=form_token(response)
        self.assertEqual(self.client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=renewed)).status_code,302)
        self.operation.assert_called_once()

    def test_passwords_are_never_preserved_in_recovery(self):
        self.token()
        response=self.client.post('/admin/users/1/reset-password',data={'csrf_token':expired_token(self.erp.app,self.client),'password':'DO-NOT-ECHO','confirm_password':'DO-NOT-ECHO'})
        html=response.get_data(as_text=True)
        self.assertEqual(response.status_code,400)
        self.assertNotIn('DO-NOT-ECHO',html)
        self.assertNotIn('Resubmit reviewed values',html)
        self.audit.assert_not_called()

    def test_multiple_tabs_and_token_refresh_keep_both_tokens_valid(self):
        first=self.token()
        response=self.client.get('/auth/csrf-token')
        second=response.get_json()['csrf_token']
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=first)).status_code,302)
        self.assertEqual(self.client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=second)).status_code,302)
        self.assertEqual(self.operation.call_count,2)

    def test_login_rejects_missing_and_invalid_then_accepts_valid_token_and_rotates_seed(self):
        client=self.erp.app.test_client()
        lookup=self.stack.enter_context(patch.object(self.erp,'get_user_by_username',return_value=self.state))
        self.stack.enter_context(patch.object(self.erp,'check_password_hash',return_value=True))
        self.stack.enter_context(patch.object(self.erp,'update_last_login'))
        for data in ({'username':'test','password':'test'},{'username':'test','password':'test','csrf_token':'invalid'}):
            self.assertEqual(client.post('/login',data=data).status_code,400)
        lookup.assert_not_called()
        token=form_token(client.get('/login'))
        self.assertEqual(client.post('/login',data={'username':'test','password':'test','csrf_token':token}).status_code,302)
        self.assertEqual(client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=token)).status_code,400)
        fresh=self.token(client)
        self.assertEqual(client.post('/procurement/suppliers/add',data=dict(self.data,csrf_token=fresh)).status_code,302)

    def test_get_logout_is_harmless_for_valid_legacy_and_disabled_sessions(self):
        for legacy,disabled in ((False,False),(True,False),(False,True)):
            with self.subTest(legacy=legacy,disabled=disabled):
                with self.client.session_transaction() as mapping:
                    stamp_session(self.erp.app,mapping,self.state)
                    if legacy:mapping.pop('auth_version')
                    before={k:v for k,v in mapping.items() if k!='csrf_token'}
                self.state['is_active']=not disabled
                self.assertEqual(self.client.get('/logout').status_code,200)
                with self.client.session_transaction() as mapping:
                    self.assertEqual({k:v for k,v in mapping.items() if k!='csrf_token'},before)
        self.loader.assert_not_called()
        self.audit.assert_not_called()

    def test_post_logout_requires_csrf_even_during_authorization_outage(self):
        token=self.token()
        self.loader.side_effect=RuntimeError('isolated outage')
        self.assertEqual(self.client.post('/logout').status_code,400)
        with self.client.session_transaction() as mapping:self.assertIn('user_id',mapping)
        self.audit.assert_not_called()
        self.assertEqual(self.client.post('/logout',data={'csrf_token':token}).status_code,302)
        self.assertEqual(self.audit.call_args.kwargs['action'],'LOGOUT')
        with self.client.session_transaction() as mapping:self.assertNotIn('user_id',mapping)

    def test_json_errors_are_clear_and_do_not_echo_payload(self):
        response=self.client.post('/procurement/suppliers/add',json={'secret':'do-not-echo'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json['error'],'csrf_failed')
        self.assertNotIn('do-not-echo',response.get_data(as_text=True))
        self.operation.assert_not_called()

    def test_https_requires_matching_referrer_in_addition_to_token(self):
        token=self.token()
        self.assertEqual(self.client.post('/procurement/suppliers/add',base_url='https://localhost',headers={'X-CSRFToken':token,'Referer':'https://untrusted.example/'},data=self.data).status_code,400)
        self.assertEqual(self.client.post('/procurement/suppliers/add',base_url='https://localhost',headers={'X-CSRFToken':token,'Referer':'https://localhost/procurement/suppliers/add'},data=self.data).status_code,302)

    def test_all_original_forms_and_new_forms_include_the_shared_field(self):
        count=0
        for path in (ROOT/'templates').rglob('*.html'):
            source=path.read_text(encoding='utf-8')
            for form in re.findall(r'<form\b[\s\S]*?</form>',source,re.I):
                if re.search(r'method\s*=\s*[\"\x27]POST',form,re.I):
                    self.assertEqual(form.count("include 'partials/csrf_field.html'"),1,str(path))
                    count+=1
        self.assertEqual(count,89)  # Original 86 + navigation, logout confirmation, recovery.


class CSRFMethodAndReceivingCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__,template_folder=str(ROOT/'templates'))
        self.app.config.update(SECRET_KEY='isolated-method-test',TESTING=True)
        init_csrf(self.app)
        self.saved={}
        self.app.context_processor(lambda:{'has_permission':lambda _:False})
        self.app.add_url_rule('/login','login',lambda:'login')
        self.app.add_url_rule('/dashboard','dashboard',lambda:'dashboard')
        self.app.add_url_rule('/logout','logout',lambda:render_template('security/logout.html'))
        def receive():
            identifier=request.form.get('submission_id','generic')
            self.saved.setdefault(identifier,len(self.saved)+1)
            return jsonify(receipt_id=self.saved[identifier])
        self.app.add_url_rule('/receive','receive',receive,methods=['POST','PUT','PATCH','DELETE'])
        self.client=self.app.test_client()

    def test_all_unsafe_methods_are_protected_and_header_supported(self):
        token=self.client.get('/auth/csrf-token').json['csrf_token']
        for method in ('POST','PUT','PATCH','DELETE'):
            with self.subTest(method=method):
                self.assertEqual(self.client.open('/receive',method=method).status_code,400)
                self.assertEqual(self.client.open('/receive',method=method,headers={'X-CSRFToken':'invalid'}).status_code,400)
                self.assertEqual(self.client.open('/receive',method=method,headers={'X-CSRFToken':token}).status_code,200)

    def test_expiry_recovery_retains_submission_uuid_and_duplicate_values(self):
        token=self.client.get('/auth/csrf-token').json['csrf_token']
        identifier=str(uuid.uuid4())
        data=MultiDict([('csrf_token',token),('submission_id',identifier),('quantity_received_1','5'),('notes','<delivery>'),('line','a'),('line','b')])
        self.assertEqual(self.client.post('/receive',data=data).json['receipt_id'],1)
        data['csrf_token']=expired_token(self.app,self.client)
        response=self.client.post('/receive',data=data)
        self.assertEqual(response.status_code,400)
        self.assertEqual(len(self.saved),1)
        html=response.get_data(as_text=True)
        self.assertIn(f'name="submission_id" value="{identifier}"',html)
        self.assertIn('name="quantity_received_1" value="5"',html)
        self.assertIn('value="&lt;delivery&gt;"',html)
        self.assertIn('name="line" value="a"',html)
        self.assertIn('name="line" value="b"',html)
        data['csrf_token']=form_token(response)
        self.assertEqual(self.client.post('/receive',data=data).json['receipt_id'],1)
        self.assertEqual(len(self.saved),1)


if __name__=='__main__':unittest.main()
