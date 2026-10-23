"""Schedule concurrency guard and safe HTTP conflicts; no company connections."""
from contextlib import ExitStack
from datetime import date
import importlib
import unittest
from unittest.mock import MagicMock, patch

from mysql.connector import Error
import payroll_period_repository as repo
from security_helpers import csrf_client, stamp_session, user_state


class PayrollScheduleRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.db = MagicMock(); self.cur = self.db.cursor.return_value
        self.cur.lastrowid = 7
        self.connect = self.stack.enter_context(patch.object(repo, 'get_connection', return_value=self.db))
        self.start, self.end = date(2026, 1, 1), date(2026, 1, 15)

    def write(self, editing=False):
        args = ('Test', self.start, self.end, date(2026, 1, 16), None, 1)
        return repo.update_payroll_period(7, *args) if editing else repo.create_payroll_period(*args)

    def test_missing_storage_or_gate_and_overlap_fail_before_writes(self):
        for rows, status in (([None], 503), ([('MyISAM',)], 503), ([('InnoDB',), None], 503),
                             ([('InnoDB',), (1,), (42,)], 409)):
            for editing in (False, True):
                self.cur.fetchone.side_effect = rows
                with self.subTest(rows=rows, editing=editing), self.assertRaises(repo.PayrollScheduleError) as error:
                    self.write(editing)
                self.assertEqual(error.exception.status_code, status)
        self.db.commit.assert_not_called()
        for call in self.cur.execute.call_args_list:
            self.assertTrue(call.args[0].startswith('SELECT'))

    def test_gate_precedes_current_read_and_bound_overlap_parameters(self):
        self.cur.fetchone.side_effect = [('InnoDB',), (1,), None]
        self.write(True)
        sql = [call.args[0] for call in self.cur.execute.call_args_list]
        self.assertIn('payroll.process', sql[1]); self.assertIn('FOR UPDATE', sql[1])
        self.assertIn("status<>'CANCELLED'", sql[2]); self.assertIn('FOR UPDATE', sql[2])
        self.assertEqual(self.cur.execute.call_args_list[2].args[1], (self.end, self.start, 7, 7))
        self.assertIn("AND status = 'DRAFT'", sql[3])
        self.db.start_transaction.assert_called_once(); self.db.commit.assert_called_once()

    def test_commit_and_lock_errors_never_retry_and_always_close(self):
        for editing in (False, True):
            for errno in (1205, 1213, 2013):
                self.db.reset_mock(); self.connect.reset_mock()
                self.cur.fetchone.side_effect = [('InnoDB',), (1,), None]
                self.db.commit.side_effect = Error('PRIVATE commit outcome', errno=errno)
                with self.subTest(editing=editing, errno=errno), self.assertRaises(Error): self.write(editing)
                self.connect.assert_called_once(); self.db.commit.assert_called_once()
                self.db.rollback.assert_called_once(); self.db.close.assert_called_once()


class PayrollScheduleRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack(); cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='synthetic-payroll-schedule', ERP_ENV='testing', ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')

    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state = user_state(permissions=['payroll.process', 'payroll.view'])
        self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda _: self.state))
        self.period = dict(payroll_period_id=7, period_number='PP-7', period_name='Old', status='DRAFT',
                           start_date=date(2026, 1, 1), end_date=date(2026, 1, 15), pay_date=date(2026, 1, 16), notes=None)
        self.stack.enter_context(patch.object(self.erp, 'get_payroll_period_by_id', return_value=self.period))
        self.stack.enter_context(patch.object(self.erp, 'has_overlapping_payroll_period', return_value=None))
        self.audit = self.stack.enter_context(patch.object(self.erp, 'create_audit_log'))
        self.client = csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping: stamp_session(self.erp.app, mapping, self.state)
        self.form = dict(period_name='Submitted <name>', start_date='2026-02-01', end_date='2026-02-15', pay_date='2026-02-16', notes='Retained notes')

    def test_late_schedule_conflict_and_unavailable_state_render_safe_feedback(self):
        for path, operation in (('add', 'create_payroll_period'), ('7/edit', 'update_payroll_period')):
            for status in (409, 503):
                with patch.object(self.erp, operation, side_effect=repo.PayrollScheduleError('Reload and review.', status)):
                    response = self.client.post('/payroll/periods/' + path, data=self.form)
                self.assertEqual(response.status_code, status)
                html = response.get_data(as_text=True)
                self.assertIn('Reload and review.', html)
                self.assertIn('Submitted &lt;name&gt;', html)
                self.assertIn('2026-02-01', html)
                self.assertIn('Retained notes', html)
        self.audit.assert_not_called()

    def test_read_only_and_invalid_csrf_cannot_call_schedule_writer(self):
        for path, operation in (('add', 'create_payroll_period'), ('7/edit', 'update_payroll_period')):
            with patch.object(self.erp, operation) as write:
                self.assertEqual(self.client.post('/payroll/periods/' + path, data=self.form, headers={'X-CSRFToken': 'invalid'}).status_code, 400)
                self.state['permissions'] = frozenset(['payroll.view'])
                self.assertEqual(self.client.post('/payroll/periods/' + path, data=self.form).status_code, 302)
                write.assert_not_called()
                self.state['permissions'] = frozenset(['payroll.process', 'payroll.view'])
