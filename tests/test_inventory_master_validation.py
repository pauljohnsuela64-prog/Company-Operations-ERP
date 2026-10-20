"""Inventory master boundaries and route validation, without company DB access."""
from contextlib import ExitStack
from decimal import Decimal
import importlib
import unittest
from unittest.mock import patch, MagicMock
import inventory_category_repository as categories
import warehouse_repository as warehouses
import inventory_item_repository as items
from inventory_validation import category_fields, warehouse_fields, item_fields, lock_assignment_category
from security_helpers import csrf_client, stamp_session, user_state


class InventoryMasterValidationTests(unittest.TestCase):
    def cases(self):
        return [(categories,categories.create_inventory_category,categories.update_inventory_category,['C','Category',None],[30,100,255]),
                (warehouses,warehouses.create_warehouse,warehouses.update_warehouse,['W','Warehouse',None],[30,100,255]),
                (items,items.create_inventory_item,items.update_inventory_item,['I','Item',None,None,'pcs','0'],[50,150,None,255,30,None])]

    def test_text_overflow_rejected_before_connection_for_create_and_edit(self):
        for module,create,update,valid,limits in self.cases():
            for index,limit in enumerate(limits):
                if limit is None:continue
                values=list(valid);values[index]='x'*(limit+1)
                for action,args in ((create,values),(update,[1]+values)):
                    with self.subTest(action=action.__name__,field=index),patch.object(module,'get_connection') as connect:
                        with self.assertRaisesRegex(ValueError,str(limit)+' characters'):action(*args)
                        connect.assert_not_called()

    def test_required_fields_and_normalized_boundaries(self):
        self.assertEqual(category_fields(' c ',' n ',' '),('C','n',None))
        self.assertEqual(warehouse_fields('w'*30,'n'*100,'l'*255),('W'*30,'n'*100,'l'*255))
        self.assertEqual(item_fields('i'*50,'n'*150,None,'d'*255,'u'*30,'9999999999.99')[-1],Decimal('9999999999.99'))
        for module,create,update,valid,_ in self.cases():
            required=(0,1,4) if module is items else (0,1)
            for index in required:
                for value in (None,'','   '):
                    values=list(valid);values[index]=value
                    with patch.object(module,'get_connection') as connect:
                        with self.assertRaisesRegex(ValueError,'required'):create(*values)
                        with self.assertRaisesRegex(ValueError,'required'):update(1,*values)
                        connect.assert_not_called()

    def test_invalid_reorder_and_category_ids_never_open_connection(self):
        for index,values in ((5,('NaN','sNaN','Infinity','-Infinity','-0.01','0.001','10000000000','1e9999','bad',None)),
                             (2,('bad','1.5','-1',0,True,1.5,'2147483648'))):
            for value in values:
                args=['I','Item',None,None,'pcs','0'];args[index]=value
                with patch.object(items,'get_connection') as connect:
                    with self.assertRaises(ValueError):items.create_inventory_item(*args)
                    with self.assertRaises(ValueError):items.update_inventory_item(1,*args)
                    connect.assert_not_called()

    def test_category_lock_accepts_existing_inactive_but_not_new_assignment(self):
        cursor=MagicMock()
        cursor.fetchone.return_value=(False,)
        with self.assertRaisesRegex(ValueError,'new assignments'):lock_assignment_category(cursor,2)
        lock_assignment_category(cursor,2,existing_category=2)
        self.assertIn('FOR SHARE',cursor.execute.call_args.args[0])
        cursor.fetchone.return_value=None
        with self.assertRaisesRegex(ValueError,'does not exist'):lock_assignment_category(cursor,2)

    def test_item_assignment_failure_rolls_back_and_never_updates(self):
        connection=MagicMock();cursor=connection.cursor.return_value
        cursor.fetchone.side_effect=[(1,),(False,)]
        with patch.object(items,'get_connection',return_value=connection):
            with self.assertRaisesRegex(ValueError,'new assignments'):
                items.update_inventory_item(7,'I','Item',2,None,'pcs','0')
        connection.start_transaction.assert_called_once();connection.rollback.assert_called_once();connection.commit.assert_not_called()
        self.assertFalse(any(call.args[0].lstrip().startswith('UPDATE') for call in cursor.execute.call_args_list))


class InventoryMasterRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard=ExitStack();cls.addClassCleanup(cls.guard.close)
        cls.guard.enter_context(patch('dotenv.load_dotenv',return_value=False))
        cls.guard.enter_context(patch.dict('os.environ',SECRET_KEY='master-tests-only',ERP_ENV='testing',ERP_DEBUG='false'))
        cls.guard.enter_context(patch('mysql.connector.connect',side_effect=AssertionError('Company DB forbidden')))
        cls.erp=importlib.import_module('app')

    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(self.erp.app.config,TESTING=True))
        self.stack.enter_context(patch("database.ensure_ready"))  # Route unit test: schema integration tested separately.
        self.state=user_state(permissions=['inventory.view','inventory.categories.manage','inventory.warehouses.manage','inventory.items.manage'])
        self.stack.enter_context(patch.object(self.erp,'get_authorization_state',side_effect=lambda _:self.state))
        self.audit=self.stack.enter_context(patch.object(self.erp,'create_audit_log'))
        for name,value in [('get_inventory_category_by_id',dict(category_id=1,category_code='C',category_name='Category',description=None)),('get_warehouse_by_id',dict(warehouse_id=1,warehouse_code='W',warehouse_name='Warehouse',location=None)),('get_inventory_item_by_id',dict(item_id=1,item_code='I',item_name='Item',category_id=None,description=None,unit_of_measure='pcs',reorder_level=Decimal('0'))),('get_active_inventory_categories',[]),('get_all_inventory_categories',[])]:
            self.stack.enter_context(patch.object(self.erp,name,return_value=value))
        self.client=csrf_client(self.erp.app)
        with self.client.session_transaction() as mapping:stamp_session(self.erp.app,mapping,self.state)

    def test_actual_validation_messages_and_csrf_fields_for_add_and_edit(self):
        cases=[('categories',dict(category_code='C',category_name='Category',description='x'*256),'255 characters'),
               ('warehouses',dict(warehouse_code='W',warehouse_name='Warehouse',location='x'*256),'255 characters'),
               ('items',dict(item_code='I',item_name='Item',unit_of_measure='pcs',reorder_level='NaN'),'finite'),
               ('items',dict(item_code='I',item_name='Item',unit_of_measure='pcs',reorder_level='0',category_id='bad'),'valid inventory category')]
        for section,data,error in cases:
            for suffix in ('add','1/edit'):
                response=self.client.post(f'/inventory/{section}/{suffix}',data=data)
                self.assertEqual(response.status_code,400 if section=='warehouses' else 200);html=response.get_data(as_text=True)
                self.assertIn(error,html);self.assertIn('name="csrf_token"',html)
        self.audit.assert_not_called()

    def test_item_route_passes_decimal_and_permissions_are_enforced(self):
        data=dict(item_code='I',item_name='Item',unit_of_measure='pcs',reorder_level='0.10')
        with patch.object(self.erp,'create_inventory_item') as create:
            self.assertEqual(self.client.post('/inventory/items/add',data=data).status_code,302)
            self.assertIsInstance(create.call_args.args[-1],Decimal)
            self.assertEqual(create.call_args.args[-1],Decimal('0.10'))
            create.reset_mock();self.state['permissions']=frozenset()
            self.assertEqual(self.client.post('/inventory/items/add',data=data).status_code,302);create.assert_not_called()
