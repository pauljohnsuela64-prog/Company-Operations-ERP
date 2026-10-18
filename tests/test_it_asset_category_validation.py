"""Category boundaries and forged forms; company connections are forbidden."""
from contextlib import ExitStack
import importlib
import unittest
from unittest.mock import patch
import mysql.connector
from it_asset_validation import category_values
from security_helpers import csrf_client, stamp_session, user_state


class CategoryValidationTests(unittest.TestCase):
    def test_normalization_boundaries_optional_description_and_unicode_expansion(self):
        self.assertEqual(category_values(' code ',' Name ',' '),('CODE','Name',None))
        self.assertEqual(category_values('x'*30,'n'*100,'d'*255),('X'*30,'n'*100,'d'*255))
        for values in [('x'*31,'Name',None),('CODE','n'*101,None),('CODE','Name','d'*256),('', 'Name',None),('CODE',' ',None),(chr(223)*16,'Name',None)]:
            with self.subTest(values=values),self.assertRaises(ValueError):category_values(*values)

    def test_repositories_reject_before_connection(self):
        repo=importlib.import_module('it_asset_repository')
        with patch.object(repo,'get_connection',side_effect=AssertionError('DB must not be touched')) as connection:
            for values in [('X'*31,'Name',None),('CODE','n'*101,None),('CODE','Name','d'*256),('', 'Name',None),('CODE','',None)]:
                for operation,args in [(repo.create_it_asset_category,values),(repo.update_it_asset_category,(1,*values))]:
                    with self.subTest(operation=operation.__name__),self.assertRaises(ValueError):operation(*args)
            connection.assert_not_called()


class CategoryRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-category',ERP_ENV='testing'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.state=user_state(permissions=['it_assets.view','it_assets.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.category=dict(category_id=3,category_code='OLD',category_name='Old name',description='Old description')
        self.stack.enter_context(patch.object(self.erp,'get_it_asset_category_by_id',return_value=self.category))
        self.create=self.stack.enter_context(patch.object(self.erp,'create_it_asset_category',return_value=3))
        self.update=self.stack.enter_context(patch.object(self.erp,'update_it_asset_category',return_value=True))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        self.render=self.stack.enter_context(patch.object(self.erp,'render_template',return_value='form'))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)

    def test_invalid_and_missing_form_fields_retained_without_writes_or_audits(self):
        for path in ['/it/assets/categories/add','/it/assets/categories/3/edit']:
            for values in [dict(category_code='x'*31,category_name=' Name ',description='<retained>'),
                           dict(category_code='code',category_name='x'*101),dict(category_code='code',category_name='Name',description='x'*256),{},dict(category_code='CODE')]:
                with self.subTest(path=path,values=values):
                    self.assertEqual(self.client.post(path,data=values).status_code,200)
                    retained=self.render.call_args.kwargs['form_values']
                    self.assertEqual(retained,{k:values.get(k,'') for k in ['category_code','category_name','description']})
        self.create.assert_not_called();self.update.assert_not_called();self.audit.assert_not_called()

    def test_successful_forms_normalize_and_audit_once(self):
        for path,operation,action in [('/it/assets/categories/add',self.create,'CREATE'),('/it/assets/categories/3/edit',self.update,'UPDATE')]:
            self.audit.reset_mock()
            self.assertEqual(self.client.post(path,data=dict(category_code=' code ',category_name=' Name ',description=' ')).status_code,302)
            args=('CODE','Name',None)
            operation.assert_called_once_with(*((3,*args) if action=='UPDATE' else args))
            self.audit.assert_called_once()
            event=self.audit.call_args.kwargs
            self.assertEqual((event['action'],event['entity_id'],event['user_id']),(action,3,self.state['user_id']))

    def test_duplicate_code_retains_form_and_never_audits(self):
        self.create.side_effect=self.update.side_effect=mysql.connector.IntegrityError(errno=1062,msg='Duplicate')
        values=dict(category_code='CODE',category_name='Retained',description='Retained description')
        for path in ['/it/assets/categories/add','/it/assets/categories/3/edit']:
            self.assertEqual(self.client.post(path,data=values).status_code,200)
            self.assertEqual(self.render.call_args.kwargs['form_values'],values)
        self.audit.assert_not_called()

    def test_csrf_and_fresh_permission_enforcement(self):
        plain=self.erp.app.test_client()
        with plain.session_transaction() as sess:stamp_session(self.erp.app,sess,self.state)
        for path in ['/it/assets/categories/add','/it/assets/categories/3/edit']:
            self.assertEqual(plain.post(path,data={}).status_code,400)
        self.state['permissions']=['it_assets.view']
        for path in ['/it/assets/categories/add','/it/assets/categories/3/edit']:
            self.assertEqual(self.client.post(path,data={}).status_code,302)
        self.create.assert_not_called();self.update.assert_not_called();self.audit.assert_not_called()
