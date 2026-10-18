"""IT asset/maintenance validation and master-lock reliability: disposable MySQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import time
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for
from test_finance_functional import FormValues


def run(port, data_dir):
    options = dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as c:
        cur=c.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_it_validation');cur.execute('USE erp_it_validation')
        for name in ['core','it_assets','it_asset_assignment','it_asset_maintenance','audit_logs']:
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        c.commit()
    options.update(database='erp_it_validation',init_command="SET SESSION sql_mode='NO_ENGINE_SUBSTITUTION'")
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as c:
            cur=c.cursor();cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            c.commit();return result
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Manager'),(2,'Viewer')")
    sql("INSERT INTO permissions(permission_code) VALUES('it_assets.view'),('it_assets.manage')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='it_assets.view'")
    for uid in [1,2]:sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES(%s,%s,%s,\'synthetic\')',(uid,uid,f'validate-{uid}'))
    for i in [1,2,3]:
        sql('INSERT INTO departments(department_id,department_code,department_name,is_active) VALUES(%s,%s,%s,%s)',(i,f'D{i}',f'Dept {i}',i!=3))
        sql('INSERT INTO it_asset_categories(category_id,category_code,category_name,is_active) VALUES(%s,%s,%s,%s)',(i,f'C{i}',f'Category {i}',i!=3))
    for i,status in [(1,'Active'),(2,'Inactive')]:sql('INSERT INTO employees(employee_id,employee_number,first_name,last_name,department_id,employment_status) VALUES(%s,%s,\'Synthetic\',\'Employee\',1,%s)',(i,f'EMP{i}',status))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-it-validation',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');repo=importlib.import_module('it_asset_repository')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        def client(uid=1):
            c=erp.app.test_client()
            with c.session_transaction() as sess:stamp_session(erp.app,sess,user_state(user_id=uid,role_id=uid,username=f'validate-{uid}',password_hash='synthetic'))
            return c
        c=client();token=csrf_token_for(c)
        def post(path,form):return c.post(path,data=dict(form,csrf_token=token))
        def snapshot():return [sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in ['it_assets','it_asset_assignments','it_asset_maintenance','audit_logs']]
        form=dict(asset_tag='VALID',asset_name='Laptop',category_id='1',department_id='1',assigned_employee_id='1',
                  brand='Brand',model='Model',serial_number='SERIAL',purchase_date='2026-01-01',purchase_cost='0.10',
                  warranty_expiry='2027-01-01',condition_status='GOOD',notes='Retain notes')
        invalid=[('asset_tag','x'*51),('asset_name','x'*151),('brand','x'*101),('model','x'*101),('serial_number','x'*101),('notes','x'*256),
                 ('asset_tag','ß'*26),('asset_name',' '),('category_id',''),('category_id','-1'),('category_id','999'),('category_id','3'),
                 ('department_id','NaN'),('department_id','999'),('department_id','3'),('assigned_employee_id','999'),
                 ('purchase_date','2026-02-30'),('purchase_date','0000-01-01'),('warranty_expiry','0999-01-01'),('condition_status','INVALID')]
        invalid += [('purchase_cost',v) for v in ['NaN','Infinity','-Infinity','-0.01','0.001','10000000000','1e2','1,00']]
        before=snapshot()
        for field,value in invalid:
            response=post('/it/assets/add',dict(form,**{field:value}))
            assert response.status_code==200,(field,value,response.status_code)
            assert snapshot()==before,(field,value)
        response=post('/it/assets/add',dict(form,purchase_cost='NaN'))
        fields=FormValues(response.get_data(as_text=True))
        for name in ['asset_tag','asset_name','brand','model','serial_number','purchase_date','purchase_cost','warranty_expiry']:
            assert fields.values[name]==('NaN' if name=='purchase_cost' else form[name])
        for name in ['category_id','department_id','assigned_employee_id','condition_status']:assert fields.selected(name)==form[name]
        assert form['notes'] in response.get_data(as_text=True)
        response=post('/it/assets/add',dict(form,department_id='<invalid>'))
        assert FormValues(response.get_data(as_text=True)).selected('department_id')=='<invalid>'
        assert '<invalid>' not in response.get_data(as_text=True)
        assert post('/it/assets/add',form).status_code==302
        aid=sql("SELECT asset_id FROM it_assets WHERE asset_tag='VALID'",fetch=True)[0][0]
        assert sql('SELECT status,assigned_employee_id,purchase_cost FROM it_assets WHERE asset_id=%s',(aid,),True)==[('ASSIGNED',1,Decimal('0.10'))]
        assert sql('SELECT employee_id,department_id,assigned_by FROM it_asset_assignments WHERE asset_id=%s',(aid,),True)==[(1,1,1)]
        before=snapshot()
        for f in [dict(form,asset_tag='VALID',serial_number='OTHER'),dict(form,asset_tag='OTHER',serial_number='SERIAL')]:
            response=post('/it/assets/add',f)
            assert response.status_code==200 and 'already exists' in response.get_data(as_text=True)
            assert FormValues(response.get_data(as_text=True)).values['asset_tag']==f['asset_tag'] and snapshot()==before
        edit_path=f'/it/assets/{aid}/edit'
        for field,value in invalid:
            if field=='assigned_employee_id':continue
            response=post(edit_path,dict(form,**{field:value}))
            assert response.status_code==200,(field,value,response.status_code)
            assert snapshot()==before,(field,value)
        # Historical inactive links remain selected and editable if unchanged.
        sql('UPDATE it_asset_categories SET is_active=0 WHERE category_id=1')
        sql('UPDATE departments SET is_active=0 WHERE department_id=1')
        values=FormValues(c.get(edit_path).get_data(as_text=True))
        assert values.selected('category_id')=='1' and values.selected('department_id')=='1'
        assert post(edit_path,dict(form,purchase_cost='0.00')).status_code==302
        assert sql('SELECT purchase_cost FROM it_assets WHERE asset_id=%s',(aid,),True)==[(Decimal('0.00'),)]
        assert FormValues(c.get(edit_path).get_data(as_text=True)).values['purchase_cost']=='0.00'
        sql('UPDATE it_asset_categories SET is_active=1 WHERE category_id=1')
        sql('UPDATE departments SET is_active=1 WHERE department_id=1')
        maximum=dict(form,asset_tag='MAX',asset_name='a'*150,brand='b'*100,model='m'*100,serial_number='s'*100,
                     notes='n'*255,purchase_cost='9999999999.99',purchase_date='1000-01-01',warranty_expiry='9999-12-31',assigned_employee_id='2')
        assert post('/it/assets/add',maximum).status_code==302
        assert sql("SELECT assigned_employee_id,purchase_cost FROM it_assets WHERE asset_tag='MAX'",fetch=True)==[(2,Decimal('9999999999.99'))]
        before=snapshot()
        for changes in [dict(asset_tag='MAX'),dict(serial_number='s'*100)]:
            response=post(edit_path,dict(form,**changes))
            assert response.status_code==200 and 'already exists' in response.get_data(as_text=True)
            assert snapshot()==before
        # Employee activity has no approved restrictive policy; it stays compatible.
        print('PASS actual VARCHAR/DATE/DECIMAL limits, non-strict SQL rejection/rollback, duplicates, form retention, historical inactive links and unchanged inactive-employee policy')

        maintenance=dict(maintenance_type='Repair',description='Fix',vendor='Vendor',cost='0.20',start_date='2026-10-01',notes='Retained maintenance')
        before=snapshot()
        for field,value in [('maintenance_type',''),('maintenance_type','x'*51),('description',''),('description','x'*256),('vendor','x'*151),('notes','x'*256),('start_date','2026-02-30'),('cost','NaN'),('cost','Infinity'),('cost','-1'),('cost','0.001'),('cost','10000000000')]:
            response=post(f'/it/assets/{aid}/maintenance/add',dict(maintenance,**{field:value}))
            assert response.status_code==200 and snapshot()==before,(field,value)
            assert FormValues(response.get_data(as_text=True)).selected('maintenance_type')==('x'*51 if field=='maintenance_type' and value else maintenance['maintenance_type'] if field!='maintenance_type' else '')
        assert post(f'/it/assets/{aid}/maintenance/add',maintenance).status_code==302
        mid=sql('SELECT maintenance_id FROM it_asset_maintenance WHERE asset_id=%s',(aid,),True)[0][0]
        before=snapshot()
        for value in ['2026-09-30','2026-02-30','0000-01-01']:
            assert post(f'/it/assets/maintenance/{mid}/complete',dict(completed_date=value)).status_code==302
            assert snapshot()==before
        assert post(f'/it/assets/maintenance/{mid}/complete',dict(completed_date='2026-10-01')).status_code==302
        assert sql('SELECT status,assigned_employee_id FROM it_assets WHERE asset_id=%s',(aid,),True)==[('ASSIGNED',1)]
        before=snapshot();post(f'/it/assets/maintenance/{mid}/complete',dict(completed_date='2026-10-01'));assert snapshot()==before
        print('PASS maintenance fields/cost/dates, chronological completion, same-day completion, duplicate rejection and custody/history preservation')

        # Master deactivation commits while a write is queued: eligibility is read
        # under a locking read after the wait, not from the form's stale options.
        def blocked_master(table,key,write):
            held=connect();held.start_transaction();cur=held.cursor()
            cur.execute(f'UPDATE {table} SET is_active=0 WHERE {key}=2')
            try:
                with ThreadPoolExecutor(1) as pool:
                    future=pool.submit(write)
                    try:
                        deadline=time.monotonic()+8
                        while sql("SELECT COUNT(*) FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0][0]<1:
                            assert time.monotonic()<deadline
                            time.sleep(0.05)
                    finally:held.commit()
                    try:future.result(timeout=10)
                    except ValueError:pass
                    else:raise AssertionError('Expected transaction-time inactive reference rejection')
            finally:held.close()
            sql(f'UPDATE {table} SET is_active=1 WHERE {key}=2')
        kwargs=dict(asset_tag='RACE',asset_name='Race',category_id=2,brand=None,model=None,serial_number=None,
                    department_id=2,assigned_employee_id=None,purchase_date=None,purchase_cost=Decimal('0.00'),warranty_expiry=None,
                    status='AVAILABLE',condition_status='GOOD',notes=None,created_by=1)
        before=snapshot()
        blocked_master('it_asset_categories','category_id',lambda:repo.create_it_asset(**kwargs))
        blocked_master('departments','department_id',lambda:repo.create_it_asset(**kwargs))
        assert snapshot()==before
        update=dict(kwargs);update.pop('assigned_employee_id');update.pop('status');update.pop('created_by');update['asset_id']=aid
        blocked_master('it_asset_categories','category_id',lambda:repo.update_it_asset(**update))
        blocked_master('departments','department_id',lambda:repo.update_it_asset(**update))
        assert snapshot()==before
        print('PASS four observed master-lock waits: concurrent category/department deactivation rejects stale create/edit selections without partial writes')

        # Simultaneous duplicate registration creates exactly one asset/history pair.
        def duplicate():
            try:repo.create_it_asset(**dict(kwargs,asset_tag='DUP-RACE',assigned_employee_id=1,status='ASSIGNED'));return True
            except ValueError as error:
                assert 'already exists' in str(error);return False
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(duplicate) for _ in range(2)]
            assert sum(f.result(timeout=10) for f in futures)==1
        assert sql("SELECT COUNT(*) FROM it_asset_assignments a JOIN it_assets i ON i.asset_id=a.asset_id WHERE i.asset_tag='DUP-RACE'",fetch=True)==[(1,)]
        # Inactive employees remain eligible under existing policy, but nonexistent
        # and concurrently deleted employees cannot become current custody.
        unassigned=repo.create_it_asset(**dict(kwargs,asset_tag='EMPLOYEE'))
        before=snapshot()
        for employee,department in [(999,1),(1,999)]:
            try:repo.assign_it_asset(unassigned,employee,department,1)
            except ValueError:pass
            else:raise AssertionError('Expected invalid assignment reference rejection')
            assert snapshot()==before
        repo.assign_it_asset(unassigned,2,1,1)
        assert sql('SELECT assigned_employee_id FROM it_assets WHERE asset_id=%s',(unassigned,),True)==[(2,)]
        unassigned=repo.create_it_asset(**dict(kwargs,asset_tag='DELETED-EMPLOYEE'))
        sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(3,'TEMP','Synthetic','Temporary')")
        held=connect();held.start_transaction();cur=held.cursor();cur.execute('DELETE FROM employees WHERE employee_id=3')
        before=snapshot()
        try:
            with ThreadPoolExecutor(1) as pool:
                future=pool.submit(repo.assign_it_asset,unassigned,3,1,1)
                try:
                    deadline=time.monotonic()+8
                    while sql("SELECT COUNT(*) FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0][0]<1:
                        assert time.monotonic()<deadline
                        time.sleep(0.05)
                finally:held.commit()
                try:future.result(timeout=10)
                except ValueError:pass
                else:raise AssertionError('Expected transaction-time employee existence validation')
        finally:held.close()
        assert snapshot()==before
        print('PASS duplicate registration commits once with one history; inactive employee compatibility, invalid references and an observed concurrent employee-deletion lock wait')

        # Late write errors must undo asset and history / maintenance changes.
        before=snapshot()
        sql("CREATE TRIGGER reject_initial_history BEFORE INSERT ON it_asset_assignments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic history failure'")
        try:
            try:repo.create_it_asset(**dict(kwargs,assigned_employee_id=1,status='ASSIGNED'))
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected injected history failure')
        finally:sql('DROP TRIGGER reject_initial_history')
        assert snapshot()==before
        sql("CREATE TRIGGER reject_maintenance_state BEFORE UPDATE ON it_assets FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic state failure'")
        try:
            try:repo.create_it_asset_maintenance(aid,'Repair','Fix',None,Decimal('0.00'),'2026-10-01',None,1)
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected injected late maintenance failure')
        finally:sql('DROP TRIGGER reject_maintenance_state')
        assert snapshot()==before
        mid=repo.create_it_asset_maintenance(aid,'Repair','Completion rollback',None,Decimal('0.00'),'2026-10-03',None,1)
        before=snapshot()
        sql("CREATE TRIGGER reject_completion_state BEFORE UPDATE ON it_assets FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic completion failure'")
        try:
            try:repo.complete_it_asset_maintenance(mid,'2026-10-03')
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected completion rollback after history update')
        finally:sql('DROP TRIGGER reject_completion_state')
        assert snapshot()==before
        repo.complete_it_asset_maintenance(mid,'2026-10-03')
        before=snapshot()
        class CommitFailure:
            def __init__(self):self.inner=connect()
            def __getattr__(self,name):return getattr(self.inner,name)
            def commit(self):raise RuntimeError('Synthetic pre-COMMIT failure')
        with patch.object(repo,'get_connection',side_effect=CommitFailure):
            try:repo.create_it_asset(**dict(kwargs,asset_tag='COMMIT-FAIL',assigned_employee_id=1,status='ASSIGNED'))
            except RuntimeError:pass
            else:raise AssertionError('Expected pre-COMMIT failure')
        assert snapshot()==before
        viewer=client(2)
        assert viewer.post('/it/assets/add',data=dict(form,csrf_token=csrf_token_for(viewer))).location.endswith('/dashboard')
        assert c.post('/it/assets/add',data=form).status_code==400
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND permission_code='it_assets.manage'")
        assert post(edit_path,form).location.endswith('/dashboard') and snapshot()==before
        assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True)==[(0,)]
        print('PASS late creation/maintenance rollback, CSRF, viewer denial, real permission revocation and zero unexpected audit writes')
    print('SUCCESS: IT validation tested with synthetic records in disposable MySQL only')


if __name__=='__main__':
    harness.run=run
    harness.main()
