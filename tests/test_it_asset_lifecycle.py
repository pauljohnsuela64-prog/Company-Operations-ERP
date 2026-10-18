"""Return requests bind to a specific custody record and fail without success."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch

from security_helpers import stamp_session, user_state, csrf_token_for


class AssetLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-asset-lifecycle', ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')
        cls.repo = importlib.import_module('it_asset_repository')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.state = user_state(permissions=['it_assets.view', 'it_assets.manage'])
        self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda _: self.state))
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.audit = self.stack.enter_context(patch.object(self.erp, 'create_audit_log'))
        self.stack.enter_context(patch.object(self.erp, 'get_it_asset_by_id', return_value=dict(asset_id=42, asset_tag='IT-42')))
        self.client = self.erp.app.test_client()
        with self.client.session_transaction() as sess:
            stamp_session(self.erp.app, sess, self.state)

    def test_return_forwards_the_rendered_assignment_identity(self):
        with patch.object(self.erp, 'unassign_it_asset', return_value=True) as write:
            response = self.client.post('/it/assets/42/unassign', data=dict(assignment_id='17', csrf_token=csrf_token_for(self.client)))
        self.assertTrue(response.location.endswith('/it/assets/42'))
        write.assert_called_once_with(asset_id=42, returned_by=7, assignment_id='17')
        with self.client.session_transaction() as sess:
            self.assertIn(('success', 'IT asset unassigned successfully.'), sess['_flashes'])

    def test_rejected_transition_never_flashes_success_or_audits(self):
        for message in ['Assignment changed. Reload the asset before returning it.', 'Assignment history is missing or inconsistent.']:
            with self.client.session_transaction() as sess:
                sess.pop('_flashes', None)
            with patch.object(self.erp, 'unassign_it_asset', side_effect=ValueError(message)):
                self.client.post('/it/assets/42/unassign', data=dict(assignment_id='17', csrf_token=csrf_token_for(self.client)))
            with self.client.session_transaction() as sess:
                self.assertEqual(sess['_flashes'], [('danger', message)])
        self.audit.assert_not_called()

    def test_assignment_token_required_before_any_database_operation(self):
        with patch.object(self.repo, 'get_connection', side_effect=AssertionError('No database access for malformed token')):
            for value in [None, '', '0', '-1', 'NaN', '1.0', '2147483648', '1'*5000]:
                with self.subTest(value=str(value)[:30]), self.assertRaisesRegex(ValueError, 'Reload the asset'):
                    self.repo.unassign_it_asset(42, 7, value)

    def test_csrf_and_fresh_authorization_precede_return(self):
        with patch.object(self.erp, 'unassign_it_asset') as write:
            self.assertEqual(self.client.post('/it/assets/42/unassign', data={'assignment_id':'17'}).status_code, 400)
            self.state['permissions'] = frozenset(['it_assets.view'])
            response = self.client.post('/it/assets/42/unassign', data=dict(assignment_id='17', csrf_token=csrf_token_for(self.client)))
            self.assertTrue(response.location.endswith('/dashboard'))
            self.state['is_active'] = False
            response = self.client.post('/it/assets/42/unassign', data=dict(assignment_id='17', csrf_token=csrf_token_for(self.client)))
            self.assertTrue(response.location.endswith('/login'))
            write.assert_not_called()
        self.audit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
