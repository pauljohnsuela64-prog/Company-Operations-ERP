"""Administration contract checks with all real database connections blocked."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import MagicMock, patch
from werkzeug.datastructures import MultiDict
from security_helpers import csrf_client, stamp_session, user_state


class AdminIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-admin-tests', ERP_ENV='testing', ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')
        cls.repo = importlib.import_module('user_repository')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('database.ensure_ready'))
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.state = user_state(user_id=7, permissions=['users.manage'])
        self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda _: self.state))
        self.audit = self.stack.enter_context(patch.object(self.erp, 'create_audit_log'))
        self.client = csrf_client(self.erp.app)
        with self.client.session_transaction() as session:
            stamp_session(self.erp.app, session, self.state)

    def test_invalid_and_self_repository_calls_never_connect(self):
        calls = [lambda value=value: self.repo.update_user_role(42, value, actor_user_id=7)
                 for value in (None, '', True, 0, -1, '1.0', 2147483648)]
        calls += [lambda: self.repo.update_user_role(7, 1, actor_user_id=7),
                  lambda: self.repo.set_user_active_status(7, False, actor_user_id=7),
                  lambda: self.repo.set_user_active_status(42, '0', actor_user_id=7),
                  lambda: self.repo.set_user_active_status(42, False, actor_user_id=0)]
        with patch.object(self.repo, 'get_connection') as connection:
            for action in calls:
                with self.assertRaises(self.repo.AdminIntegrityError):
                    action()
            connection.assert_not_called()

    def test_role_update_and_explicit_status_audit_only_changed_commits(self):
        for path, field, value, operation, action in (
            ('role', 'role_id', '3', 'update_user_role', 'UPDATE'),
            ('status', 'is_active', '0', 'set_user_active_status', 'DEACTIVATE'),
            ('status', 'is_active', '1', 'set_user_active_status', 'ACTIVATE')):
            with self.subTest(action=action), patch.object(self.erp, operation) as write:
                write.return_value = self.repo.AdminAccessResult(42, 'target.user', True)
                self.audit.reset_mock()
                self.assertEqual(self.client.post(f'/admin/users/42/{path}', data={field: value}).status_code, 302)
                self.assertEqual(write.call_args.kwargs, {'actor_user_id': 7})
                self.assertEqual(self.audit.call_args.kwargs['action'], action)
                self.assertEqual(self.audit.call_args.kwargs['entity_id'], 'target.user')
                self.audit.reset_mock()
                write.return_value = self.repo.AdminAccessResult(42, 'target.user', False)
                self.assertEqual(self.client.post(f'/admin/users/42/{path}', data={field: value}).status_code, 302)
                self.audit.assert_not_called()
                for status in (400, 404, 409, 503):
                    write.side_effect = self.repo.AdminIntegrityError('Review account', status)
                    self.assertEqual(self.client.post(f'/admin/users/42/{path}', data={field: value}).status_code, status)
                    self.audit.assert_not_called()

    def test_missing_invalid_duplicate_targets_and_self_are_rejected(self):
        with patch.object(self.erp, 'set_user_active_status') as write:
            for data in ({}, {'is_active': 'bad'}, MultiDict([('is_active', '0'), ('is_active', '1')])):
                self.assertEqual(self.client.post('/admin/users/42/status', data=data).status_code, 400)
            self.assertEqual(self.client.post('/admin/users/7/status', data={'is_active': '0'}).status_code, 302)
            write.assert_not_called()
        self.audit.assert_not_called()

    def test_missing_integrity_guard_or_canonical_role_fails_closed(self):
        for rows in ([None], [{'permission_id': 1}, None]):
            connection = MagicMock()
            cursor = connection.cursor.return_value
            cursor.fetchone.side_effect = rows
            with patch.object(self.repo, 'get_connection', return_value=connection):
                with self.assertRaises(self.repo.AdminIntegrityError) as raised:
                    self.repo.update_user_role(42, 3, actor_user_id=7)
            self.assertEqual(raised.exception.status_code, 503)
            connection.commit.assert_not_called()
            connection.rollback.assert_called_once()
            self.assertFalse(any('UPDATE users' in call.args[0] for call in cursor.execute.call_args_list))

    def test_security_and_csrf_remain_authoritative(self):
        with patch.object(self.erp, 'update_user_role') as write:
            raw = self.erp.app.test_client()
            with raw.session_transaction() as session:
                stamp_session(self.erp.app, session, self.state)
            self.assertEqual(raw.post('/admin/users/42/role', data={'role_id': '3'}).status_code, 400)
            self.state['permissions'] = frozenset()
            self.assertTrue(self.client.post('/admin/users/42/role', data={'role_id': '3'}).location.endswith('/dashboard'))
            write.assert_not_called()
        self.audit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
