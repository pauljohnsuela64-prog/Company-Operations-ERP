"""Schema boundaries and HR route behavior without company database access."""
from contextlib import ExitStack
from datetime import date, datetime
from html import escape
import importlib
import unittest
from unittest.mock import patch

from werkzeug.datastructures import MultiDict
from hr_validation import (HRValidationError, EMPLOYEE_FIELDS, EMPLOYMENT_STATUSES,
                           employee_values, department_values, identifier, form_values)
from hr_revision import HRWriteResult, HRMissingRecordError
from security_helpers import csrf_client, stamp_session, user_state


EMPLOYEE = dict(employee_number='EMP-001', department_id='1', first_name='First',
                middle_name='', last_name='Last', email='employee@example.invalid',
                phone='', job_title='', hire_date='2026-01-01')
DEPARTMENT = dict(department_code='DEPT', department_name='Department', description='Long <notes> & details')
LIMITS = dict(employee_number=30, first_name=100, middle_name=100, last_name=100,
              email=150, phone=30, job_title=100)


class HRValidationTests(unittest.TestCase):
    def test_every_employee_text_boundary_and_required_field(self):
        for key, limit in LIMITS.items():
            exact = 'a' * limit if key != 'email' else 'a' * 138 + '@example.org'
            self.assertEqual(len(exact), limit)
            self.assertEqual(len(employee_values(dict(EMPLOYEE, **{key: exact}))[key]), limit)
            with self.subTest(field=key), self.assertRaises(HRValidationError):
                employee_values(dict(EMPLOYEE, **{key: 'a' * (limit + 1)}))
        for key in ('employee_number', 'first_name', 'last_name'):
            with self.subTest(required=key), self.assertRaises(HRValidationError):
                employee_values(dict(EMPLOYEE, **{key: ' '}))

    def test_optional_fields_normalization_and_statuses(self):
        values = employee_values(dict(EMPLOYEE, employee_number=' emp-001 ',
            department_id='', email='', hire_date=''))
        self.assertEqual(values['employee_number'], 'EMP-001')
        for key in ('department_id', 'email', 'hire_date', 'middle_name', 'phone', 'job_title'):
            self.assertIsNone(values[key])
        for status in EMPLOYMENT_STATUSES:
            self.assertEqual(employee_values(dict(EMPLOYEE, employment_status=status), True)['employment_status'], status)
        for status in ('', 'UNKNOWN', 'X'*31):
            with self.assertRaises(HRValidationError):
                employee_values(dict(EMPLOYEE, employment_status=status), True)
        for raw in (dict(EMPLOYEE, employee_number='ß'*16), dict(EMPLOYEE, email='not-an-email')):
            with self.assertRaises(HRValidationError):
                employee_values(raw)

    def test_dates_and_identifiers(self):
        for raw in ('2024-02-29', date(1000, 1, 1), '9999-12-31'):
            self.assertIsInstance(employee_values(dict(EMPLOYEE, hire_date=raw))['hire_date'], date)
        for raw in ('2025-02-29', '2026-13-01', '0000-00-00', '0999-12-31', '20260101',
                    '2026-01-01T12:00:00', datetime(2026, 1, 1), 'invalid'):
            with self.subTest(date=raw), self.assertRaises(HRValidationError):
                employee_values(dict(EMPLOYEE, hire_date=raw))
        for raw in ('abc', '-1', '0', '1.5', '1e2', '2147483648', True, [], '9'*100):
            with self.subTest(identifier=raw), self.assertRaises(HRValidationError):
                identifier(raw, 'Department')
        self.assertEqual(identifier(' 01 ', 'Department'), 1)

    def test_department_boundaries_and_duplicate_form_fields(self):
        for field, limit in [('department_code',20), ('department_name',100), ('description',255)]:
            self.assertEqual(len(department_values(dict(DEPARTMENT, **{field: 'X'*limit}))[field]), limit)
            with self.assertRaises(HRValidationError):
                department_values(dict(DEPARTMENT, **{field: 'X'*(limit+1)}))
        for field in ('department_code', 'department_name'):
            with self.assertRaises(HRValidationError):
                department_values(dict(DEPARTMENT, **{field:''}))
        self.assertIsNone(department_values(dict(DEPARTMENT, description=''))['description'])
        with self.assertRaises(HRValidationError):
            department_values(dict(DEPARTMENT, department_code='ß'*11))
        with self.assertRaises(HRValidationError):
            form_values(MultiDict([('department_id','1'), ('department_id','2')]), EMPLOYEE_FIELDS)


class HRRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ExitStack()
        cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv', return_value=False))
        cls.guard.enter_context(patch.dict('os.environ', SECRET_KEY='synthetic-hr-routes', ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        cls.erp = importlib.import_module('app')

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config, TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state = user_state(permissions=['employees.view','employees.create','employees.edit',
            'departments.view','departments.manage'])
        self.stack.enter_context(patch.object(self.erp, 'get_authorization_state', side_effect=lambda uid:self.state))
        self.client = csrf_client(self.erp.app)
        with self.client.session_transaction() as session: stamp_session(self.erp.app, session, self.state)
        self.employee = dict(employee_values(EMPLOYEE), employee_id=1, employment_status='Active', revision=1)
        self.department = dict(DEPARTMENT, department_id=1, is_active=True, revision=1)
        for name, value in [('get_employee_by_id',self.employee),('get_department_by_id',self.department),
                            ('get_active_departments',[self.department]),('get_all_departments',[self.department]),
                            ('get_all_employees',[]),('create_employee',1),('update_employee',HRWriteResult(2)),
                            ('create_department',1),('update_department',HRWriteResult(2)),('set_department_active_status',HRWriteResult(2))]:
            setattr(self,name,self.stack.enter_context(patch.object(self.erp,name,return_value=value)))

    def test_employee_errors_retain_submitted_values_and_selection(self):
        for path in ['/employees/add','/employees/1/edit']:
            fields=dict(EMPLOYEE, first_name='X'*101, phone='Retained phone', employment_status='Active', expected_revision='1')
            response=self.client.post(path,data=fields)
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn('First name must not exceed 100 characters.',html)
            self.assertIn('value="Retained phone"',html)
            self.assertRegex(html, r'value="1"\s+selected')
        self.create_employee.assert_not_called(); self.update_employee.assert_not_called()

    def test_duplicate_and_reference_errors_retain_forms_without_success(self):
        for path, name in [('/employees/add','create_employee'),('/employees/1/edit','update_employee')]:
            getattr(self,name).side_effect=HRValidationError('Employee number or email already exists.')
            fields=dict(EMPLOYEE, department_id='999', first_name='Retained first', employment_status='Active', expected_revision='1')
            response=self.client.post(path,data=fields)
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn('value="Retained first"',html)
            self.assertIn('value="999" selected',html)
            self.assertIn('Unavailable department',html)
            self.assertNotIn('Employee updated successfully.',html)

    def test_department_errors_retain_long_description_and_no_write(self):
        for path in ['/departments/add','/departments/1/edit']:
            fields=dict(DEPARTMENT,expected_revision='1',department_code='X'*21,description='Retained <description> & notes')
            response=self.client.post(path,data=fields)
            self.assertEqual(response.status_code,200)
            self.assertIn(escape(fields['description']),response.get_data(as_text=True))
        self.create_department.assert_not_called();self.update_department.assert_not_called()

    def test_missing_targets_and_concurrent_disappearance_do_not_flash_success(self):
        for path,lookup in [('/employees/1/edit',self.get_employee_by_id),('/departments/1/edit',self.get_department_by_id)]:
            lookup.return_value=None
            self.assertEqual(self.client.post(path,data=EMPLOYEE).status_code,404)
        self.get_employee_by_id.return_value=self.employee
        self.update_employee.side_effect=HRMissingRecordError('Employee no longer exists.')
        response=self.client.post('/employees/1/edit',data=dict(EMPLOYEE,employment_status='Active', expected_revision='1'))
        self.assertEqual(response.status_code,404)
        self.assertIn('Employee no longer exists',response.get_data(as_text=True))

    def test_desired_state_is_explicit_and_repeatable(self):
        for desired in ('0','0','1','1'):
            self.assertEqual(self.client.post('/departments/1/status',data={'is_active':desired,'expected_revision':'1'}).status_code,302)
            self.set_department_active_status.assert_called_with(1,desired=='1',expected_revision=1)
        self.set_department_active_status.reset_mock()
        for fields in ({},{'is_active':'true'}, MultiDict([('is_active','0'),('is_active','1')])):
            self.assertEqual(self.client.post('/departments/1/status',data=MultiDict([*fields.items(multi=True),('expected_revision','1')]) if isinstance(fields,MultiDict) else dict(fields,expected_revision='1')).status_code,302)
        self.set_department_active_status.assert_not_called()

    def test_permissions_revocation_csrf_and_disabled_accounts(self):
        paths=['/employees/add','/employees/1/edit','/departments/add','/departments/1/edit','/departments/1/status']
        self.state['permissions']=frozenset(['employees.view','departments.view'])
        for path in paths:
            self.assertTrue(self.client.post(path,data=EMPLOYEE).location.endswith('/dashboard'))
        self.state['permissions']=frozenset()
        self.assertTrue(self.client.get('/employees').location.endswith('/dashboard'))
        self.state['is_active']=False
        self.assertTrue(self.client.get('/employees').location.endswith('/login'))
        raw=self.erp.app.test_client()
        for path in paths: self.assertEqual(raw.post(path).status_code,400)
        self.create_employee.assert_not_called();self.update_employee.assert_not_called()
        self.create_department.assert_not_called();self.update_department.assert_not_called()
        self.set_department_active_status.assert_not_called()

    def test_unexpected_failures_are_not_hidden(self):
        self.create_employee.side_effect=RuntimeError('unexpected failure')
        with self.assertRaises(RuntimeError): self.client.post('/employees/add',data=EMPLOYEE)
