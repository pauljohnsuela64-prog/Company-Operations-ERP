"""Audit Logs validation, bounded read-only queries and HTTP security."""
from contextlib import ExitStack
from datetime import date,datetime
import importlib
import unittest
from unittest.mock import MagicMock,patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from audit_log_validation import AuditLogError,FIELDS,filter_values
from security_helpers import csrf_client,stamp_session,user_state


class AuditLogFilterTests(unittest.TestCase):
    def test_defaults_and_page_sizes(self):
        self.assertEqual((filter_values({})['page'],filter_values({})['page_size']),(1,25))
        for size in (25,50,100):self.assertEqual(filter_values({'page_size':str(size)})['page_size'],size)
        for raw in ({'page':'0'},{'page':'-1'},{'page':'1e2'},{'page':True},{'page':'2147483648'},
                    {'page':'\uff11'},{'page_size':'500'},{'page_size':'26'},{'start_dat':'2026-01-01'}):
            with self.subTest(raw=raw),self.assertRaises(AuditLogError):filter_values(raw)

    def test_text_boundaries_unicode_and_controls(self):
        self.assertEqual(len(filter_values({'search':'x'*100})['search']),100)
        for raw in ({'search':'x'*101},{'module':'x'*51},{'action':'x'*51},{'search':False},
                    {'search':'x\x00'},{'search':'x\n'},{'action':'\tREAD'},{'module':'x\nY'},{'search':'\ud800'}):
            with self.assertRaises(AuditLogError):filter_values(raw)
        self.assertEqual(filter_values({'search':' \u00e9%_! '})['search'],'\u00e9%_!')

    def test_historical_names_and_unknown_values_are_exact_not_dropped(self):
        values=filter_values({'module':'Legacy Ops','action':'Read / Inspect'})
        self.assertEqual((values['module'],values['action']),('Legacy Ops','Read / Inspect'))
        self.assertEqual(filter_values({'module':'UNKNOWN'})['module'],'UNKNOWN')

    def test_strict_dates_and_reversed_ranges(self):
        for value in ('2026-02-29','20260101','0999-12-31','2026-13-01',datetime(2026,1,1),'   '):
            with self.assertRaises(AuditLogError):filter_values({'start_date':value})
        with self.assertRaises(AuditLogError):filter_values({'start_date':'2026-02-02','end_date':'2026-02-01'})
        for value in ('1000-01-01','9999-12-31','2024-02-29'):
            self.assertIsInstance(filter_values({'end_date':value})['end_date'],date)

    def test_duplicate_filters(self):
        for field in FIELDS:
            with self.assertRaises(AuditLogError):filter_values(MultiDict([(field,'1'),(field,'2')]))


class AuditLogRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        self.stack.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        self.repo=importlib.import_module('audit_log_repository')
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(self.repo,'get_connection',return_value=self.db))
        self.real_storage=self.repo._check_audit_storage
        self.storage=self.stack.enter_context(patch.object(self.repo,'_check_audit_storage'))
        self.cur.fetchone.return_value={'total':251}
        self.cur.fetchall.side_effect=[[dict(audit_log_id=1)], [{'module':'Legacy Ops'}],[{'action':'READ'}]]

    def test_invalid_filters_precede_connection(self):
        for raw in ({'page_size':'500'},{'start_date':'bad'},{'module':False},{'unexpected':'value'}):
            with self.assertRaises(AuditLogError):self.repo.get_audit_log_page(raw)
        with self.assertRaises(AuditLogError):self.repo.get_filtered_audit_logs(search_text=False)
        self.factory.assert_not_called()

    def test_count_page_options_and_read_only_cleanup(self):
        page=self.repo.get_audit_log_page({'page':'999'})
        self.assertEqual((page['total'],page['pages'],page['filters']['page'],page['first'],page['last']),(251,11,11,251,251))
        self.assertEqual(page['modules'],['Legacy Ops'])
        query,params=self.cur.execute.call_args_list[1].args
        self.assertIn('created_at DESC,audit_log_id DESC LIMIT %s OFFSET %s',query);self.assertEqual(params,(25,250))
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once();self.cur.close.assert_called_once();self.db.close.assert_called_once()
        for call in self.cur.execute.call_args_list:self.assertTrue(call.args[0].startswith('SELECT'))

    def test_literal_parameterized_search_and_inclusive_dates(self):
        needle="%_!' OR 1=1"
        self.repo.get_audit_log_page(dict(search=needle,module='Legacy Ops',action='READ',start_date='2026-01-01',end_date='2026-01-02'))
        query,params=self.cur.execute.call_args_list[1].args
        self.assertNotIn(needle,query);self.assertEqual(params[0],"%!%!_!!' OR 1=1%")
        self.assertEqual(params[6:10],('Legacy Ops','READ',date(2026,1,1),datetime(2026,1,3)))
        self.assertIn('created_at < %s',query)

    def test_maximum_end_date_never_overflows_or_drops_bound(self):
        self.repo.get_audit_log_page({'end_date':'9999-12-31'})
        query,params=self.cur.execute.call_args_list[1].args
        self.assertIn('created_at <= %s',query);self.assertEqual(params[0],'9999-12-31 23:59:59.999999')
        self.assertNotIn('DATE_ADD',query)

    def test_empty_state_counts_and_compatibility_list_api(self):
        self.cur.fetchone.return_value={'total':0}
        self.cur.fetchall.side_effect=[[]]
        self.assertEqual(self.repo.get_filtered_audit_logs(module='UNKNOWN'),[])
        self.assertEqual(len(self.cur.execute.call_args_list),2)
        self.db.commit.assert_not_called()

    def test_read_failure_never_returns_partial_page(self):
        self.cur.execute.side_effect=Error('PRIVATE SQL failure',errno=1146)
        with self.assertRaises(AuditLogError) as raised:self.repo.get_audit_log_page({})
        self.assertEqual(raised.exception.status_code,503);self.assertNotIn('PRIVATE',str(raised.exception))
        self.db.close.assert_called_once();self.db.commit.assert_not_called()

    def test_cleanup_failure_is_not_hidden(self):
        self.db.rollback.side_effect=Error('rollback failed',errno=2013)
        self.cur.close.side_effect=Error('close failed',errno=2013)
        with self.assertRaises(AuditLogError) as raised:self.repo.get_audit_log_page({})
        self.assertEqual(raised.exception.status_code,503);self.db.close.assert_called_once()

    def test_storage_requires_innodb_and_unique_identity(self):
        check=self.real_storage;cursor=MagicMock()
        cursor.fetchone.return_value={'ENGINE':'InnoDB'}
        cursor.fetchall.return_value=[{'NON_UNIQUE':0,'COLUMN_NAME':'audit_log_id','SUB_PART':None}]
        check(cursor)
        for engine in (None,{'ENGINE':'MyISAM'}):
            cursor.fetchone.return_value=engine
            with self.assertRaises(AuditLogError):check(cursor)
        cursor.fetchone.return_value={'ENGINE':'InnoDB'}
        for keys in ([],[{'NON_UNIQUE':0,'COLUMN_NAME':'other','SUB_PART':None}]):
            cursor.fetchall.return_value=keys
            with self.assertRaises(AuditLogError):check(cursor)


class AuditLogRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-audit-reading',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['audit_logs.view'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.writer=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.read=self.stack.enter_context(patch.object(self.erp,'get_audit_log_page'))
        values=filter_values(dict(search='A&B',module='Legacy Ops',action='READ',start_date='2026-01-01',end_date='2026-01-02',page='2'))
        self.page=dict(records=[],total=51,pages=3,first=26,last=50,filters=values,modules=['Legacy Ops'],actions=['READ'])
        self.read.return_value=self.page
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)

    def test_counts_links_and_privacy_headers(self):
        response=self.client.get('/admin/audit-logs')
        self.assertEqual(response.status_code,200);html=response.get_data(as_text=True)
        for value in ('Showing 26-50 of 51 matching records','Page 2 of 3','search=A%26B','module=Legacy+Ops','start_date=2026-01-01','end_date=2026-01-02','page_size=25'):self.assertIn(value,html)
        self.assertIn('no-store',response.headers['Cache-Control']);self.assertEqual(response.headers['Referrer-Policy'],'no-referrer')
        self.writer.assert_not_called()

    def test_validation_does_not_silently_show_unfiltered_data(self):
        repo=importlib.import_module('audit_log_repository')
        self.read.side_effect=repo.get_audit_log_page
        for url in ('?start_date=invalid','?start_date=2026-02-01&end_date=2026-01-01','?page_size=500','?module=a&module=b','?date_from=2026-01-01'):
            response=self.client.get('/admin/audit-logs'+url)
            self.assertEqual(response.status_code,400)
            html=response.get_data(as_text=True)
            self.assertIn('Audit logs were not loaded.',html);self.assertNotIn('Showing 0',html)
            self.assertIn('no-store',response.headers['Cache-Control'])
        self.writer.assert_not_called()

    def test_unknown_filter_and_empty_database_states(self):
        self.page.update(total=0,pages=1,first=0,last=0)
        self.page['filters']=filter_values({'module':'UNKNOWN'})
        self.assertIn('No audit log records match these filters.',self.client.get('/admin/audit-logs').get_data(as_text=True))
        self.page['filters']=filter_values({})
        self.assertIn('No audit log records found.',self.client.get('/admin/audit-logs').get_data(as_text=True))
        self.writer.assert_not_called()

    def test_html_is_escaped_in_historical_descriptions_and_filters(self):
        self.page['records']=[dict(audit_log_id=1,username='<user>',module='Legacy Ops',action='READ',entity_type='TEST',entity_id='<target>',description='<img src=x onerror=alert(1)>',created_at='2026-01-01')]
        html=self.client.get('/admin/audit-logs').get_data(as_text=True)
        self.assertIn('&lt;img src=x',html);self.assertNotIn('<img src=x',html);self.assertIn('&lt;user&gt;',html)

    def test_read_outage_is_generic_503(self):
        self.read.side_effect=AuditLogError('Audit Logs are temporarily unavailable.',503)
        response=self.client.get('/admin/audit-logs')
        self.assertEqual(response.status_code,503);self.assertNotIn('Showing 0',response.get_data(as_text=True));self.writer.assert_not_called()

    def test_permission_denial_and_revocation_precede_read(self):
        self.state['permissions']=frozenset(['users.manage'])
        self.assertTrue(self.client.get('/admin/audit-logs').location.endswith('/dashboard'))
        self.state['is_active']=False
        self.assertTrue(self.client.get('/admin/audit-logs').location.endswith('/login'))
        self.read.assert_not_called();self.writer.assert_not_called()

    def test_read_route_has_no_mutation_methods(self):
        for method in ('POST','PUT','PATCH','DELETE'):
            response=self.client.open('/admin/audit-logs',method=method)
            self.assertEqual(response.status_code,405)
        self.read.assert_not_called();self.writer.assert_not_called()

    def test_schema_outage_and_anonymous_access(self):
        self.assertTrue(self.erp.app.test_client().get('/admin/audit-logs').location.endswith('/login'))
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('PRIVATE diagnostic')):
            response=self.client.get('/admin/audit-logs')
        self.assertEqual(response.status_code,503);self.assertNotIn('PRIVATE',response.get_data(as_text=True))
        self.read.assert_not_called();self.writer.assert_not_called()
