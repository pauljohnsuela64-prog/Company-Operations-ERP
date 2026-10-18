"""IT category validation in strict/non-strict disposable MySQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
import time
import uuid
from html.parser import HTMLParser
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as c:
        cur=c.cursor();cur.execute('SELECT @@datadir');assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE erp_it_categories');cur.execute('USE erp_it_categories')
        for name in ['core','it_assets','it_asset_assignment','it_asset_maintenance','audit_logs']:
            for statement in re.sub(r'--[^\n]*','',(harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):cur.execute(statement)
        c.commit()
    options['database']='erp_it_categories'
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
        class Values(HTMLParser):
            def __init__(self,html):
                super().__init__();self.values={};self.current=None;self.feed(html)
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='input' and attrs.get('name'):self.values[attrs['name']]=attrs.get('value','')
                if tag=='textarea':self.current=attrs.get('name');self.values[self.current]=''
            def handle_data(self,data):
                if self.current:self.values[self.current]+=data
            def handle_endtag(self,tag):
                if tag=='textarea':self.current=None
        sequence=0
        def fields():
            nonlocal sequence
            sequence+=1
            return dict(category_code='C'+str(sequence).zfill(29),category_name='N'*100,description='D'*255)
        def retained(response,values):
            assert response.status_code==200,response.status_code
            form=Values(response.get_data(as_text=True)).values
            assert {key:form[key] for key in ['category_code','category_name','description']}=={key:values.get(key,'') for key in ['category_code','category_name','description']}
        for mode in ['STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION','NO_ENGINE_SUBSTITUTION']:
            options['init_command']=f"SET SESSION sql_mode='{mode}'"
            assert ('STRICT_TRANS_TABLES' in sql('SELECT @@session.sql_mode',fetch=True)[0][0])==mode.startswith('STRICT')
            valid=fields();before=len(logs())
            assert post('/it/assets/categories/add',valid).status_code==302
            cid=sql('SELECT category_id FROM it_asset_categories WHERE category_code=%s',(valid['category_code'],),True)[0][0]
            assert sql('SELECT category_code,category_name,description FROM it_asset_categories WHERE category_id=%s',(cid,),True)==[tuple(valid.values())]
            assert logs()[-1][0:6]==(1,'auditor-1','IT_ASSETS','CREATE','IT_ASSET_CATEGORY',str(cid))
            assert len(logs())==before+1
            updated=fields();updated['category_code']=' '+updated['category_code'].lower()+' '
            updated['category_name']=' '+updated['category_name']+' ';updated['description']=' '+updated['description']+' '
            assert post(f'/it/assets/categories/{cid}/edit',updated).status_code==302
            assert sql('SELECT category_code,category_name,description FROM it_asset_categories WHERE category_id=%s',(cid,),True)==[(updated['category_code'].strip().upper(),updated['category_name'].strip(),updated['description'].strip())]
            assert logs()[-1][3:6]==('UPDATE','IT_ASSET_CATEGORY',str(cid)) and len(logs())==before+2
            baseline=dict(category_code='RETAINED',category_name='Retained <name> "quoted"',description='Retained <description> & notes')
            invalid=[]
            for field,limit in [('category_code',30),('category_name',100),('description',255)]:
                values=dict(baseline);values[field]='X'*(limit+1);invalid.append(values)
            invalid += [{},dict(category_code=' ',category_name='Name'),dict(category_code='CODE',category_name=' '),dict(baseline,category_code=chr(223)*16)]
            for path in ['/it/assets/categories/add',f'/it/assets/categories/{cid}/edit']:
                for values in invalid:
                    before_snapshot=snapshot();response=post(path,values)
                    retained(response,values);assert snapshot()==before_snapshot
                    assert 'successfully.' not in response.get_data(as_text=True)
            # Repository callers also reject invalid values before writing in both modes.
            for values in invalid:
                args=tuple(values.get(k,'') for k in ['category_code','category_name','description'])
                for call in [lambda:repo.create_it_asset_category(*args),lambda:repo.update_it_asset_category(cid,*args)]:
                    before_snapshot=snapshot()
                    try:call()
                    except ValueError:pass
                    else:raise AssertionError('Repository accepted invalid category')
                    assert snapshot()==before_snapshot
            other=fields();assert post('/it/assets/categories/add',other).status_code==302
            duplicate=dict(other,category_name='Retained duplicate name',description='Retained duplicate description')
            for path in ['/it/assets/categories/add',f'/it/assets/categories/{cid}/edit']:
                before_snapshot=snapshot();response=post(path,duplicate)
                retained(response,duplicate)
                assert 'Asset category code already exists.' in response.get_data(as_text=True)
                assert snapshot()==before_snapshot
            # Names are not unique in the existing schema; preserve that policy.
            same_name=fields();same_name['category_name']=other['category_name'];same_name['description']=''
            assert post('/it/assets/categories/add',same_name).status_code==302
            new_id=sql('SELECT category_id FROM it_asset_categories WHERE category_code=%s',(same_name['category_code'],),True)[0][0]
            assert sql('SELECT description FROM it_asset_categories WHERE category_id=%s',(new_id,),True)==[(None,)]
            assert post(f'/it/assets/categories/{cid}/edit',dict(category_code='CODE-'+str(sequence),category_name='Same name permitted',description=' ')).status_code==302
            assert sql('SELECT description FROM it_asset_categories WHERE category_id=%s',(cid,),True)==[(None,)]
            for expected in [False,True]:
                before=len(logs());assert post(f'/it/assets/categories/{cid}/status').status_code==302
                assert sql('SELECT is_active FROM it_asset_categories WHERE category_id=%s',(cid,),True)==[(expected,)]
                assert len(logs())==before+1 and logs()[-1][3]==('ACTIVATE' if expected else 'DEACTIVATE')
            print('PASS mode',mode,': exact boundaries, normalization, all oversized/missing fields, raw escaped form retention, duplicate rollback, optional description, names policy, activation and precise audits')
        # Fail a legitimate UPDATE at SQL execution: previous record and audits remain intact.
        sql("CREATE TRIGGER reject_category_update BEFORE UPDATE ON it_asset_categories FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic rollback'")
        before_snapshot=snapshot()
        try:
            try:post(f'/it/assets/categories/{cid}/edit',fields())
            except mysql.connector.Error:pass
            else:raise AssertionError('Expected SQL failure')
        finally:sql('DROP TRIGGER reject_category_update')
        assert snapshot()==before_snapshot
        print('PASS actual SQL update rollback: no partial fields or success audit')
        before_snapshot=snapshot()
        for path in ['/it/assets/categories/add',f'/it/assets/categories/{cid}/edit']:
            assert post(path,fields(),uid=2).location.endswith('/dashboard')
            assert client().post(path,data=fields()).status_code==400
            invalid_csrf=dict(fields(),csrf_token='forged');assert client().post(path,data=invalid_csrf).status_code==400
        assert snapshot()==before_snapshot
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND permission_code='it_assets.manage'")
        for path in ['/it/assets/categories/add',f'/it/assets/categories/{cid}/edit']:
            assert post(path,fields()).location.endswith('/dashboard')
        assert snapshot()==before_snapshot
        print('PASS forged viewer POST, CSRF missing/invalid, fresh permission revocation and no unauthorized audit/business changes')
    print('SUCCESS: category validation verified only with disposable MySQL and synthetic records')


if __name__=='__main__':
    harness.run=run
    harness.main()
