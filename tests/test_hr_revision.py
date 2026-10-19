"""Version parsing and safe conflict responses; company DB access is forbidden."""
import unittest
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from werkzeug.datastructures import MultiDict

import test_hr_validation as fixtures
from hr_revision import (revision, form_revision, require_current, require_incrementable,
    MAX_REVISION, HRWriteResult, HRRevisionInputError, HRConflictError,
    HRMissingRecordError, HRRevisionExhaustedError)


class RevisionInputTests(unittest.TestCase):
    def test_migration_import_is_inert_and_rejects_existing_transaction(self):
        path=Path(__file__).resolve().parents[1]/'database/migrations/008_hr_employee_department_revisions.py'
        spec=importlib.util.spec_from_file_location('inert_hr_revision_upgrade',path)
        module=importlib.util.module_from_spec(spec)
        with patch('mysql.connector.connect',side_effect=AssertionError('No implicit DB target')), \
             patch('dotenv.load_dotenv',side_effect=AssertionError('No implicit environment')):
            spec.loader.exec_module(module)
            with self.assertRaises(RuntimeError):
                module.upgrade(SimpleNamespace(in_transaction=True))

    def test_integer_range_without_float_or_bigint_coercion(self):
        for value in (1,'1',str(MAX_REVISION)):
            self.assertEqual(revision(value),int(value))
        for value in (None,'',0,-1,True,False,1.0,'1.0','1e2','+1','NaN',
                      str(MAX_REVISION+1),'9'*1000,'١'):
            with self.subTest(value=str(value)[:25]),self.assertRaises(HRRevisionInputError):
                revision(value)
        with self.assertRaises(HRRevisionInputError):
            form_revision(MultiDict([('expected_revision','1'),('expected_revision','2')]))
        with self.assertRaises(HRConflictError):require_current(2,1)
        with self.assertRaises(HRConflictError):require_current(1,2)
        with self.assertRaises(HRRevisionExhaustedError):require_incrementable(MAX_REVISION)
        require_incrementable(MAX_REVISION-1)


class RevisionRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HRRouteTests.setUpClass.__func__(cls)

    setUp = fixtures.HRRouteTests.setUp

    def test_get_tokens_and_ordinary_validation_keep_submitted_revision(self):
        for path,data,target in [('/employees/1/edit',dict(fixtures.EMPLOYEE,employment_status='Active',phone='P'*31),self.employee),
                                 ('/departments/1/edit',dict(fixtures.DEPARTMENT,description='D'*256),self.department)]:
            self.assertIn('name="expected_revision" value="1"',self.client.get(path).get_data(as_text=True))
            target['revision']=2
            response=self.client.post(path,data=dict(data,expected_revision='1'))
            self.assertEqual(response.status_code,200)
            self.assertIn('name="expected_revision" value="1"',response.get_data(as_text=True))
            self.assertNotIn('name="expected_revision" value="2"',response.get_data(as_text=True))
        self.update_employee.assert_not_called();self.update_department.assert_not_called()

    def test_stale_values_are_escaped_with_no_save_or_refreshed_token(self):
        self.update_employee.side_effect=HRConflictError('This record changed since you opened the form. Your changes were not saved.')
        response=self.client.post('/employees/1/edit',data=dict(fixtures.EMPLOYEE,first_name='<script>alert(1)</script>',employment_status='Active',expected_revision='1'))
        html=response.get_data(as_text=True)
        self.assertEqual(response.status_code,409)
        self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('Reload current data',html)
        self.assertNotIn('name="expected_revision"',html)
        self.assertNotIn('Save Changes',html)
        self.assertNotIn('Employee updated successfully.',html)

    def test_revisions_are_required_and_never_filled_from_latest_model(self):
        for path,data in [('/employees/1/edit',dict(fixtures.EMPLOYEE,employment_status='Active')),
                          ('/departments/1/edit',fixtures.DEPARTMENT),
                          ('/departments/1/status',{'is_active':'0'})]:
            for bad in (None,'0','-1','abc',str(MAX_REVISION+1)):
                form=dict(data)
                if bad is not None:form['expected_revision']=bad
                self.assertEqual(self.client.post(path,data=form).status_code,400)
        self.update_employee.assert_not_called();self.update_department.assert_not_called()
        self.set_department_active_status.assert_not_called()

    def test_department_detail_and_status_conflicts_and_noop(self):
        self.update_department.side_effect=HRConflictError('This record changed since you opened the form. Your changes were not saved.')
        self.assertEqual(self.client.post('/departments/1/edit',data=dict(fixtures.DEPARTMENT,expected_revision='1')).status_code,409)
        self.set_department_active_status.side_effect=HRConflictError('Record changed.')
        self.assertEqual(self.client.post('/departments/1/status',data={'expected_revision':'1','is_active':'0'}).status_code,409)
        self.set_department_active_status.side_effect=None
        self.set_department_active_status.return_value=HRWriteResult(2,changed=False)
        response=self.client.post('/departments/1/status',data={'expected_revision':'1','is_active':'0'})
        self.assertEqual(response.status_code,302)
        with self.client.session_transaction() as session:
            self.assertIn(('info','Department is already in the requested state.'),session['_flashes'])

    def test_missing_and_exhausted_records_have_distinct_safe_responses(self):
        for error,status in [(HRMissingRecordError('Employee no longer exists.'),404),
                             (HRRevisionExhaustedError('Contact an administrator.'),503)]:
            self.update_employee.side_effect=error
            response=self.client.post('/employees/1/edit',data=dict(fixtures.EMPLOYEE,employment_status='Active',expected_revision='1'))
            self.assertEqual(response.status_code,status)
            self.assertNotIn('name="expected_revision"',response.get_data(as_text=True))
