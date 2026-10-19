"""Additional read-only final-review checks; no application database access."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch

from flask import Flask
from security import configure_security
from security_helpers import stamp_session, user_state


class FinalSecurityReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack=ExitStack()
        cls.addClassCleanup(cls.stack.close)
        cls.stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-final-review-key',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.stack.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB access forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack()
        self.addCleanup(self.stack.close)
        self.state=user_state(permissions=['procurement.suppliers.manage','procurement.view'])
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.loader=self.stack.enter_context(patch.object(self.erp,'get_authorization_state',return_value=self.state))
        self.client=self.erp.app.test_client()
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.write=self.stack.enter_context(patch.object(self.erp,'create_supplier'))

    def test_token_renewal_has_no_business_side_effects_or_external_redirect(self):
        response=self.client.get('/auth/csrf-token?next=https://untrusted.example')
        self.assertEqual(response.status_code,200)
        self.assertEqual(set(response.json),{'csrf_token'})
        self.assertNotIn('Location',response.headers)
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.audit.assert_not_called()
        self.write.assert_not_called()
        self.assertEqual(self.client.post('/auth/csrf-token',data={'csrf_token':response.json['csrf_token']}).status_code,405)

    def test_renewal_does_not_grant_revoked_permissions_or_bypass_csrf(self):
        token=self.client.get('/auth/csrf-token').json['csrf_token']
        self.state['permissions']=frozenset()
        self.assertEqual(self.client.post('/procurement/suppliers/add',data={'supplier_code':'NO','supplier_name':'Denied'}).status_code,400)
        response=self.client.post('/procurement/suppliers/add',data={'csrf_token':token,'supplier_code':'NO','supplier_name':'Denied'})
        self.assertTrue(response.location.endswith('/dashboard'))
        self.audit.assert_not_called()
        self.write.assert_not_called()

    def test_expired_session_cannot_be_renewed_into_authentication(self):
        token=self.client.get('/auth/csrf-token').json['csrf_token']
        with self.client.session_transaction() as mapping:mapping['auth_seen']-=1801
        response=self.client.get('/auth/csrf-token',headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,401)
        self.assertNotIn('csrf_token',response.json)
        self.assertEqual(self.client.post('/procurement/suppliers/add',data={'csrf_token':token,'supplier_code':'NO','supplier_name':'Denied'}).status_code,400)
        self.audit.assert_not_called()
        self.write.assert_not_called()

    def test_production_missing_or_unsafe_critical_settings_fail_before_startup(self):
        for overrides in ({'SECRET_KEY':None},{'SECRET_KEY':'short'},{'SECRET_KEY':'YOUR_SECRET_KEY_HERE'*3}, {'ERP_DEBUG':'true'}, {'ERP_SESSION_IDLE_SECONDS':'0'}, {'ERP_SESSION_ABSOLUTE_SECONDS':'not-an-integer'}):
            env=dict(ERP_ENV='production',SECRET_KEY='valid-length-test-secret-with-40-characters')
            env.update(overrides)
            if env.get('SECRET_KEY') is None:env.pop('SECRET_KEY')
            with self.subTest(overrides=overrides),self.assertRaises(RuntimeError):
                configure_security(Flask(__name__),env)


if __name__=='__main__':unittest.main()
