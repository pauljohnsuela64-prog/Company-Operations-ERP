"""Dashboard reads and route boundaries; configured database access is forbidden."""
from contextlib import ExitStack
from datetime import date
import importlib
import unittest
from unittest.mock import MagicMock, patch
import mysql.connector
from security_helpers import csrf_client, stamp_session, user_state


class DashboardReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-dashboard-unit', ERP_ENV='testing', ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')
        cls.repo = importlib.import_module('dashboard_repository')

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('database.ensure_ready'))
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.state = user_state(permissions=['attendance.view', 'leave.view'])
        self.auth = self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda _: self.state))
        self.client = csrf_client(self.erp.app)
        with self.client.session_transaction() as session:
            stamp_session(self.erp.app, session, self.state)

    def test_permission_matrix_calls_only_authorized_readers(self):
        with patch.object(self.repo, '_read_section', return_value={'synthetic': 1}) as read:
            for section, (permission, *_) in self.repo.SECTIONS.items():
                read.reset_mock()
                result = self.repo.get_dashboard_summary({permission})
                self.assertEqual(set(result), {'today', *self.repo.SECTIONS})
                self.assertEqual([call.args[0] for call in read.call_args_list], [section])
                self.assertTrue(all(result[key] is None for key in self.repo.SECTIONS if key != section))
            read.reset_mock()
            result = self.repo.get_dashboard_summary(set())
            read.assert_not_called()
            self.assertTrue(all(result[key] is None for key in self.repo.SECTIONS))

    def test_isolation_and_fundamental_failure_distinction(self):
        def reader(section, today):
            if section == 'payroll': raise self.repo.SectionUnavailable()
            return {'total': 2}
        with patch.object(self.repo, '_read_section', side_effect=reader):
            summary = self.repo.get_dashboard_summary({'employees.view', 'payroll.view'})
            self.assertEqual(summary['employees'], {'total': 2})
            self.assertIsNone(summary['payroll'])
        with patch.object(self.repo, '_read_section', side_effect=self.repo.SchemaUnavailable()):
            with self.assertRaises(self.repo.SchemaUnavailable):
                self.repo.get_dashboard_summary({'employees.view'})

    def test_bounded_readonly_snapshot_and_date_parameter(self):
        db = MagicMock(); cursor = db.cursor.return_value
        cursor.fetchone.return_value = {'total': 0, 'present': 0}
        with patch.object(self.repo, 'get_connection', return_value=db):
            self.assertEqual(self.repo._read_section('attendance', date(2026, 10, 22)), {'total': 0, 'present': 0})
        db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ', consistent_snapshot=True, readonly=True)
        self.assertEqual(cursor.execute.call_args.args[1][-1], date(2026, 10, 22))
        cursor.fetchall.assert_not_called(); db.commit.assert_not_called()
        db.rollback.assert_called_once(); db.close.assert_called_once(); cursor.close.assert_called_once()

    def test_only_missing_module_schema_errors_become_unavailable(self):
        for errno in (1054, 1146, 1142, 2006, 2013, 1064):
            with self.subTest(errno=errno):
                db = MagicMock(); cursor = db.cursor.return_value
                cursor.execute.side_effect = mysql.connector.Error('PRIVATE SQL diagnostic', errno=errno)
                with patch.object(self.repo, 'get_connection', return_value=db), self.assertLogs(self.repo.logger, 'WARNING'):
                    expected = self.repo.SectionUnavailable if errno in (1054, 1146) else self.repo.SchemaUnavailable
                    with self.assertRaises(expected): self.repo._read_section('payroll', date.today())
                db.rollback.assert_called_once(); db.close.assert_called_once()
        db = MagicMock(); db.cursor.return_value.fetchone.return_value = {'total': 0}
        db.close.side_effect = mysql.connector.Error('Synthetic cleanup failure', errno=2013)
        with patch.object(self.repo, 'get_connection', return_value=db), self.assertRaises(self.repo.SchemaUnavailable):
            self.repo._read_section('employees', date.today())

    def test_hr_links_and_cards_without_administration_permissions(self):
        values = {'attendance': dict(total=3, present=1, late=1, absent=0, on_leave=1, half_day=0),
                  'leave': dict(pending=2, approved=1)}
        with patch.object(self.repo, '_read_section', side_effect=lambda section, today: values[section]) as read:
            response = self.client.get('/dashboard')
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('href="/attendance"', html); self.assertIn('href="/leave/requests"', html)
            self.assertNotIn('href="/admin/users"', html)
            self.assertEqual({call.args[0] for call in read.call_args_list}, {'attendance', 'leave'})
            self.state['permissions'] = frozenset({'attendance.view'})
            html = self.client.get('/dashboard').get_data(as_text=True)
            self.assertNotIn('href="/leave/requests"', html)

    def test_unavailable_card_and_authorization_failures_are_not_zero_counts(self):
        self.state['permissions'] = frozenset({'payroll.view'})
        with patch.object(self.repo, '_read_section', side_effect=self.repo.SectionUnavailable()):
            response = self.client.get('/dashboard'); html = response.get_data(as_text=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Currently unavailable.', html)
            self.assertNotIn('No paid payroll period yet.', html)
            self.assertNotIn('PRIVATE', html)
        with patch.object(self.repo, '_read_section', side_effect=self.repo.SchemaUnavailable()):
            self.assertEqual(self.client.get('/dashboard').status_code, 503)
        with patch.object(self.repo, '_read_section') as read:
            self.auth.side_effect = RuntimeError('Synthetic authorization outage')
            with patch.object(self.erp.app.logger, 'exception'):
                self.assertEqual(self.client.get('/dashboard').status_code, 503)
            read.assert_not_called()

    def test_anonymous_and_global_schema_failures_do_not_reach_dashboard(self):
        with patch.object(self.erp, 'get_dashboard_summary') as read:
            self.assertTrue(self.erp.app.test_client().get('/dashboard').location.endswith('/login'))
            with patch('database.ensure_ready', side_effect=self.repo.SchemaUnavailable()):
                self.assertEqual(self.client.get('/dashboard').status_code, 503)
            read.assert_not_called()


if __name__ == '__main__': unittest.main()
