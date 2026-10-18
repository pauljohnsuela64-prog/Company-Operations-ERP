"""IT business-action audit boundaries; configured databases are forbidden."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch

from security_helpers import csrf_client, stamp_session, user_state


def cases():
    asset=dict(asset_tag='new-tag',asset_name='Private name',category_id='3',department_id='3',
               assigned_employee_id='1',purchase_cost='123456.78',condition_status='GOOD',notes='private notes')
    category=dict(category_code='CAT',category_name='Private category',description='private description')
    maintenance=dict(maintenance_type='Repair',description='private repair',vendor='private vendor',cost='123456.78',start_date='2026-10-01',notes='private notes')
    return [
        ('/it/assets/add',asset,'create_it_asset',41,'CREATE','IT_ASSET',41,'NEW-TAG'),
        ('/it/assets/41/edit',asset,'update_it_asset',True,'UPDATE','IT_ASSET',41,'NEW-TAG'),
        ('/it/assets/41/assign',dict(employee_id='1'),'assign_it_asset',True,'ASSIGN','IT_ASSET',41,'IT-41'),
        ('/it/assets/41/unassign',dict(assignment_id='12'),'unassign_it_asset',True,'RETURN','IT_ASSET',41,'IT-41'),
        ('/it/assets/41/lost',{},'mark_it_asset_lost',True,'MARK_LOST','IT_ASSET',41,'IT-41'),
        ('/it/assets/41/restore',{},'restore_it_asset','LOST','RECOVER','IT_ASSET',41,'IT-41'),
        ('/it/assets/41/retire',{},'retire_it_asset',True,'RETIRE','IT_ASSET',41,'IT-41'),
        ('/it/assets/41/restore',{},'restore_it_asset','RETIRED','RESTORE','IT_ASSET',41,'IT-41'),
        ('/it/assets/categories/add',category,'create_it_asset_category',3,'CREATE','IT_ASSET_CATEGORY',3,'CAT'),
        ('/it/assets/categories/3/edit',category,'update_it_asset_category',True,'UPDATE','IT_ASSET_CATEGORY',3,'CAT'),
        ('/it/assets/categories/3/status',{},'set_it_asset_category_active_status',True,'DEACTIVATE','IT_ASSET_CATEGORY',3,'CAT'),
        ('/it/assets/categories/3/status',{},'set_it_asset_category_active_status',True,'ACTIVATE','IT_ASSET_CATEGORY',3,'CAT'),
        ('/it/assets/41/maintenance/add',maintenance,'create_it_asset_maintenance',77,'CREATE','IT_ASSET_MAINTENANCE',77,'IT-41'),
        ('/it/assets/maintenance/77/complete',dict(completed_date='2026-10-02'),'complete_it_asset_maintenance',41,'COMPLETE','IT_ASSET_MAINTENANCE',77,'IT-41'),
    ]


class AssetAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-it-audit',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.state=user_state(permissions=['it_assets.view','it_assets.manage'])
        self.mock('get_authorization_state',side_effect=lambda _:self.state)
        self.mock('render_template',return_value='form')
        self.mock('get_it_asset_by_id',return_value=dict(asset_id=41,asset_tag='IT-41',category_id=3,department_id=3))
        self.category=dict(category_id=3,category_code='CAT',is_active=True)
        self.mock('get_it_asset_category_by_id',return_value=self.category)
        self.mock('get_employee_by_id',return_value=dict(employee_id=1,department_id=3))
        self.mock('get_all_employees',return_value=[dict(employee_id=1)])
        self.mock('get_active_departments',return_value=[dict(department_id=3)])
        self.mock('get_active_it_asset_categories',return_value=[self.category])
        self.mock_logger=self.stack.enter_context(patch.object(self.erp.app.logger,'exception'))
        self.audit=self.mock('create_audit_log')
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)

    def mock(self,name,**kwargs):return self.stack.enter_context(patch.object(self.erp,name,**kwargs))

    def test_all_events_actor_numeric_entity_and_minimal_readable_description(self):
        for path,fields,operation,result,action,entity,eid,label in cases():
            with self.subTest(action=action,entity=entity),patch.object(self.erp,operation,return_value=result) as write:
                self.category['is_active']=action!='ACTIVATE'
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=fields).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()
                event=self.audit.call_args.kwargs
                for key,value in dict(user_id=7,username='acting.user',module='IT_ASSETS',action=action,entity_type=entity,entity_id=eid).items():
                    self.assertEqual(event[key],value)
                self.assertIn(label,event['description'])
                for private in ['Private name','Private category','private notes','private description','private repair','private vendor','123456.78']:
                    self.assertNotIn(private,str(event))

    def test_rejected_or_rolled_back_operations_never_audit(self):
        for error in [ValueError('Rejected transition'),RuntimeError('Commit failed')]:
            for path,fields,operation,*_ in cases():
                with self.subTest(path=path,error=type(error).__name__),patch.object(self.erp,operation,side_effect=error):
                    self.audit.reset_mock()
                    try:self.client.post(path,data=fields)
                    except (ValueError,RuntimeError):pass
                    self.audit.assert_not_called()

    def test_false_write_results_and_unchanged_updates_never_audit(self):
        for path,fields,operation,*_ in cases():
            with self.subTest(path=path),patch.object(self.erp,operation,return_value=False):
                self.audit.reset_mock()
                self.client.post(path,data=fields)
                self.audit.assert_not_called()

    def test_audit_storage_failure_isolated_after_each_success(self):
        self.audit.side_effect=RuntimeError('Audit offline')
        for path,fields,operation,result,action,*_ in cases():
            with self.subTest(path=path,action=action),patch.object(self.erp,operation,return_value=result) as write:
                self.category['is_active']=action!='ACTIVATE'
                self.audit.reset_mock()
                self.assertEqual(self.client.post(path,data=fields).status_code,302)
                write.assert_called_once();self.audit.assert_called_once()
        self.assertTrue(self.mock_logger.called)

    def test_readable_lookup_failure_retains_numeric_identity_and_event(self):
        with patch.object(self.erp,'assign_it_asset',return_value=True),patch.object(self.erp,'get_it_asset_by_id',side_effect=RuntimeError('Lookup offline')):
            self.assertEqual(self.client.post('/it/assets/41/assign',data={'employee_id':'1'}).status_code,302)
        self.assertEqual(self.audit.call_args.kwargs['entity_id'],41)
        self.assertEqual(self.audit.call_args.kwargs['action'],'ASSIGN')

    def test_recovery_classification_uses_committed_result_not_later_state(self):
        with patch.object(self.erp,'restore_it_asset',return_value='LOST'),patch.object(
                self.erp,'get_it_asset_by_id',return_value=dict(asset_tag='IT-41',status='RETIRED')):
            self.assertEqual(self.client.post('/it/assets/41/restore').status_code,302)
        self.assertEqual(self.audit.call_args.kwargs['action'],'RECOVER')

    def test_permission_revocation_disabled_user_and_csrf_never_reach_writes(self):
        raw=self.erp.app.test_client()
        with raw.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)
        self.assertEqual(raw.post('/it/assets/41/lost').status_code,400)
        self.state['permissions']=frozenset(['it_assets.view'])
        for path,fields,*_ in cases():
            self.assertTrue(self.client.post(path,data=fields).location.endswith('/dashboard'))
        self.state['is_active']=False
        self.assertTrue(self.client.post('/it/assets/41/lost').location.endswith('/login'))
        self.audit.assert_not_called()

    def test_form_gets_never_emit_business_events(self):
        for path in ['/it/assets/add','/it/assets/41/edit','/it/assets/categories/add',
                     '/it/assets/categories/3/edit','/it/assets/41/maintenance/add']:
            self.assertEqual(self.client.get(path).status_code,200)
        self.audit.assert_not_called()


if __name__=='__main__':unittest.main()
