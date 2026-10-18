"""Persisted IT Asset business audits, real concurrency and failure isolation."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
import time
import uuid
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as c:
        cur=c.cursor();cur.execute('SELECT @@datadir');assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_it_audit');cur.execute('USE erp_it_audit')
        for name in ['core','it_assets','it_asset_assignment','it_asset_maintenance','audit_logs']:
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        c.commit()
    options['database']='erp_it_audit'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as c:
            cur=c.cursor();cur.execute(query,params);result=cur.fetchall() if fetch else cur.lastrowid;c.commit();return result
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Audit operator'),(2,'Viewer')")
    sql("INSERT INTO permissions(permission_code) VALUES('it_assets.view'),('it_assets.manage')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='it_assets.view'")
    for uid in [1,2]:sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES(%s,%s,%s,\'synthetic\')',(uid,uid,f'auditor-{uid}'))
    sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(1,'PRIVATE','private first','private last')")
    sql("INSERT INTO departments(department_id,department_code,department_name) VALUES(1,'DPT','private department')")
    sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES(1,'BASE','private category')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='isolated-it-audit',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        erp=importlib.import_module('app');repo=importlib.import_module('it_asset_repository')
        stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        logger=stack.enter_context(patch.object(erp.app.logger,'exception'))
        def client(uid=1):
            c=erp.app.test_client()
            with c.session_transaction() as sess:stamp_session(erp.app,sess,user_state(user_id=uid,role_id=uid,username=f'auditor-{uid}',password_hash='synthetic'))
            return c
        def post(path,fields=None,uid=1):
            c=client(uid);return c.post(path,data=dict(fields or {},csrf_token=csrf_token_for(c)))
        def logs():return sql('SELECT user_id,username,module,action,entity_type,entity_id,description FROM audit_logs ORDER BY audit_log_id',fetch=True)
        def snapshot():return [sql('SELECT * FROM '+table+' ORDER BY 1',fetch=True) for table in ['it_assets','it_asset_categories','it_asset_assignments','it_asset_maintenance','audit_logs']]
        def form():return dict(asset_tag=uuid.uuid4().hex.upper(),asset_name='private asset',category_id='1',department_id='1',
                               assigned_employee_id='',condition_status='GOOD',purchase_cost='123456.78',notes='private notes')
        def asset(assigned=False):
            f=form()
            aid=repo.create_it_asset(f['asset_tag'],f['asset_name'],1,None,None,None,1,1 if assigned else None,
                None,None,None,'ASSIGNED' if assigned else 'AVAILABLE','GOOD','private notes',1)
            return aid,f
        def assignment(aid):return sql('SELECT assignment_id FROM it_asset_assignments WHERE asset_id=%s AND returned_at IS NULL',(aid,),True)[0][0]
        def maintenance(aid):return repo.create_it_asset_maintenance(aid,'Repair','private repair','private vendor',None,'2026-10-01','private notes',1)
        def fixture(kind):
            action=kind;entity='IT_ASSET';eid=None;aid=None;label=None
            if kind.startswith('CATEGORY_'):
                action=kind.removeprefix('CATEGORY_');entity='IT_ASSET_CATEGORY'
                label='CAT'+uuid.uuid4().hex[:16].upper()
                fields=dict(category_code=label,category_name='private category',description='private category description')
                if action=='CREATE':path='/it/assets/categories/add'
                else:
                    eid=repo.create_it_asset_category('OLD'+uuid.uuid4().hex[:16], 'private category',None)
                    path=f'/it/assets/categories/{eid}/edit'
                    if action in ['ACTIVATE','DEACTIVATE']:
                        sql('UPDATE it_asset_categories SET is_active=%s,category_code=%s WHERE category_id=%s',(action=='DEACTIVATE',label,eid))
                        path=f'/it/assets/categories/{eid}/status';fields={}
            elif kind=='CREATE':
                fields=form();fields['assigned_employee_id']='1';label=fields['asset_tag'];path='/it/assets/add'
            else:
                aid,fields=asset(kind in ['RETURN','MARK_LOST','RECOVER','MAINTENANCE_CREATE','MAINTENANCE_COMPLETE'])
                eid=aid;label=fields['asset_tag'];path=f'/it/assets/{aid}'
                if kind=='UPDATE':fields['asset_name']='private changed name';path+='/edit'
                elif kind=='ASSIGN':fields=dict(employee_id='1');path+='/assign'
                elif kind=='RETURN':fields=dict(assignment_id=assignment(aid));path+='/unassign'
                elif kind=='MARK_LOST':fields={};path+='/lost'
                elif kind=='RECOVER':repo.mark_it_asset_lost(aid);fields={};path+='/restore'
                elif kind=='RETIRE':fields={};path+='/retire'
                elif kind=='RESTORE':repo.retire_it_asset(aid);fields={};path+='/restore'
                elif kind=='MAINTENANCE_CREATE':
                    entity='IT_ASSET_MAINTENANCE';action='CREATE';eid=None
                    fields=dict(maintenance_type='Repair',description='private repair',vendor='private vendor',cost='123456.78',start_date='2026-10-01',notes='private notes');path+='/maintenance/add'
                elif kind=='MAINTENANCE_COMPLETE':
                    entity='IT_ASSET_MAINTENANCE';action='COMPLETE';eid=maintenance(aid)
                    fields=dict(completed_date='2026-10-02');path=f'/it/assets/maintenance/{eid}/complete'
            return dict(kind=kind,path=path,fields=fields,action=action,entity=entity,eid=eid,aid=aid,label=label)
        def resolve(f):
            if f['eid'] is not None:return f['eid']
            if f['entity']=='IT_ASSET':return sql('SELECT asset_id FROM it_assets WHERE asset_tag=%s',(f['label'],),True)[0][0]
            if f['entity']=='IT_ASSET_CATEGORY':return sql('SELECT category_id FROM it_asset_categories WHERE category_code=%s',(f['label'],),True)[0][0]
            return sql('SELECT maintenance_id FROM it_asset_maintenance WHERE asset_id=%s',(f['aid'],),True)[0][0]
        kinds=['CREATE','UPDATE','ASSIGN','RETURN','MARK_LOST','RECOVER','RETIRE','RESTORE',
               'CATEGORY_CREATE','CATEGORY_UPDATE','CATEGORY_ACTIVATE','CATEGORY_DEACTIVATE','MAINTENANCE_CREATE','MAINTENANCE_COMPLETE']
        fixtures=[]
        for kind in kinds:
            f=fixture(kind);before=len(logs());assert post(f['path'],f['fields']).status_code==302
            eid=resolve(f);f['eid']=eid;fixtures.append(f)
            after=logs();assert len(after)==before+1,(kind,after)
            row=after[-1]
            assert row[:6]==(1,'auditor-1','IT_ASSETS',f['action'],f['entity'],str(eid)),row
            assert f['label'] in row[6] and str(eid) in row[6],row
            assert 'private ' not in row[6] and '123456.78' not in row[6],row
            if kind not in ['CATEGORY_ACTIVATE','CATEGORY_DEACTIVATE']:
                # Duplicate CREATE keys, no-op UPDATE and stale status requests.
                before=snapshot();post(f['path'],f['fields']);assert snapshot()==before,kind
        assert len(logs())==14
        print('PASS fourteen persisted event variants: actors, numeric IDs, tags/codes, maintenance identity, minimal descriptions, duplicate/no-op rejection and one CREATE for initially assigned assets')

        for state in ['LOST','MAINTENANCE']:
            aid,_=asset(True);token=assignment(aid)
            if state=='LOST':repo.mark_it_asset_lost(aid)
            else:maintenance(aid)
            before=snapshot();post(f'/it/assets/{aid}/unassign',dict(assignment_id=token));assert snapshot()==before
        aid,_=asset(True);old=assignment(aid);repo.unassign_it_asset(aid,1,old);repo.assign_it_asset(aid,1,1,1)
        before=snapshot();post(f'/it/assets/{aid}/unassign',dict(assignment_id=old));assert snapshot()==before
        f=fixture('CREATE');before=snapshot();post(f['path'],dict(f['fields'],purchase_cost='NaN'));assert snapshot()==before
        f=fixture('MAINTENANCE_COMPLETE');before=snapshot();post(f['path'],dict(completed_date='2026-09-30'));assert snapshot()==before
        print('PASS approved blocked returns, stale same-employee custody, monetary/date validation: no success audits or business changes')

        for kind in kinds:
            f=fixture(kind);before=len(logs())
            sql("CREATE TRIGGER reject_it_audit BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit outage'")
            try:assert post(f['path'],f['fields']).status_code==302
            finally:sql('DROP TRIGGER reject_it_audit')
            eid=resolve(f);assert len(logs())==before
            if f['entity']=='IT_ASSET':
                expected={'CREATE':'ASSIGNED','ASSIGN':'ASSIGNED','RETURN':'AVAILABLE','MARK_LOST':'LOST','RECOVER':'ASSIGNED','RETIRE':'RETIRED','RESTORE':'AVAILABLE','UPDATE':'AVAILABLE'}[kind]
                assert sql('SELECT status FROM it_assets WHERE asset_id=%s',(eid,),True)==[(expected,)]
            elif f['entity']=='IT_ASSET_MAINTENANCE':
                assert sql('SELECT status FROM it_asset_maintenance WHERE maintenance_id=%s',(eid,),True)==[('OPEN' if kind=='MAINTENANCE_CREATE' else 'COMPLETED',)]
            else:
                assert sql('SELECT category_code,is_active FROM it_asset_categories WHERE category_id=%s',(eid,),True)==[(f['label'],kind!='CATEGORY_DEACTIVATE')]
        assert logger.called
        print('PASS actual audit SQL outage for all fourteen event variants: business operations remain committed')

        for kind in ['CREATE','RETURN','MAINTENANCE_CREATE','MAINTENANCE_COMPLETE']:
            f=fixture(kind);before=snapshot()
            target='it_asset_assignments' if kind=='CREATE' else 'it_assets'
            operation='INSERT' if kind=='CREATE' else 'UPDATE'
            sql(f"CREATE TRIGGER reject_business BEFORE {operation} ON {target} FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic late business failure'")
            try:
                try:post(f['path'],f['fields'])
                except mysql.connector.Error:pass
                else:raise AssertionError('Expected business SQL failure')
            finally:sql('DROP TRIGGER reject_business')
            assert snapshot()==before,kind
        print('PASS real late SQL rollback after asset/history/maintenance writes creates no success audit')

        def race(f):
            held=connect();held.start_transaction();cur=held.cursor();cur.execute('SELECT asset_id FROM it_assets WHERE asset_id=%s FOR UPDATE',(f['aid'],));cur.fetchall()
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures=[pool.submit(post,f['path'],f['fields']) for _ in range(2)]
                    try:
                        deadline=time.monotonic()+8
                        while sql("SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'",fetch=True)[0][0]<2:
                            assert time.monotonic()<deadline,'Both business transactions must really wait'
                            time.sleep(0.05)
                    finally:held.commit()
                    statuses=[future.result(timeout=12).status_code for future in futures]
                    expected=[200,302] if f['kind'] in ['UPDATE','MAINTENANCE_CREATE'] else [302,302]
                    assert sorted(statuses)==expected,(f['kind'],statuses)
            finally:held.close()
        for kind in ['ASSIGN','RETURN','MARK_LOST','RECOVER','RETIRE','RESTORE','MAINTENANCE_CREATE','MAINTENANCE_COMPLETE','UPDATE']:
            f=fixture(kind);before=len(logs());race(f)
            assert len(logs())==before+1,kind
            assert logs()[-1][3:6]==(f['action'],f['entity'],str(resolve(f))),kind
        # Category toggle requests that both read the same initial state must
        # produce one changed row and one DEACTIVATE event, not a duplicate.
        f=fixture('CATEGORY_DEACTIVATE');original=erp.get_it_asset_category_by_id
        barrier=threading.Barrier(2);counter=[0];lock=threading.Lock()
        def same_preflight(cid):
            result=original(cid)
            with lock:counter[0]+=1;n=counter[0]
            if n<=2:barrier.wait(8)
            return result
        before=len(logs())
        with patch.object(erp,'get_it_asset_category_by_id',side_effect=same_preflight),ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(post,f['path'],f['fields']) for _ in range(2)]
            assert all(future.result(timeout=12).status_code==302 for future in futures)
        assert len(logs())==before+1 and logs()[-1][3]=='DEACTIVATE'
        print('PASS nine actual two-waiter route races and concurrent stale category toggles: exactly one committed-action audit each')

        before=snapshot()
        for f in fixtures:
            assert post(f['path'],f['fields'],uid=2).location.endswith('/dashboard')
            assert client().post(f['path'],data=f['fields']).status_code==400
        assert snapshot()==before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND permission_code='it_assets.manage'")
        for f in fixtures:assert post(f['path'],f['fields']).location.endswith('/dashboard')
        assert snapshot()==before
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert post(fixtures[0]['path'],fixtures[0]['fields']).location.endswith('/login')
        assert snapshot()==before
        print('PASS viewer/forged requests, missing CSRF, committed permission revocation and disabled users: no business/audit changes')
    print('SUCCESS: IT audit verification used disposable MySQL and synthetic records only')


if __name__=='__main__':
    harness.run=run
    harness.main()
