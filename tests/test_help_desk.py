"""Help Desk input, transaction, HTTP authorization and audit guarantees."""
from contextlib import ExitStack
import ast
import importlib
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from mysql.connector import Error
from werkzeug.datastructures import MultiDict
from help_desk_validation import HelpDeskError, CREATE_FIELDS, create_values, identifier, resolution_value, listing_values, unique_values
from security_helpers import csrf_client, stamp_session, user_state

FORM=dict(employee_id='1',category_id='1',subject='Synthetic subject',description='PRIVATE <script>description</script>',priority='HIGH')


class HelpDeskValidationTests(unittest.TestCase):
    def test_id_boundaries(self):
        for value in (0,-1,True,None,'1e2','1.0','2147483648','\uff11','9'*100):
            with self.subTest(value=value),self.assertRaises(HelpDeskError):identifier(value)
        self.assertEqual(identifier(' 001 '),1)

    def test_subject_and_priority(self):
        self.assertEqual(len(create_values(dict(FORM,subject='x'*150))['subject']),150)
        for values in (dict(FORM,subject=''),dict(FORM,subject='x'*151),dict(FORM,priority='OTHER'),dict(FORM,priority=None)):
            with self.assertRaises(HelpDeskError):create_values(values)
        self.assertEqual(create_values(dict(FORM,priority=' low '))['priority'],'LOW')

    def test_text_byte_limits_and_unicode(self):
        self.assertEqual(len(resolution_value('x'*65535)),65535)
        self.assertEqual(len(resolution_value('\U0001f642'*16383)),16383)
        for bad in ('x'*65536,'\U0001f642'*16384,'\ud800','bad\x00','',False,0):
            with self.subTest(bad_type=type(bad)),self.assertRaises(HelpDeskError):resolution_value(bad)
        with self.assertRaises(HelpDeskError):create_values(dict(FORM,description='\U0001f642'*16384))

    def test_duplicate_fields(self):
        for key in CREATE_FIELDS:
            data=MultiDict(FORM);data.add(key,FORM[key])
            with self.assertRaises(HelpDeskError):unique_values(data,CREATE_FIELDS)

    def test_filters_bounded_and_unassigned(self):
        for values in ({'page':'0'},{'page_size':'26'},{'category_id':'-1'},{'assigned_to':'1e2'},
                       {'status':'UNKNOWN'},{'priority':'OTHER'},{'search':'x'*101}):
            with self.assertRaises(HelpDeskError):listing_values(values)
        with self.assertRaises(HelpDeskError):listing_values(MultiDict([('page','1'),('page','2')]))
        self.assertEqual(listing_values(dict(assigned_to='unassigned'))['assigned_to'],'unassigned')
        for size in (25,50,100):self.assertEqual(listing_values({'page_size':str(size)})['page_size'],size)

    def test_one_effective_filter_and_history_implementation(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'help_desk_repository.py').read_text())
        for name in ('get_filtered_helpdesk_tickets','get_helpdesk_ticket_history'):
            self.assertEqual(sum(isinstance(n,ast.FunctionDef) and n.name==name for n in tree.body),1)


class HelpDeskRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        self.stack.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        self.repo=importlib.import_module('help_desk_repository')
        self.db=MagicMock();self.cur=self.db.cursor.return_value
        self.factory=self.stack.enter_context(patch.object(self.repo,'get_connection',return_value=self.db))
        self.stack.enter_context(patch.object(self.repo,'_check_storage'))

    def test_invalid_before_connection(self):
        with self.assertRaises(HelpDeskError):self.repo.create_helpdesk_ticket(**dict(FORM,employee_id=0),department_id=None,created_by=1)
        with self.assertRaises(HelpDeskError):self.repo.resolve_helpdesk_ticket(1,'',1)
        with self.assertRaises(HelpDeskError):self.repo.assign_helpdesk_ticket(1,False,1)
        self.factory.assert_not_called()

    def test_create_derives_department_and_commits_history(self):
        self.cur.fetchone.side_effect=[{'department_id':9},{'department_id':9},{'is_active':1}]
        self.cur.lastrowid=41
        self.assertEqual(self.repo.create_helpdesk_ticket(**FORM,department_id=None,created_by=7),(41,'HD-000041'))
        queries=[c.args for c in self.cur.execute.call_args_list]
        insert=next(params for sql,params in queries if sql.startswith('INSERT INTO helpdesk_tickets'))
        self.assertEqual(insert[2],9)
        self.assertEqual(queries[-1][1],(41,'CREATED',None,'OPEN','Ticket created',7))
        self.db.commit.assert_called_once();self.db.start_transaction.assert_called_once()

    def test_missing_inactive_and_stale_references(self):
        for rows,department in (([None],None),([{'department_id':None},None],None),([{'department_id':None},{'is_active':0}],None),([{'department_id':9}],8)):
            self.cur.fetchone.side_effect=rows
            with self.assertRaises(HelpDeskError):self.repo.create_helpdesk_ticket(**FORM,department_id=department,created_by=1)
        self.db.commit.assert_not_called()

    def test_assignment_rechecks_role_and_noop(self):
        self.cur.fetchone.side_effect=[{'user_id':5,'role_id':1,'is_active':1},{'role_name':'IT Manager'},{'status':'OPEN','assigned_to':5}]
        self.assertFalse(self.repo.assign_helpdesk_ticket(41,5,7))
        self.assertFalse(any('UPDATE helpdesk_tickets' in c.args[0] for c in self.cur.execute.call_args_list))
        self.assertFalse(any('INSERT' in c.args[0] for c in self.cur.execute.call_args_list))
        self.db.commit.assert_called_once()
        for user,role in ((None,None),({'is_active':0},None),({'is_active':1,'role_id':1},{'role_name':'Viewer'})):
            self.cur.fetchone.side_effect=[user,role]
            with self.assertRaises(HelpDeskError):self.repo.assign_helpdesk_ticket(41,5,7)

    def test_atomic_transition_and_resolution_history_prefix(self):
        self.cur.fetchone.return_value={'status':'IN_PROGRESS','assigned_to':5}
        self.assertTrue(self.repo.resolve_helpdesk_ticket(41,'R'*500,7))
        history=self.cur.execute.call_args.args[1]
        self.assertEqual(history,(41,'RESOLVED','IN_PROGRESS','RESOLVED','R'*255,7))
        self.db.commit.assert_called_once()

    def test_missing_ticket_invalid_status_and_unassigned_start(self):
        for row,code in ((None,404),({'status':'CLOSED','assigned_to':5},409),({'status':'OPEN','assigned_to':None},409)):
            self.cur.fetchone.return_value=row
            with self.assertRaises(HelpDeskError) as raised:self.repo.start_helpdesk_ticket(41,7)
            self.assertEqual(raised.exception.status_code,code)
        self.db.commit.assert_not_called()

    def test_sql_errors_and_uncertain_commit(self):
        self.cur.fetchone.return_value={'status':'RESOLVED','assigned_to':5}
        for errno,code in ((1062,409),(1452,409),(1205,409),(1213,409),(2013,503)):
            self.db.commit.side_effect=Error('PRIVATE raw SQL',errno=errno)
            with self.assertRaises(HelpDeskError) as raised:self.repo.close_helpdesk_ticket(41,7)
            self.assertEqual(raised.exception.status_code,code);self.assertNotIn('PRIVATE',str(raised.exception))
        self.assertEqual(self.db.rollback.call_count,5)

    def test_history_failure_rolls_back_business_change(self):
        self.cur.fetchone.return_value={'status':'OPEN','assigned_to':5}
        def execute(sql,params):
            if sql.startswith('INSERT INTO helpdesk_ticket_history'):raise Error('synthetic history failure',errno=1644)
        self.cur.execute.side_effect=execute
        with self.assertRaises(HelpDeskError):self.repo.start_helpdesk_ticket(41,7)
        self.db.commit.assert_not_called();self.db.rollback.assert_called_once()

    def test_cleanup_failure_after_commit_is_uncertain(self):
        self.cur.fetchone.return_value={'status':'RESOLVED','assigned_to':5}
        self.cur.close.side_effect=Error('close failed',errno=2013)
        self.db.close.side_effect=Error('close failed',errno=2013)
        with self.assertRaises(HelpDeskError) as raised:self.repo.close_helpdesk_ticket(41,7)
        self.assertEqual(raised.exception.status_code,503);self.db.commit.assert_called_once()

    def test_snapshot_bound_search_counts_and_stable_order(self):
        self.cur.fetchone.return_value=dict(total_tickets=51,open_count=51,in_progress_count=0,resolved_count=0,closed_count=0,cancelled_count=0)
        self.cur.fetchall.return_value=[]
        page=self.repo.get_helpdesk_ticket_page(dict(search='%_!',page='999',assigned_to='unassigned'))
        self.assertEqual((page['page'],page['pages'],page['summary']['total_tickets']),(3,3,51))
        sql,params=self.cur.execute.call_args.args
        self.assertIn('t.assigned_to IS NULL',sql);self.assertIn('t.created_at DESC,t.ticket_id DESC LIMIT',sql)
        self.assertEqual(params[0],'%!%!_!!%');self.assertEqual(params[-2:],(25,50))
        self.db.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        self.db.commit.assert_not_called()


class HelpDeskRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='synthetic-helpdesk-unit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch('database.ensure_ready'))
        self.state=user_state(permissions=['helpdesk.view','helpdesk.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        for name,result in (('get_all_employees',[dict(employee_id=1,employee_number='SYN',first_name='Test',last_name='Employee')]),
            ('get_active_helpdesk_categories',[dict(category_id=1,category_name='Synthetic')]),('get_all_helpdesk_categories',[dict(category_id=1,category_name='Synthetic',is_active=1)]),
            ('get_helpdesk_assignable_users',[dict(user_id=5,username='tech',role_name='IT Manager')]),('get_helpdesk_filter_users',[]),('get_helpdesk_ticket_history',[])):
            self.stack.enter_context(patch.object(self.erp,name,return_value=result))
        self.ticket=dict(ticket_id=41,ticket_number='HD-000041',assigned_to=5,status='IN_PROGRESS',description=FORM['description'],subject=FORM['subject'],priority='HIGH')
        self.read=self.stack.enter_context(patch.object(self.erp,'get_helpdesk_ticket_by_id',return_value=self.ticket))
        self.operations={}
        for name in ('create_helpdesk_ticket','assign_helpdesk_ticket','start_helpdesk_ticket','resolve_helpdesk_ticket','close_helpdesk_ticket'):
            self.operations[name]=self.stack.enter_context(patch.object(self.erp,name,return_value=(41,'HD-000041') if name=='create_helpdesk_ticket' else True))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as session:stamp_session(self.erp.app,session,self.state)

    def test_all_success_events_after_repository_return_without_private_data(self):
        cases=[('/it/help-desk/add',FORM,'create_helpdesk_ticket','CREATE'),('/it/help-desk/41/assign',{'assigned_to':'5'},'assign_helpdesk_ticket','ASSIGN'),
            ('/it/help-desk/41/start',{},'start_helpdesk_ticket','START'),('/it/help-desk/41/resolve',{'resolution':'PRIVATE fix'},'resolve_helpdesk_ticket','RESOLVE'),('/it/help-desk/41/close',{},'close_helpdesk_ticket','CLOSE')]
        for path,data,name,action in cases:
            with self.subTest(action=action):
                order=[];result=(41,'HD-000041') if action=='CREATE' else True
                self.operations[name].side_effect=lambda *a,**kw:order.append('commit') or result
                self.audit.reset_mock();self.audit.side_effect=lambda **kw:order.append('audit')
                self.assertEqual(self.client.post(path,data=data).status_code,302)
                self.assertEqual(order,['commit','audit']);self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                self.assertEqual((event['module'],event['action'],event['entity_id']),('HELP_DESK',action,41))
                self.assertNotIn('PRIVATE',event['description']);self.assertNotIn('subject',event['description'])

    def test_create_validation_retains_escaped_fields_and_unavailable_ids(self):
        response=self.client.post('/it/help-desk/add',data=dict(FORM,subject='X'*151,employee_id='999'))
        self.assertEqual(response.status_code,400);html=response.get_data(as_text=True)
        self.assertIn('PRIVATE &lt;script&gt;description&lt;/script&gt;',html);self.assertIn('value="999" selected',html)
        self.operations['create_helpdesk_ticket'].assert_not_called();self.audit.assert_not_called()

    def test_assignment_and_resolution_errors_retain_values(self):
        self.operations['assign_helpdesk_ticket'].side_effect=HelpDeskError('Invalid technician',400)
        response=self.client.post('/it/help-desk/41/assign',data={'assigned_to':'999'})
        self.assertEqual(response.status_code,400);self.assertIn('value="999" selected',response.get_data(as_text=True))
        self.operations['resolve_helpdesk_ticket'].side_effect=HelpDeskError('Uncertain save',503)
        response=self.client.post('/it/help-desk/41/resolve',data={'resolution':'PRIVATE <fix>'})
        self.assertEqual(response.status_code,503);self.assertIn('PRIVATE &lt;fix&gt;',response.get_data(as_text=True));self.audit.assert_not_called()

    def test_duplicate_fields_do_not_write(self):
        for path,data,field in (('/it/help-desk/add',FORM,'employee_id'),('/it/help-desk/41/assign',{'assigned_to':'5'},'assigned_to'),('/it/help-desk/41/resolve',{'resolution':'Fix'},'resolution')):
            form=MultiDict(data);form.add(field,form[field])
            self.assertEqual(self.client.post(path,data=form).status_code,400)
        for operation in self.operations.values():operation.assert_not_called()
        self.audit.assert_not_called()

    def test_noop_assignment_emits_no_success_audit(self):
        self.operations['assign_helpdesk_ticket'].return_value=False
        self.assertEqual(self.client.post('/it/help-desk/41/assign',data={'assigned_to':'5'}).status_code,302)
        self.audit.assert_not_called()

    def test_audit_failure_cannot_reverse_committed_change(self):
        self.audit.side_effect=RuntimeError('audit unavailable')
        with patch.object(self.erp.app.logger,'exception'):
            self.assertEqual(self.client.post('/it/help-desk/41/close').status_code,302)
        self.operations['close_helpdesk_ticket'].assert_called_once()

    def test_all_failed_writes_emit_no_success_audit(self):
        cases=[('/it/help-desk/add',FORM,'create_helpdesk_ticket'),
               ('/it/help-desk/41/assign',{'assigned_to':'5'},'assign_helpdesk_ticket'),
               ('/it/help-desk/41/start',{},'start_helpdesk_ticket'),
               ('/it/help-desk/41/resolve',{'resolution':'PRIVATE fix'},'resolve_helpdesk_ticket'),
               ('/it/help-desk/41/close',{},'close_helpdesk_ticket')]
        for path,form,name in cases:
            self.operations[name].side_effect=HelpDeskError('Could not confirm the save.',503)
            self.assertEqual(self.client.post(path,data=form).status_code,503)
            self.audit.assert_not_called()

    def test_manage_only_errors_do_not_disclose_ticket_or_history(self):
        self.state['permissions']=frozenset(['helpdesk.manage'])
        self.operations['start_helpdesk_ticket'].side_effect=HelpDeskError('Conflict',409)
        response=self.client.post('/it/help-desk/41/start')
        self.assertEqual(response.status_code,409);self.assertNotIn('PRIVATE',response.get_data(as_text=True));self.read.assert_not_called()

    def test_missing_history_during_error_rendering_remains_safe_503(self):
        self.operations['start_helpdesk_ticket'].side_effect=HelpDeskError('Unavailable',503)
        with patch.object(self.erp,'get_helpdesk_ticket_history',side_effect=Error('PRIVATE missing table',errno=1146)):
            for response in (self.client.post('/it/help-desk/41/start'),self.client.get('/it/help-desk/41')):
                self.assertEqual(response.status_code,503)
                self.assertNotIn('PRIVATE',response.get_data(as_text=True))
        self.audit.assert_not_called()

    def test_security_gate_csrf_viewer_and_revocation(self):
        self.assertEqual(self.client.post('/it/help-desk/add',data=FORM,headers={'X-CSRFToken':'invalid'}).status_code,400)
        self.state['permissions']=frozenset(['helpdesk.view'])
        self.assertTrue(self.client.post('/it/help-desk/add',data=FORM).location.endswith('/dashboard'))
        self.state['is_active']=False
        self.assertTrue(self.client.post('/it/help-desk/41/start').location.endswith('/login'))
        import database
        with patch('database.ensure_ready',side_effect=database.SchemaUnavailable('private')):
            self.assertEqual(self.client.post('/it/help-desk/41/start').status_code,503)
        for operation in self.operations.values():operation.assert_not_called()
        self.audit.assert_not_called()

    def test_missing_oversized_ids_and_no_get_mutation(self):
        for number in (0,2147483648):
            self.assertEqual(self.client.get(f'/it/help-desk/{number}').status_code,404)
            for action in ('assign','start','resolve','close'):
                self.assertEqual(self.client.post(f'/it/help-desk/{number}/{action}').status_code,404)
        self.assertEqual(self.client.get('/it/help-desk/41/start').status_code,405)

    def test_filtered_listing_counts_and_retained_links(self):
        summary=dict(total_tickets=51,open_count=51,in_progress_count=0,resolved_count=0,closed_count=0,cancelled_count=0)
        with patch.object(self.erp,'get_helpdesk_ticket_page',return_value=dict(records=[],summary=summary,page=2,pages=3)):
            response=self.client.get('/it/help-desk?search=A%26B&status=OPEN&priority=HIGH&category_id=1&assigned_to=5&page=2&page_size=25')
        self.assertEqual(response.status_code,200);html=response.get_data(as_text=True)
        for value in ('51 tickets','Page 2 of 3','search=A%26B','assigned_to=5','priority=HIGH'):self.assertIn(value,html)
        self.assertEqual(self.client.get('/it/help-desk?page_size=26').status_code,400)
