"""Inventory master-data regression on a verified disposable MySQL server only."""
from contextlib import ExitStack
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cursor=connection.cursor();cursor.execute('SELECT @@datadir')
        assert Path(cursor.fetchone()[0]).resolve()==data_dir.resolve()
        cursor.execute('CREATE DATABASE erp_inventory_master_test');cursor.execute('USE erp_inventory_master_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_inventory_master_test'
    local=threading.local()
    class Proxy:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            if getattr(local,'hold',None):
                entered,release=local.hold;entered.set();assert release.wait(10)
            return self.connection.commit()
        def __enter__(self):return self
        def __exit__(self,*args):self.connection.close()
    def connect():return Proxy(mysql.connector.connect(**options))
    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as connection:
            cur=connection.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            connection.commit();return result
    def snapshot():
        return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ('inventory_categories','warehouses','inventory_items','inventory_stock','stock_movements','audit_logs')]
    def rejected(action,exception=ValueError):
        before=snapshot()
        try:action()
        except exception:pass
        else:raise AssertionError('Invalid operation succeeded')
        assert snapshot()==before
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Inventory test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'inventory.test','synthetic')")
    sql("INSERT INTO inventory_categories(category_id,category_code,category_name,is_active) VALUES (1,'ACTIVE','Active',TRUE),(2,'OFF','Inactive',FALSE),(3,'RACE','Concurrent',TRUE)")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES (1,'W','Warehouse')")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name,category_id,unit_of_measure) VALUES (1,'ITEM','Item',1,'pcs'),(2,'OLD','Historical assignment',2,'pcs')")
    sql('INSERT INTO inventory_stock(item_id,warehouse_id,quantity) VALUES (1,1,1)')
    sql("INSERT INTO stock_movements(item_id,warehouse_id,movement_type,quantity,reference_type,created_by) VALUES (1,1,'IN',1,'SYNTHETIC_HISTORY',1)")
    historical=sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True)
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='inventory-master-mysql-only',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        modules=[importlib.import_module(name) for name in ('inventory_category_repository','warehouse_repository','inventory_item_repository')]
        for module in modules:stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        categories,warehouses,items=modules
        expected={'inventory_categories':{'category_code':30,'category_name':100,'description':255},'warehouses':{'warehouse_code':30,'warehouse_name':100,'location':255},'inventory_items':{'item_code':50,'item_name':150,'unit_of_measure':30,'description':255}}
        for table,columns in expected.items():
            for column,limit in columns.items():
                assert sql('SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s',(table,column),True)==[(limit,)]
        assert sql("SELECT NUMERIC_PRECISION,NUMERIC_SCALE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='inventory_items' AND column_name='reorder_level'",fetch=True)==[(12,2)]
        categories.create_inventory_category('c'*30,'n'*100,'d'*255)
        warehouses.create_warehouse('w'*30,'n'*100,'l'*255)
        items.create_inventory_item('i'*50,'n'*150,1,'d'*255,'u'*30,'9999999999.99')
        assert sql('SELECT reorder_level FROM inventory_items WHERE item_code=%s',('I'*50,),True)==[(Decimal('9999999999.99'),)]
        items.update_inventory_item(1,'ITEM','Item',1,None,'pcs','0.10')
        assert sql('SELECT reorder_level FROM inventory_items WHERE item_id=1',fetch=True)==[(Decimal('0.10'),)]
        for category in ('bad',0,-1,'1.5',99999,2):
            rejected(lambda:items.create_inventory_item('BAD','Bad',category,None,'pcs','0'))
            rejected(lambda:items.update_inventory_item(1,'ITEM','Item',category,None,'pcs','0'))
        # Preserve an existing inactive assignment, but do not let another item join it.
        items.update_inventory_item(2,'OLD','Historical assignment',2,'Updated description','pcs','0')
        assert sql('SELECT category_id FROM inventory_items WHERE item_id=2',fetch=True)==[(2,)]
        for value in ('NaN','Infinity','-1','0.001','10000000000','bad'):
            rejected(lambda:items.create_inventory_item('BAD','Bad',1,None,'pcs',value))
            rejected(lambda:items.update_inventory_item(1,'ITEM','Item',1,None,'pcs',value))
        for action in (lambda:categories.update_inventory_category(99999,'NONE','None'),lambda:warehouses.update_warehouse(99999,'NONE','None'),lambda:items.update_inventory_item(99999,'NONE','None',1,None,'pcs','0')):rejected(action)
        print('PASS actual schema boundaries, Decimal values, malformed/nonexistent/inactive assignments, historical inactive retention and missing-edit targets')
        # Category deactivation is serialized after an assignment that already holds its shared lock.
        entered,release,started=threading.Event(),threading.Event(),threading.Event()
        def held_assignment():
            local.hold=(entered,release)
            try:items.create_inventory_item('RACEITEM','Concurrent assignment',3,None,'pcs','0')
            finally:del local.hold
        def deactivate():
            started.set();categories.set_inventory_category_active_status(3,False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(held_assignment);assert entered.wait(5)
            second=pool.submit(deactivate);assert started.wait(5)
            try:
                try:second.result(timeout=0.3);raise AssertionError('Category deactivated through assignment lock')
                except TimeoutError:pass
            finally:release.set()
            first.result(timeout=10);second.result(timeout=10)
        rejected(lambda:items.create_inventory_item('TOOLATE','Inactive assignment',3,None,'pcs','0'))
        # Reject after deactivation wins, and preserve existing item on a late SQL failure.
        sql("CREATE TRIGGER item_update_failure BEFORE UPDATE ON inventory_items FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic failure'")
        try:rejected(lambda:items.update_inventory_item(1,'ITEM','Changed',1,None,'pcs','1'),mysql.connector.Error)
        finally:sql('DROP TRIGGER item_update_failure')
        print('PASS category activation locks, rejected post-deactivation assignment and transaction rollback')
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        for code in ('inventory.view','inventory.categories.manage','inventory.warehouses.manage','inventory.items.manage'):
            pid=sql('INSERT INTO permissions(permission_code) VALUES (%s)',(code,));sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(pid,))
        client=csrf_client(erp.app)
        with client.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        forms=[('categories',dict(category_code='NEW',category_name='New',description='Description'),{'category_code':30,'category_name':100,'description':255}),('warehouses',dict(warehouse_code='NEW',warehouse_name='New',location='Location'),{'warehouse_code':30,'warehouse_name':100,'location':255}),('items',dict(item_code='NEW',item_name='New',unit_of_measure='pcs',reorder_level='0',category_id='1',description='Description'),{'item_code':50,'item_name':150,'unit_of_measure':30,'description':255})]
        for section,valid,limits in forms:
            for suffix in ('add','1/edit'):
                path=f'/inventory/{section}/{suffix}'
                for field,limit in limits.items():
                    form=dict(valid,**{field:'x'*(limit+1)});before=snapshot()
                    response=client.post(path,data=form)
                    assert response.status_code==200 and str(limit) in response.get_data(as_text=True)
                    assert 'name="csrf_token"' in response.get_data(as_text=True) and snapshot()==before
                # Duplicate code, then duplicate name where the schema requires name uniqueness.
                fields={'items':['item_code'],'categories':['category_code','category_name'],
                        'warehouses':['warehouse_code','warehouse_name']}[section]
                for field in fields:
                    table='inventory_'+section if section in ('categories','items') else section
                    other=sql('SELECT '+field+' FROM '+table+' WHERE '+('item_id' if section=='items' else 'category_id' if section=='categories' else 'warehouse_id')+' <> 1 LIMIT 1',fetch=True)[0][0]
                    form=dict(valid,**{field:other});before=snapshot()
                    response=client.post(path,data=form)
                    assert response.status_code==200 and 'already exists' in response.get_data(as_text=True)
                    assert snapshot()==before
        for value in ('bad','1.5','99999','2'):
            for suffix in ('add','1/edit'):
                before=snapshot();form=dict(forms[-1][1],category_id=value)
                response=client.post('/inventory/items/'+suffix,data=form)
                assert response.status_code==200 and snapshot()==before
        def audit_count():return sql('SELECT COUNT(*) FROM audit_logs',fetch=True)[0][0]
        def check_event(before,action,entity,identifier,code):
            assert audit_count()==before+1
            row=sql('SELECT user_id,username,module,action,entity_type,entity_id,description FROM audit_logs ORDER BY audit_log_id DESC LIMIT 1',fetch=True)[0]
            assert row[:6]==(1,'inventory.test','INVENTORY',action,entity,str(identifier)),row
            assert code.upper() in row[6] and str(identifier) in row[6],row
            for private in ('Description','Location','private-'):assert private not in row[6]
        # Successful CRUD paths still preserve the same item/warehouse foreign keys.
        for section,valid,_ in forms:
            before_count=audit_count()
            assert client.post(f'/inventory/{section}/add',data=valid).status_code==302
            table={'categories':'inventory_categories','warehouses':'warehouses','items':'inventory_items'}[section]
            key={'categories':'category_id','warehouses':'warehouse_id','items':'item_id'}[section]
            entity={'categories':'INVENTORY_CATEGORY','warehouses':'WAREHOUSE','items':'INVENTORY_ITEM'}[section]
            identifier=sql(f'SELECT {key} FROM {table} WHERE '+{'categories':'category_code','warehouses':'warehouse_code','items':'item_code'}[section]+"='NEW'",fetch=True)[0][0]
            check_event(before_count,'CREATE',entity,identifier,'NEW')
            codefield={'categories':'category_code','warehouses':'warehouse_code','items':'item_code'}[section]
            namefield={'categories':'category_name','warehouses':'warehouse_name','items':'item_name'}[section]
            updated=dict(valid,**{codefield:'EDIT-'+section,namefield:'Edited '+section})
            before_count=audit_count()
            assert client.post(f'/inventory/{section}/1/edit',data=updated).status_code==302
            check_event(before_count,'UPDATE',entity,1,updated[codefield])
        html=client.get('/inventory/items/2/edit').get_data(as_text=True)
        assert 'value="2"' in html and '(Inactive)' in html
        html=client.get('/inventory/items/1/edit').get_data(as_text=True)
        assert '(Inactive)' not in html
        # Real route-level SQL failures must not create success events.
        for section,valid,_ in forms:
            table={'categories':'inventory_categories','warehouses':'warehouses','items':'inventory_items'}[section]
            codefield={'categories':'category_code','warehouses':'warehouse_code','items':'item_code'}[section]
            namefield={'categories':'category_name','warehouses':'warehouse_name','items':'item_name'}[section]
            form=dict(valid,**{codefield:'ROLLBACK-'+section,namefield:'Rollback '+section})
            sql(f"CREATE TRIGGER inventory_route_failure BEFORE UPDATE ON {table} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic rollback'")
            try:rejected(lambda:client.post(f'/inventory/{section}/1/edit',data=form),mysql.connector.Error)
            finally:sql('DROP TRIGGER inventory_route_failure')
        # Activation remains supported, without adding a stock-holding restriction.
        for section,entity in (('categories','INVENTORY_CATEGORY'),('warehouses','WAREHOUSE'),('items','INVENTORY_ITEM')):
            for action in ('DEACTIVATE','ACTIVATE'):
                before_count=audit_count()
                assert client.post(f'/inventory/{section}/1/status').status_code==302
                check_event(before_count,action,entity,1,'EDIT-'+section)
        # A real duplicate status write reports no change and cannot emit a success event.
        for section,kind,repo in (('categories','inventory_category',categories),('warehouses','warehouse',warehouses),('items','inventory_item',items)):
            saved=getattr(erp,'get_'+kind+'_by_id')(1)
            before_count=audit_count()
            assert getattr(repo,'set_'+kind+'_active_status')(1,False)
            with patch.object(erp,'get_'+kind+'_by_id',return_value=saved):
                assert client.post(f'/inventory/{section}/1/status').status_code==302
            assert audit_count()==before_count
            assert getattr(repo,'set_'+kind+'_active_status')(1,True)
        # Real SQL audit failure must not undo committed master-data changes.
        sql("CREATE TRIGGER inventory_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic audit failure'")
        before_count=audit_count()
        try:
            with patch.object(erp.app.logger,'exception'):
                for section,valid,_ in forms:
                    codefield={'categories':'category_code','warehouses':'warehouse_code','items':'item_code'}[section]
                    namefield={'categories':'category_name','warehouses':'warehouse_name','items':'item_name'}[section]
                    form=dict(valid,**{codefield:'AUD-FAIL',namefield:'Audit failure isolation'})
                    assert client.post(f'/inventory/{section}/add',data=form).status_code==302
                    table={'categories':'inventory_categories','warehouses':'warehouses','items':'inventory_items'}[section]
                    assert sql(f'SELECT COUNT(*) FROM {table} WHERE {codefield}=%s',('AUD-FAIL',),True)==[(1,)]
                    # The same audit outage cannot undo edits or status changes either.
                    form[codefield]='AUD-FAIL-EDIT';form[namefield]='Audit edit isolation'
                    assert client.post(f'/inventory/{section}/1/edit',data=form).status_code==302
                    key={'categories':'category_id','warehouses':'warehouse_id','items':'item_id'}[section]
                    assert sql(f'SELECT {codefield} FROM {table} WHERE {key}=1',fetch=True)==[('AUD-FAIL-EDIT',)]
                    for active in (0,1):
                        assert client.post(f'/inventory/{section}/1/status').status_code==302
                        assert sql(f'SELECT is_active FROM {table} WHERE {key}=1',fetch=True)==[(active,)]
            assert audit_count()==before_count
        finally:sql('DROP TRIGGER inventory_audit_failure')
        print('PASS all 12 persisted master audit events, numeric/readable identities, no-op status rejection and audit SQL failure isolation')
        assert (sql('SELECT * FROM stock_movements',fetch=True),sql('SELECT * FROM inventory_stock',fetch=True))==historical
        before=snapshot()
        raw=erp.app.test_client()
        with raw.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        for section,valid,_ in forms:
            for suffix in ('add','1/edit'):
                for form in (valid,dict(valid,csrf_token='invalid')):assert raw.post(f'/inventory/{section}/{suffix}',data=form).status_code==400
        assert snapshot()==before
        sql('DELETE FROM role_permissions WHERE role_id=1')
        for section,valid,_ in forms:
            for suffix in ('add','1/edit'):assert client.post(f'/inventory/{section}/{suffix}',data=valid).status_code==302
        assert snapshot()==before
        print('PASS all create/edit route overflow and duplicate errors, category errors, activation, preserved stock/history, CSRF and permission denial; rejected requests create no success audit events')
    print('SUCCESS: Inventory master-data checks passed on disposable MySQL only')


if __name__=='__main__':
    harness.run=run
    harness.main()
