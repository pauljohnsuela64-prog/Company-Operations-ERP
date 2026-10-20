"""Leave validation, HTTP/audit ordering and transactional failure unit checks."""
from contextlib import ExitStack
from datetime import date, datetime
from decimal import Decimal
import importlib
import unittest
from unittest.mock import MagicMock, patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from leave_validation import LeaveError, request_values, type_values, listing_values, unique_values, REQUEST_FIELDS
from security_helpers import csrf_client, stamp_session, user_state

FORM = dict(employee_id='1', leave_type_id='1', start_date='2027-01-01', end_date='2027-01-02', reason='PRIVATE <script>reason</script>')
TYPE = dict(leave_code='SYN', leave_name='Synthetic', description='', annual_entitlement='5.00', is_paid='1')


class LeaveValidationTests(unittest.TestCase):
    def test_strict_id_boundaries(self):
        for field in ('employee_id', 'leave_type_id'):
            for value in ('0', '-1', '1e2', '1.0', '2147483648', True, None, '\uff11'):
                with self.subTest(field=field, value=value), self.assertRaises(LeaveError):
                    request_values(dict(FORM, **{field: value}))
        self.assertEqual(request_values(dict(FORM, employee_id='001'))['employee_id'], 1)

    def test_dates_and_physical_days_capacity(self):
        for value in ('0999-12-31', '2027-02-29', '20270101', datetime(2027, 1, 1), None):
            with self.assertRaises(LeaveError): request_values(dict(FORM, start_date=value))
        with self.assertRaises(LeaveError): request_values(dict(FORM, end_date='2026-12-31'))
        with self.assertRaises(LeaveError): request_values(dict(FORM, end_date='2030-01-01'))
        self.assertEqual(request_values(dict(FORM, start_date='9999-12-31', end_date='9999-12-31'))['total_days'], 1)
        self.assertEqual(request_values(dict(FORM, start_date='2024-02-28', end_date='2024-03-01'))['total_days'], 3)

    def test_reason_utf8_controls_and_lengths(self):
        self.assertEqual(len(request_values(dict(FORM, reason='\u00e9'*500))['reason']), 500)
        for value in ('', 'X'*501, '\x00', '\ud800', False, 1):
            with self.assertRaises(LeaveError): request_values(dict(FORM, reason=value))

    def test_duplicate_form_fields(self):
        for field in FORM:
            form = MultiDict(FORM); form.add(field, FORM[field])
            with self.assertRaises(LeaveError): unique_values(form, REQUEST_FIELDS)

    def test_type_storage_limits_without_changing_entitlements(self):
        for value in ('NaN', 'Infinity', '-0.01', '1000', '.001', '1e999', True):
            with self.assertRaises(LeaveError): type_values(dict(TYPE, annual_entitlement=value))
        self.assertIsNone(type_values(dict(TYPE, annual_entitlement=''))['annual_entitlement'])
        self.assertEqual(type_values(dict(TYPE, annual_entitlement='999.99'))['annual_entitlement'], Decimal('999.99'))
        for field, bad in (('leave_code','\u00df'*30), ('leave_name','X'*101), ('description','X'*256), ('description',False), ('is_paid','yes')):
            with self.assertRaises(LeaveError): type_values(dict(TYPE, **{field:bad}))

    def test_filters_strict_and_bounded(self):
        for raw in ({'page':'0'}, {'page_size':'26'}, {'search':'X'*101}, {'status':'OTHER'},
                    {'leave_type_id':'0'}, {'department_id':'1e2'}, {'date_from':'2027-02-01','date_to':'2027-01-01'}):
            with self.assertRaises(LeaveError): listing_values(raw)
        with self.assertRaises(LeaveError): listing_values(MultiDict([('status','PENDING'),('status','APPROVED')]))
        for size in (25,50,100): self.assertEqual(listing_values({'page_size':str(size)})['page_size'],size)


class LeaveRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        self.stack.enter_context(patch('mysql.connector.connect', side_effect=AssertionError('Company DB forbidden')))
        self.repo = importlib.import_module('leave_repository')
        self.db = MagicMock(); self.cur = self.db.cursor.return_value
        self.factory = self.stack.enter_context(patch.object(self.repo, 'get_connection', return_value=self.db))
        self.stack.enter_context(patch.object(self.repo, '_check_storage'))

    def test_validation_before_connections(self):
        with self.assertRaises(LeaveError): self.repo.create_leave_request(**request_values(FORM), requested_by=0)
        with self.assertRaises(LeaveError): self.repo.reject_leave_request(1,1,'X'*501)
        with self.assertRaises(LeaveError): self.repo.create_leave_request(**dict(request_values(FORM),total_days=1), requested_by=1)
        self.factory.assert_not_called()

    def test_create_locks_before_overlap_and_commits_final_number(self):
        self.cur.fetchone.side_effect=[{'employee_id':1},{'is_active':1}]
        self.cur.fetchall.return_value=[]; self.cur.lastrowid=42
        self.assertEqual(self.repo.create_leave_request(**request_values(FORM),requested_by=1),(42,'LR-000042'))
        queries=[call.args[0] for call in self.cur.execute.call_args_list]
        self.assertIn('employees',queries[0]); self.assertIn('FOR UPDATE',queries[0])
        self.assertIn('FOR SHARE',queries[1]);self.assertIn('FOR UPDATE',queries[2])
        self.assertIn('INSERT INTO leave_requests',queries[3]); self.db.commit.assert_called_once()

    def test_overlap_rolls_back_without_insert(self):
        self.cur.fetchone.side_effect=[{'employee_id':1},{'is_active':1}]
        self.cur.fetchall.return_value=[{'leave_request_id':2}]
        with self.assertRaises(LeaveError) as raised: self.repo.create_leave_request(**request_values(FORM),requested_by=1)
        self.assertEqual(raised.exception.status_code,409)
        self.db.rollback.assert_called_once();self.db.commit.assert_not_called()
        self.assertFalse(any('INSERT' in c.args[0] for c in self.cur.execute.call_args_list))

    def test_inactive_or_missing_references(self):
        for rows in ([None],[{'employee_id':1},None],[{'employee_id':1},{'is_active':0}]):
            self.cur.fetchone.side_effect=rows
            with self.assertRaises(LeaveError): self.repo.create_leave_request(**request_values(FORM),requested_by=1)
        self.db.commit.assert_not_called()

    def test_sql_and_uncertain_commit_errors_never_report_success(self):
        self.cur.fetchone.return_value={'status':'PENDING'}
        for errno,code in ((1062,409),(1452,409),(1205,409),(1213,409),(2013,503)):
            self.db.commit.side_effect=Error('PRIVATE raw SQL',errno=errno)
            with self.assertRaises(LeaveError) as raised:self.repo.cancel_leave_request(1)
            self.assertEqual(raised.exception.status_code,code);self.assertNotIn('PRIVATE',str(raised.exception))
        self.assertEqual(self.db.rollback.call_count,5)

    def test_cleanup_error_after_commit_is_uncertain(self):
        self.cur.fetchone.return_value={'status':'PENDING'}
        self.cur.close.side_effect=Error('close failed',errno=2013)
        self.db.close.side_effect=Error('close failed',errno=2013)
        with self.assertRaises(LeaveError) as raised:self.repo.cancel_leave_request(1)
        self.db.commit.assert_called_once();self.assertEqual(raised.exception.status_code,503)

    def test_missing_and_finalized_transitions(self):
        for row,code in ((None,404),({'status':'APPROVED'},409)):
            self.cur.fetchone.return_value=row
            with self.assertRaises(LeaveError) as raised:self.repo.cancel_leave_request(1)
            self.assertEqual(raised.exception.status_code,code)
        self.db.commit.assert_not_called()

    def test_malformed_historical_dates_fail_without_attendance_writes(self):
        row = dict(employee_id=1, leave_type_id=1, status='PENDING', start_date=None, end_date=date(2027,1,1))
        self.cur.fetchone.side_effect = [row, row, row, row]
        with self.assertRaises(LeaveError) as raised:
            self.repo.approve_leave_request(1,1)
        self.assertEqual(raised.exception.status_code,409)
        self.db.commit.assert_not_called()
        self.db.rollback.assert_called_once()
        self.assertFalse(any('attendance_records' in c.args[0] for c in self.cur.execute.call_args_list))

    def test_snapshot_pagination_clamps_and_binds_literal_search(self):
        self.cur.fetchone.return_value=dict(total=51,pending=51,approved=0,rejected=0,cancelled=0)
        self.cur.fetchall.return_value=[]
        page=self.repo.get_leave_request_page(dict(search='%_!',page='999',date_from='2027-01-01',page_size='25'))
        self.assertEqual((page['page'],page['pages'],page['summary']['total']),(3,3,51))
        query,params=self.cur.execute.call_args.args
        self.assertEqual(params[0],'%!%!_!!%');self.assertEqual(params[-2:],(25,50))
        self.assertIn('lr.leave_request_id DESC LIMIT',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called()


class LeaveRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safety=ExitStack();cls.addClassCleanup(cls.safety.close)
        cls.safety.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.safety.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-leave-unit',ERP_ENV='testing'))
        cls.safety.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['leave.view','leave.manage','leave.approve'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.stack.enter_context(patch.object(self.erp,'get_all_employees',return_value=[dict(employee_id=1,employee_number='SYN',first_name='Test',last_name='Employee')]))
        types=[dict(leave_type_id=1,leave_name='Synthetic',is_active=1)]
        for name in ('get_all_leave_types','get_active_leave_types'):self.stack.enter_context(patch.object(self.erp,name,return_value=types))
        self.stack.enter_context(patch.object(self.erp,'get_all_departments',return_value=[]))
        self.record=dict(request_values(FORM),leave_request_id=42,request_number='LR-000042',status='PENDING',first_name='Test',last_name='Employee')
        self.stack.enter_context(patch.object(self.erp,'get_leave_request_by_id',return_value=self.record))
        self.create=self.stack.enter_context(patch.object(self.erp,'create_leave_request',return_value=(42,'LR-000042')))
        self.approve=self.stack.enter_context(patch.object(self.erp,'approve_leave_request'))
        self.reject=self.stack.enter_context(patch.object(self.erp,'reject_leave_request'))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)

    def test_valid_create_keeps_existing_no_create_audit_semantics(self):
        self.assertEqual(self.client.post('/leave/requests/add',data=FORM).status_code,302)
        self.create.assert_called_once();self.audit.assert_not_called()

    def test_invalid_retained_escaped_form_and_duplicate_fields(self):
        response=self.client.post('/leave/requests/add',data=dict(FORM,end_date='2026-01-01',employee_id='999'))
        self.assertEqual(response.status_code,400)
        html=response.get_data(as_text=True)
        self.assertIn('PRIVATE &lt;script&gt;reason&lt;/script&gt;',html);self.assertIn('value="999" selected',html)
        data=MultiDict(FORM);data.add('employee_id','2')
        self.assertEqual(self.client.post('/leave/requests/add',data=data).status_code,400)
        self.create.assert_not_called()

    def test_conflict_and_uncertain_save_preserve_fields(self):
        for code in (409,503):
            self.create.side_effect=LeaveError('Reload and verify',code)
            response=self.client.post('/leave/requests/add',data=FORM)
            self.assertEqual(response.status_code,code);self.assertIn('PRIVATE &lt;script&gt;',response.get_data(as_text=True))
        self.audit.assert_not_called()

    def test_rejection_failure_retains_reason_and_never_audits(self):
        response=self.client.post('/leave/requests/42/reject',data={'rejection_reason':'X'*501})
        self.assertEqual(response.status_code,400);self.assertIn('X'*501,response.get_data(as_text=True))
        self.reject.assert_not_called();self.audit.assert_not_called()

    def test_approval_audit_after_return_and_failure_isolation(self):
        order=[];self.approve.side_effect=lambda **kw:order.append('commit')
        self.audit.side_effect=lambda **kw:order.append('audit')
        self.assertEqual(self.client.post('/leave/requests/42/approve').status_code,302)
        self.assertEqual(order,['commit','audit'])
        self.approve.side_effect=LeaveError('Conflict',409);self.audit.reset_mock()
        self.assertEqual(self.client.post('/leave/requests/42/approve').status_code,409);self.audit.assert_not_called()
        self.approve.side_effect=None;self.audit.side_effect=RuntimeError('audit unavailable')
        with patch.object(self.erp.app.logger,'exception'):
            self.assertEqual(self.client.post('/leave/requests/42/approve').status_code,302)

    def test_listing_retains_filters_and_shows_full_counts(self):
        page=dict(records=[],summary=dict(total=51,pending=51,approved=0,rejected=0,cancelled=0),page=2,pages=3)
        with patch.object(self.erp,'get_leave_request_page',return_value=page):
            response=self.client.get('/leave/requests?search=A%26B&status=PENDING&page=2&page_size=25')
        html=response.get_data(as_text=True)
        self.assertEqual(response.status_code,200);self.assertIn('Page 2 of 3',html);self.assertIn('search=A%26B',html);self.assertIn('51 requests',html)
        self.assertEqual(self.client.get('/leave/requests?page_size=26').status_code,400)

    def test_permissions_csrf_revocation_and_schema_gate(self):
        self.assertEqual(self.client.post('/leave/requests/add',data=FORM,headers={'X-CSRFToken':'bad'}).status_code,400)
        self.assertEqual(self.client.get('/leave/requests/42/approve').status_code,405)
        self.state['permissions']=frozenset(['leave.view'])
        self.assertEqual(self.client.post('/leave/requests/add',data=FORM).status_code,302)
        self.assertEqual(self.client.post('/leave/requests/42/approve').status_code,302)
        self.state['is_active']=False
        self.assertTrue(self.client.post('/leave/requests/add',data=FORM).location.endswith('/login'))
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('private')):
            self.assertEqual(self.client.post('/leave/requests/add',data=FORM).status_code,503)
        self.create.assert_not_called();self.approve.assert_not_called()

    def test_missing_or_oversized_route_ids_are_safe(self):
        for value in (0,2147483648):
            self.assertEqual(self.client.get(f'/leave/requests/{value}').status_code,404)
            for action in ('approve','reject','cancel'):
                self.assertEqual(self.client.post(f'/leave/requests/{value}/{action}',data={'rejection_reason':'reason'}).status_code,404)
            self.assertEqual(self.client.get(f'/leave/types/{value}/edit').status_code,404)
            self.assertEqual(self.client.post(f'/leave/types/{value}/status').status_code,404)
        self.create.assert_not_called();self.approve.assert_not_called();self.reject.assert_not_called()

    def test_type_forms_retain_data_and_validate_before_repository(self):
        with patch.object(self.erp,'create_leave_type') as create:
            response=self.client.post('/leave/types/add',data=dict(TYPE,annual_entitlement='NaN'))
            self.assertEqual(response.status_code,400);self.assertIn('value="SYN"',response.get_data(as_text=True));create.assert_not_called()
        existing=dict(TYPE,leave_type_id=1,annual_entitlement=Decimal('5.00'),is_paid=False)
        with patch.object(self.erp,'get_leave_type_by_id',return_value=existing):
            html=self.client.get('/leave/types/1/edit').get_data(as_text=True)
            self.assertIn('value="SYN"',html);self.assertIn('value="5.00"',html);self.assertNotIn('checked',html)
