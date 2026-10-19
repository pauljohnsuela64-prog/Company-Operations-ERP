"""Route authorization contract; company database access is forbidden."""
import ast
from datetime import date
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import unittest
from unittest.mock import patch
from security_helpers import stamp_session, user_state, csrf_token_for

ROOT = Path(__file__).resolve().parents[1]


def route_contract():
    result = []
    for node in ast.parse((ROOT / 'app.py').read_text()).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call) or ast.unparse(dec.func) != 'app.route':
                continue
            path = ast.literal_eval(dec.args[0])
            if not path.startswith(('/it/assets', '/it/help-desk')):
                continue
            methods = next((ast.literal_eval(k.value) for k in dec.keywords if k.arg == 'methods'), ['GET'])
            prefix = 'helpdesk' if path.startswith('/it/help-desk') else 'it_assets'
            expected = prefix + ('.manage' if 'POST' in methods else '.view')
            permission = next(ast.literal_eval(d.args[0]) for d in node.decorator_list
                              if isinstance(d, ast.Call) and ast.unparse(d.func) == 'permission_required')
            result.append((re.sub(r'<int:[^>]+>', '1', path), methods, expected, permission))
    return result


class ITAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-it-authorization-tests', ERP_ENV='testing', ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state = user_state(permissions=['it_assets.view', 'helpdesk.view'])
        self.loader = self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda uid: self.state))
        self.client = self.erp.app.test_client()
        with self.client.session_transaction() as mapping:
            stamp_session(self.erp.app, mapping, self.state)
        self.audit = self.stack.enter_context(patch.object(self.erp, 'create_audit_log'))

    def test_all_26_routes_use_expected_permissions(self):
        rows = route_contract()
        self.assertEqual(len(rows), 26)
        self.assertEqual(sum('POST' in r[1] for r in rows), 17)
        for path, methods, expected, actual in rows:
            with self.subTest(path=path):
                self.assertEqual(actual, expected)

    def test_view_only_forged_posts_and_management_forms_denied_before_business_access(self):
        token = csrf_token_for(self.client)
        for path, methods, expected, _ in route_contract():
            if expected.endswith('.manage'):
                for method in methods:
                    with self.subTest(path=path, method=method):
                        response = self.client.open(path, method=method, data={'csrf_token': token})
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(response.location.endswith('/dashboard'))
        self.audit.assert_not_called()

    def test_module_permissions_do_not_cross_authorize(self):
        token = csrf_token_for(self.client)
        for permission, path in [('it_assets.manage', '/it/help-desk/1/start'), ('helpdesk.manage', '/it/assets/1/retire')]:
            self.state['permissions'] = frozenset([permission])
            self.assertTrue(self.client.post(path, data={'csrf_token': token}).location.endswith('/dashboard'))

    def test_revoked_permissions_and_disabled_accounts_rechecked_on_same_session(self):
        self.state['permissions'] = frozenset(['it_assets.manage', 'helpdesk.manage'])
        token = csrf_token_for(self.client)
        self.state['permissions'] = frozenset()
        for path in ['/it/assets/1/retire', '/it/help-desk/1/start']:
            self.assertTrue(self.client.post(path, data={'csrf_token': token}).location.endswith('/dashboard'))
        self.state['is_active'] = False
        self.assertTrue(self.client.get('/it/assets').location.endswith('/login'))
        self.audit.assert_not_called()

    def test_csrf_rejects_all_mutation_routes_even_for_managers(self):
        self.state['permissions'] = frozenset(['it_assets.manage', 'helpdesk.manage'])
        for path, methods, _, _ in route_contract():
            if 'POST' in methods:
                for token in [None, 'forged']:
                    with self.subTest(path=path, token=token):
                        data = {} if token is None else {'csrf_token': token}
                        self.assertEqual(self.client.post(path, data=data).status_code, 400)
        self.audit.assert_not_called()

    def test_dashboard_cards_and_navigation_use_independent_view_permissions(self):
        summary = dict(today=date(2026, 10, 18),
                       it_assets=dict(total=1, available=1, assigned=0, maintenance=0),
                       helpdesk=dict(open=1, total=1, urgent_open=0, resolved=0))
        with patch.object(self.erp, 'get_dashboard_summary', return_value=summary):
            for permission, visible, hidden in [
                    ('it_assets.view', '/it/assets', '/it/help-desk'),
                    ('helpdesk.view', '/it/help-desk', '/it/assets')]:
                self.state['permissions'] = frozenset([permission])
                html = self.client.get('/dashboard').get_data(as_text=True)
                self.assertIn(f'href="{visible}"', html)
                self.assertNotIn(f'href="{hidden}"', html)
                self.assertIn('id="erp-navigation"', html)

    def test_anonymous_access_requires_login(self):
        client = self.erp.app.test_client()
        token = csrf_token_for(client)
        for path, methods, _, _ in route_contract():
            for method in methods:
                with self.subTest(path=path, method=method):
                    response = client.open(path, method=method, data={'csrf_token': token})
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.location.endswith('/login'))
