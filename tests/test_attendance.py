"""Attendance validation, paging, write and security tests; no configured database."""
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta
import importlib
import unittest
from unittest.mock import MagicMock, patch

from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from attendance_validation import AttendanceError, STATUSES, values, listing_values, form_values, time_input
from security_helpers import csrf_client, stamp_session, user_state

FORM = dict(employee_id='1', attendance_date='2026-01-02', time_in='08:01:02',
            time_out='17:02:03', status='PRESENT', notes='PRIVATE <notes> & reason')


class AttendanceValidationTests(unittest.TestCase):
    def test_ids(self):
        for value in ('0','-1','1.1','1e2','2147483648',True,None,[], '9'*100):
            with self.subTest(value=value), self.assertRaises(AttendanceError): values(dict(FORM,employee_id=value))
        self.assertEqual(values(dict(FORM,employee_id=' 001 '))['employee_id'],1)

    def test_dates(self):
        for value in ('2026-02-29','2026-13-01','20260101','0999-12-31','0000-01-01',datetime(2026,1,1),None):
            with self.subTest(value=value), self.assertRaises(AttendanceError): values(dict(FORM,attendance_date=value))
        for value in ('1000-01-01','9999-12-31','2024-02-29',date(2026,1,1)):
            self.assertIsInstance(values(dict(FORM,attendance_date=value))['attendance_date'],date)

    def test_time_boundaries_and_no_invented_shift_rules(self):
        for field in ('time_in','time_out'):
            for bad in ('24:00','08:60','08:01:60','8:01','08:1','-01:00','08:01:00.1','08:01+01:00',True,1):
                with self.subTest(field=field,bad=bad),self.assertRaises(AttendanceError): values(dict(FORM,**{field:bad}))
        for status in STATUSES:
            self.assertIsNone(values(dict(FORM,status=status,time_in='',time_out=None))['time_in'])
            self.assertEqual(values(dict(FORM,status=status,time_in='23:59:59',time_out='00:00'))['time_in'],time(23,59,59))
        self.assertEqual(time_input(timedelta(hours=8,seconds=2)),'08:00:02')
        self.assertEqual(time_input(timedelta()),'00:00:00')

    def test_status_notes_unicode_and_lengths(self):
        self.assertEqual(values(dict(FORM,status=' late '))['status'],'LATE')
        self.assertEqual(values(dict(FORM,notes='?'*255))['notes'],'?'*255)
        for bad in ('x'*256,'\x00bad','\ud800',1,False):
            with self.subTest(bad=repr(bad)),self.assertRaises(AttendanceError): values(dict(FORM,notes=bad))
        for bad in ('', 'UNKNOWN', None):
            with self.assertRaises(AttendanceError): values(dict(FORM,status=bad))
        self.assertIsNone(values(dict(FORM,notes=None))['notes'])

    def test_duplicate_fields_and_paging_inputs(self):
        for field in FORM:
            form=MultiDict(FORM);form.add(field,FORM[field])
            with self.assertRaises(AttendanceError): form_values(form)
        for raw in ({'page':'0'},{'page':'2147483648'},{'page_size':'26'},{'status':'UNKNOWN'},
                    {'date':'0999-01-01'},{'department_id':'0'},{'search':'X'*101}):
            with self.subTest(raw=raw),self.assertRaises(AttendanceError): listing_values(raw)
        with self.assertRaises(AttendanceError): listing_values(MultiDict([('page','1'),('page','2')]))
        for size in (25,50,100): self.assertEqual(listing_values({'page_size':str(size)})['page_size'],size)


class AttendanceRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.safety=ExitStack();self.addCleanup(self.safety.close)
        self.safety.enter_context(patch('payroll_freshness.lock_guard'))  # Dedicated freshness suites exercise real schema/coordination.
        self.safety.enter_context(patch('payroll_freshness.advance'))
        self.safety.enter_context(patch('dotenv.load_dotenv',return_value=False))
        self.safety.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        self.repo=importlib.import_module('attendance_repository')
        storage=patch.object(self.repo,'_check_storage');storage.start();self.addCleanup(storage.stop)
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.patch=patch.object(self.repo,'get_connection',return_value=self.db)
        self.connect=self.patch.start();self.addCleanup(self.patch.stop)

    def test_invalid_inputs_precede_connection(self):
        with self.assertRaises(AttendanceError): self.repo.create_attendance_record(**dict(FORM,employee_id='0'),created_by=7)
        self.connect.assert_not_called()

    def test_write_commits_and_returns_numeric_identity(self):
        self.cur.fetchone.return_value={'employee_id':1};self.cur.lastrowid=41
        self.assertEqual(self.repo.create_attendance_record(**FORM,created_by=7),41)
        self.db.start_transaction.assert_called_once_with();self.db.commit.assert_called_once()
        self.db.close.assert_called_once()

    def test_deleted_employee_and_missing_update_rollback(self):
        self.cur.fetchone.return_value=None
        for edit in (False,True):
            with self.assertRaises(AttendanceError):
                if edit: self.repo.update_attendance_record(41,**FORM,updated_by=7)
                else: self.repo.create_attendance_record(**FORM,created_by=7)
        self.db.commit.assert_not_called();self.assertEqual(self.db.rollback.call_count,2)
        self.assertFalse(any('INSERT' in str(c) or 'UPDATE attendance_records SET' in str(c) for c in self.cur.execute.call_args_list))

    def test_duplicate_fk_lock_and_uncertain_commit_failures(self):
        self.cur.fetchone.return_value={'employee_id':1}
        for errno,code in ((1062,409),(1452,409),(1205,409),(1213,409),(2013,503)):
            self.db.commit.side_effect=Error('PRIVATE raw SQL',errno=errno)
            with self.subTest(errno=errno),self.assertRaises(AttendanceError) as raised:
                self.repo.create_attendance_record(**FORM,created_by=7)
            self.assertEqual(raised.exception.status_code,code);self.assertNotIn('PRIVATE',str(raised.exception))
        self.assertEqual(self.db.rollback.call_count,5)

    def test_disconnected_rollback_and_cleanup_stay_safe(self):
        self.cur.fetchone.return_value={'employee_id':1}
        self.db.commit.side_effect=Error('PRIVATE commit error',errno=2013)
        self.db.rollback.side_effect=Error('PRIVATE rollback error',errno=2013)
        self.cur.close.side_effect=Error('PRIVATE close error',errno=2013)
        self.db.close.side_effect=Error('PRIVATE close error',errno=2013)
        with self.assertRaises(AttendanceError) as raised:
            self.repo.create_attendance_record(**FORM,created_by=7)
        self.assertEqual(raised.exception.status_code,503)
        self.assertNotIn('PRIVATE',str(raised.exception))

    def test_paging_sql_clamps_page_and_preserves_filtered_summary(self):
        self.cur.fetchone.return_value=dict(total=51,present=51,late=0,absent=0,on_leave=0,half_day=0)
        self.cur.fetchall.return_value=[dict(attendance_id=51)]
        page=self.repo.get_attendance_page(dict(search='_%!',page='999',page_size='25',status='PRESENT',department_id='1'))
        self.assertEqual((page['page'],page['pages'],page['summary']['total']),(3,3,51))
        query,params=self.cur.execute.call_args.args
        self.assertEqual(params[-2:],(25,50));self.assertEqual(params[0],'%!_!%!!%')
        self.assertIn('a.attendance_id LIMIT',query)
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()


class AttendanceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-attendance',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['attendance.view','attendance.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.stack.enter_context(patch.object(self.erp,'get_all_employees',return_value=[dict(employee_id=1,employee_number='TEST',first_name='Test',last_name='Employee')]))
        self.stack.enter_context(patch.object(self.erp,'get_all_departments',return_value=[]))
        self.record=dict(values(FORM),attendance_id=41)
        self.read=self.stack.enter_context(patch.object(self.erp,'get_attendance_record_by_id',return_value=self.record))
        self.create=self.stack.enter_context(patch.object(self.erp,'create_attendance_record',return_value=41))
        self.update=self.stack.enter_context(patch.object(self.erp,'update_attendance_record',return_value=41))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)

    def test_create_and_update_emit_one_safe_numeric_audit(self):
        for path,action in (('/attendance/add','CREATE'),('/attendance/41/edit','UPDATE')):
            self.audit.reset_mock()
            self.assertEqual(self.client.post(path,data=FORM).status_code,302)
            self.audit.assert_called_once()
            event=self.audit.call_args.kwargs
            self.assertEqual((event['module'],event['action'],event['entity_id']),('ATTENDANCE',action,41))
            self.assertNotIn('PRIVATE',event['description']);self.assertNotIn('2026',event['description'])

    def test_validation_retains_escaped_values_and_selected_employee(self):
        for path in ('/attendance/add','/attendance/41/edit'):
            response=self.client.post(path,data=dict(FORM,time_in='25:00',employee_id='999'))
            self.assertEqual(response.status_code,400)
            html=response.get_data(as_text=True)
            self.assertIn('PRIVATE &lt;notes&gt; &amp; reason',html);self.assertIn('value="999" selected',html)
            self.assertIn('valid HH:MM',html)
        self.create.assert_not_called();self.update.assert_not_called();self.audit.assert_not_called()

    def test_write_failures_emit_no_success_event(self):
        for error in (AttendanceError('Duplicate',409),AttendanceError('Missing',404),AttendanceError('Uncertain commit',503)):
            self.create.side_effect=error
            self.assertEqual(self.client.post('/attendance/add',data=FORM).status_code,error.status_code)
        self.audit.assert_not_called()

    def test_audit_failure_does_not_reverse_success(self):
        self.audit.side_effect=RuntimeError('synthetic audit outage')
        with patch.object(self.erp.app.logger,'exception'):
            self.assertEqual(self.client.post('/attendance/add',data=FORM).status_code,302)
        self.create.assert_called_once()

    def test_missing_target_and_get_time_format(self):
        self.record['time_in']=timedelta(hours=8,seconds=2)
        self.assertIn('value="08:00:02"',self.client.get('/attendance/41/edit').get_data(as_text=True))
        self.read.return_value=None
        self.assertEqual(self.client.post('/attendance/41/edit',data=FORM).status_code,404)
        self.update.assert_not_called();self.audit.assert_not_called()

    def test_permission_csrf_revocation_and_compatibility_gate(self):
        for path in ('/attendance/add','/attendance/41/edit'):
            self.assertEqual(self.client.post(path,data=FORM,headers={'X-CSRFToken':'invalid'}).status_code,400)
            self.assertIn('name="csrf_token"',self.client.get(path).get_data(as_text=True))
        self.state['permissions']=frozenset(['attendance.view'])
        self.assertEqual(self.client.post('/attendance/add',data=FORM).status_code,302)
        self.assertEqual(self.client.get('/attendance/41/edit').status_code,302)
        self.state['is_active']=False
        self.assertTrue(self.client.post('/attendance/add',data=FORM).location.endswith('/login'))
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('private')):
            self.assertEqual(self.client.post('/attendance/add',data=FORM).status_code,503)
        self.create.assert_not_called();self.update.assert_not_called();self.audit.assert_not_called()

    def test_listing_links_keep_filters_and_filtered_totals(self):
        summary=dict(total=51,present=51,late=0,absent=0,on_leave=0,half_day=0)
        with patch.object(self.erp,'get_attendance_page',return_value=dict(records=[],summary=summary,page=2,pages=3,page_size=25)) as read:
            response=self.client.get('/attendance?search=A%26B&date=2026-01-02&status=PRESENT&department_id=1&page=2&page_size=25')
            self.assertEqual(response.status_code,200)
            html=response.get_data(as_text=True)
            self.assertIn('Page 2 of 3',html);self.assertIn('search=A%26B',html);self.assertIn('page_size=25',html)
            self.assertIn('51 records',html)
        self.assertEqual(self.client.get('/attendance?page_size=26').status_code,400)

    def test_midnight_is_displayed_as_time_not_missing(self):
        summary=dict(total=1,present=1,late=0,absent=0,on_leave=0,half_day=0)
        record=dict(self.record,time_in=timedelta(),time_out=timedelta(hours=1))
        with patch.object(self.erp,'get_attendance_page',return_value=dict(records=[record],summary=summary,page=1,pages=1,page_size=25)):
            html=self.client.get('/attendance').get_data(as_text=True)
            self.assertIn('00:00:00',html);self.assertIn('01:00:00',html)
