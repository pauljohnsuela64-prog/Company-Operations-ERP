"""HR audit boundaries without any configured database connection."""
import unittest
from unittest.mock import patch
import test_hr_validation as fixtures
from hr_revision import HRWriteResult, HRConflictError, HRMissingRecordError, HRRevisionExhaustedError
from hr_validation import HRValidationError


class HRAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.HRRouteTests.setUpClass.__func__(cls)

    def setUp(self):
        fixtures.HRRouteTests.setUp(self)
        self.audit = self.stack.enter_context(patch.object(self.erp, 'create_audit_log'))
        self.cases = [
            ('/employees/add', fixtures.EMPLOYEE, 'create_employee', 'CREATE', 'EMPLOYEE', 'Employee 1 created; revision 1.'),
            ('/employees/1/edit', dict(fixtures.EMPLOYEE, employment_status='Active', expected_revision='1'), 'update_employee', 'UPDATE', 'EMPLOYEE', 'Employee 1 profile save committed; revision 1 to 2.'),
            ('/departments/add', fixtures.DEPARTMENT, 'create_department', 'CREATE', 'DEPARTMENT', 'Department 1 created; revision 1.'),
            ('/departments/1/edit', dict(fixtures.DEPARTMENT, expected_revision='1'), 'update_department', 'UPDATE', 'DEPARTMENT', 'Department 1 detail save committed; revision 1 to 2.'),
            ('/departments/1/status', dict(is_active='0', expected_revision='1'), 'set_department_active_status', 'DEACTIVATE', 'DEPARTMENT', 'Department 1 deactivated; revision 1 to 2.'),
            ('/departments/1/status', dict(is_active='1', expected_revision='1'), 'set_department_active_status', 'ACTIVATE', 'DEPARTMENT', 'Department 1 activated; revision 1 to 2.'),
        ]

    def test_success_actor_numeric_target_and_exact_bounded_content(self):
        for path, form, repo, action, entity, description in self.cases:
            with self.subTest(action=action, entity=entity):
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path, data=form).status_code, 302)
                self.audit.assert_called_once_with(user_id=7, username='acting.user', module='HR', action=action,
                    entity_type=entity, entity_id=1, description=description)

    def test_unchanged_and_status_department_profile_saves_are_single_updates(self):
        for overrides in ({}, dict(employment_status='Resigned', department_id='2')):
            self.audit.reset_mock()
            form=dict(self.cases[1][1], **overrides)
            self.assertEqual(self.client.post('/employees/1/edit', data=form).status_code,302)
            self.assertEqual(self.audit.call_count,1)
            self.assertEqual(self.audit.call_args.kwargs['action'],'UPDATE')
            self.assertEqual(self.audit.call_args.kwargs['description'],self.cases[1][-1])

    def test_metadata_uses_repository_results_without_audit_lookup(self):
        self.create_employee.return_value=42
        self.create_department.return_value=9
        for index,target in ((0,42),(2,9)):
            self.audit.reset_mock()
            case=self.cases[index]
            self.client.post(case[0],data=case[1])
            self.assertEqual(self.audit.call_args.kwargs['entity_id'],target)
        self.update_employee.return_value=HRWriteResult(8)
        self.client.post(self.cases[1][0],data=self.cases[1][1])
        self.assertEqual(self.audit.call_args.kwargs['description'],'Employee 1 profile save committed; revision 7 to 8.')
        self.get_employee_by_id.assert_called_once_with(1)
        self.get_department_by_id.assert_not_called()

    def test_unauthenticated_and_explicit_invalid_csrf_emit_nothing(self):
        from security_helpers import csrf_client
        anonymous=csrf_client(self.erp.app)
        for path,form,*_ in self.cases:
            self.assertEqual(anonymous.post(path,data=form).status_code,302)
            self.assertEqual(self.client.post(path,data=form,headers={'X-CSRFToken':'invalid'}).status_code,400)
        self.audit.assert_not_called()

    def test_noop_has_no_audit_even_with_newer_returned_revision(self):
        self.set_department_active_status.return_value=HRWriteResult(9,changed=False)
        self.client.post('/departments/1/status',data=self.cases[4][1])
        self.audit.assert_not_called()

    def test_repository_failures_never_emit(self):
        for path,form,repo,*_ in self.cases:
            for error in (HRValidationError('duplicate or invalid'), RuntimeError('SQL rollback or commit acknowledgement failure'),
                          HRConflictError('stale or future'), HRMissingRecordError('missing'), HRRevisionExhaustedError('exhausted')):
                if 'add' in path and not isinstance(error,(HRValidationError,RuntimeError)):
                    continue
                with self.subTest(path=path,error=type(error).__name__):
                    target=getattr(self,repo)
                    target.side_effect=error
                    try:
                        if isinstance(error,RuntimeError):
                            with self.assertRaises(RuntimeError):self.client.post(path,data=form)
                        else:self.client.post(path,data=form)
                        self.audit.assert_not_called()
                    finally:target.side_effect=None

    def test_validation_missing_revision_and_security_rejections(self):
        fixtures.HRRouteTests.test_permissions_revocation_csrf_and_disabled_accounts(self)
        self.audit.assert_not_called()

    def test_invalid_forms_revisions_and_missing_lookups(self):
        for path,form,repo,*_ in self.cases:
            if 'add' in path:
                invalid=dict(form)
                invalid['employee_number' if 'employees' in path else 'department_code']=''
                self.client.post(path,data=invalid)
            else:
                for bad in ('','0','-1','1.0','9'*30):
                    self.assertEqual(self.client.post(path,data=dict(form,expected_revision=bad)).status_code,400)
        self.get_employee_by_id.return_value=None
        self.get_department_by_id.return_value=None
        for case in (self.cases[1],self.cases[3]):
            self.assertEqual(self.client.post(case[0],data=case[1]).status_code,404)
        self.audit.assert_not_called()

    def test_audit_failure_preserves_success_and_no_retry(self):
        self.audit.side_effect=RuntimeError('synthetic audit failure')
        for path,form,*_ in self.cases:
            self.audit.reset_mock()
            with self.assertLogs(self.erp.app.logger,level='ERROR'):
                self.assertEqual(self.client.post(path,data=form).status_code,302)
            self.assertEqual(self.audit.call_count,1)


if __name__=='__main__':unittest.main()
