"""Read-only Inventory reporting on disposable MySQL with synthetic history."""
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import uuid
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='',connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cursor=connection.cursor();cursor.execute('SELECT @@datadir')
        assert Path(cursor.fetchone()[0]).resolve()==data_dir.resolve()
        cursor.execute('CREATE DATABASE erp_inventory_reporting_test');cursor.execute('USE erp_inventory_reporting_test')
        for name in ('core','inventory','procurement','audit_logs'):
            source=(harness.ROOT/'database'/f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*','',source).split(';'):
                statement=statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b',statement,re.I):cursor.execute(statement)
        connection.commit()
    options['database']='erp_inventory_reporting_test'
    def connect():return mysql.connector.connect(**options)
    def sql(query,params=(),fetch=False):
        with connect() as connection:
            cursor=connection.cursor();cursor.execute(query,params)
            result=cursor.fetchall() if fetch else cursor.lastrowid
            connection.commit();return result
    def snapshot():
        return [sql('SELECT * FROM '+table+' ORDER BY 1,2',fetch=True) for table in ('inventory_items','warehouses','inventory_stock','stock_movements','purchase_requests','purchase_request_items','purchase_orders','purchase_order_items','goods_receipts','goods_receipt_items','audit_logs')]
    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Inventory read-only'),(2,'Denied')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'report.user','synthetic'),(2,2,'denied','synthetic')")
    view=sql("INSERT INTO permissions(permission_code) VALUES ('inventory.view')")
    sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(view,))
    procurement=sql("INSERT INTO permissions(permission_code) VALUES ('procurement.view')")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES (1,'MAIN','Main'),(2,'SECOND','Second'),(3,'UNUSED','Unused')")
    for identifier,code,active in ((1,'NEVER',1),(2,'BALANCED',1),(3,'OPENING',1),(4,'DIFFERENT',1),(5,'LEDGER_ONLY',1),(6,'ADJUSTED',1),(7,'ARCHIVED',0),(8,'INACTIVE_EMPTY',0)):
        sql('INSERT INTO inventory_items(item_id,item_code,item_name,is_active) VALUES (%s,%s,%s,%s)',(identifier,code,'Synthetic '+code,active))
    for item,warehouse,qty in ((2,1,'10'),(2,2,'0'),(3,1,'8'),(4,1,'9'),(6,1,'4'),(7,1,'2')):
        sql('INSERT INTO inventory_stock(item_id,warehouse_id,quantity) VALUES (%s,%s,%s)',(item,warehouse,qty))
    def movement(item,warehouse,kind,qty,notes='',reference_type='MANUAL_STOCK_IN',reference_id=None,created='2026-10-18 10:00:00'):
        return sql('INSERT INTO stock_movements(item_id,warehouse_id,movement_type,quantity,notes,reference_type,reference_id,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,1,%s)',(item,warehouse,kind,qty,notes,reference_type,reference_id,created))
    movement(2,1,'IN','12','opening coverage not verified')
    literal=movement(2,1,'OUT','2','literal %_ reference',reference_type='MANUAL_STOCK_OUT')
    movement(2,2,'IN','1',created='2026-10-17 23:59:59')
    movement(2,2,'OUT','1',reference_type='MANUAL_STOCK_OUT',created='2026-10-17 23:59:59')
    movement(4,1,'IN','4','legacy incomplete')
    movement(5,1,'IN','3','balance missing')
    movement(6,1,'ADJUSTMENT_IN','5','historical adjustment')
    movement(6,1,'ADJUSTMENT_OUT','1','historical adjustment')
    movement(7,1,'IN','2','archived item history')
    movement(7,1,'OUT','1','next-day boundary',reference_type='MANUAL_STOCK_OUT',created='2026-10-19 00:00:00')
    missing=movement(4,1,'IN','1','orphan receipt reference','GOODS_RECEIPT',99999)
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES (1,'S','Synthetic')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv',return_value=False))
        stack.enter_context(patch.dict('os.environ',SECRET_KEY='report-mysql-tests-only',ERP_ENV='testing',ERP_DEBUG='false'))
        database=importlib.import_module('database');stack.enter_context(patch.object(database,'get_connection',side_effect=connect))
        names=('stock_repository','inventory_reporting','purchase_request_repository','purchase_order_repository','goods_receipt_repository')
        modules=[importlib.import_module(name) for name in names]
        for module in modules:stack.enter_context(patch.object(module,'get_connection',side_effect=connect))
        stock,reports,pr,po,gr=modules
        rid,_=pr.create_purchase_request(1,None,'Synthetic source reference');pr.add_purchase_request_item(rid,2,'1','2.50')
        assert pr.submit_purchase_request(rid);assert pr.approve_purchase_request(rid,1)
        oid,_=po.create_purchase_order_from_request(rid,1,1);assert po.send_purchase_order(oid)
        oi=po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
        receipt_id,receipt_number,_=gr.create_goods_receipt(oid,1,1,{oi:'1'},submission_id=str(uuid.uuid4()))
        sql("UPDATE stock_movements SET created_at='2026-10-18 23:59:59' WHERE reference_type='GOODS_RECEIPT' AND reference_id=%s",(receipt_id,))
        wrong=movement(4,1,'IN','1','wrong item receipt reference','GOODS_RECEIPT',receipt_id)
        before=snapshot()
        balances=stock.get_all_stock()
        never=[row for row in balances if row['item_id']==1]
        assert len(never)==1 and never[0]['quantity']==Decimal('0') and never[0]['warehouse_id'] is None and not never[0]['has_stock_record']
        assert not any(row['item_id'] in (5,8) for row in balances)
        assert any(row['item_id']==7 and row['quantity']==Decimal('2') for row in balances)
        assert [(row['warehouse_id'],row['quantity']) for row in balances if row['item_id']==2]==[(1,Decimal('11')),(2,Decimal('0'))]
        assert snapshot()==before
        print('PASS virtual zero rows, no invented warehouse associations, separate warehouse balances and historical inactive stock visibility')
        combined=reports.get_movement_page(item_id=2,warehouse_id=1,movement_type='OUT',date_from='2026-10-18',date_to='2026-10-18',q='%_')
        assert [row['movement_id'] for row in combined['rows']]==[literal]
        assert reports.get_movement_page(q="' OR 1=1 --")['total']==0
        assert reports.get_movement_page(q=receipt_number)['total']==1
        assert reports.get_movement_page(q='BALANCED')['total']==5
        assert reports.get_movement_page(warehouse_id=2)['total']==2
        assert reports.get_movement_page(movement_type='ADJUSTMENT_OUT')['total']==1
        day=reports.get_movement_page(date_from='2026-10-18',date_to='2026-10-18')
        assert day['total']==sql("SELECT COUNT(*) FROM stock_movements WHERE created_at>='2026-10-18' AND created_at<'2026-10-19'",fetch=True)[0][0]
        expected=sql('SELECT movement_id FROM stock_movements ORDER BY created_at DESC,movement_id DESC',fetch=True)
        ids=[];page=1
        while True:
            data=reports.get_movement_page(page=page,page_size=2);ids.extend(row['movement_id'] for row in data['rows'])
            if page==data['pages']:break
            page+=1
        assert ids==[row[0] for row in expected] and len(ids)==len(set(ids))
        assert reports.get_movement_page(page=999999,page_size=2)['page']==page
        assert reports.get_movement_page(item_id=99999)['total']==0
        records=reports.get_movement_page(page_size=100)['rows']
        assert next(row for row in records if row['movement_id']==missing)['source_receipt_id'] is None
        assert next(row for row in records if row['movement_id']==wrong)['source_receipt_id'] is None
        assert any(row['source_receipt_id']==receipt_id and row['receipt_number']==receipt_number for row in records)
        assert snapshot()==before
        print('PASS bound literal search, combined filters, inclusive dates, page boundaries, deterministic ordering and supported/orphan reference handling')
        reconciliation=reports.get_reconciliation_page(page_size=100)
        pairs={(row['item_id'],row['warehouse_id']):row for row in reconciliation['rows']}
        assert pairs[(2,1)]['difference']==0 and 'coverage unverified' in pairs[(2,1)]['comparison']
        assert pairs[(4,1)]['difference']==Decimal('3') and 'coverage unverified' in pairs[(4,1)]['comparison']
        assert pairs[(3,1)]['difference'] is None and 'opening balance unknown' in pairs[(3,1)]['comparison']
        assert pairs[(5,1)]['difference'] is None and not pairs[(5,1)]['has_balance']
        assert pairs[(6,1)]['movement_balance']==Decimal('4') and pairs[(6,1)]['difference']==0
        assert reports.get_reconciliation_page(item_id=6,warehouse_id=1)['total']==1
        assert reports.get_reconciliation_page(item_id=99999)['total']==0
        assert reports.get_reconciliation_page(page=999,page_size=2)['page']==reports.get_reconciliation_page(page_size=2)['pages']
        assert snapshot()==before
        print('PASS signed adjustments, matches/differences with unverified coverage, missing history/balance, reconciliation filters and pagination; no writes')
        erp=importlib.import_module('app');stack.enter_context(patch.dict(erp.app.config,TESTING=True))
        client=csrf_client(erp.app)
        with client.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(1))
        assert 'No warehouse balance recorded' in client.get('/inventory/stock').get_data(as_text=True)
        html=client.get('/inventory/stock/movements?page_size=2&q=BALANCED').get_data(as_text=True)
        assert 'Next' in html and 'q=BALANCED' in html and 'page_size=2' in html
        link=f'href="/procurement/receipts/history/{receipt_id}"'
        html=client.get('/inventory/stock/movements').get_data(as_text=True)
        assert receipt_number in html and link not in html
        sql('INSERT INTO role_permissions(role_id,permission_id) VALUES (1,%s)',(procurement,))
        html=client.get('/inventory/stock/movements').get_data(as_text=True)
        assert link in html
        response=client.get('/inventory/stock/reconciliation')
        assert response.status_code==200 and 'not proof that stock is wrong' in response.get_data(as_text=True)
        for path in ('/inventory/stock/movements','/inventory/stock/reconciliation'):
            for query in ('?item_id=bad','?page=-1','?page_size=101'):
                assert client.get(path+query).status_code==400
        for query in ('?date_from=bad','?movement_type=BAD','?date_from=2026-10-19&date_to=2026-10-18'):
            assert client.get('/inventory/stock/movements'+query).status_code==400
        denied=csrf_client(erp.app)
        with denied.session_transaction() as mapping:stamp_session(erp.app,mapping,erp.get_authorization_state(2))
        for path in ('/inventory/stock','/inventory/stock/movements','/inventory/stock/reconciliation'):
            assert denied.get(path).status_code==302
            assert client.post(path).status_code==405
        assert snapshot()==before
        print('PASS actual report rendering, retained page filters, reference permission changes, validation errors and denied access; business/audit data unchanged')
    print('SUCCESS: Inventory reporting verified with disposable MySQL only')


if __name__=='__main__':
    harness.run=run
    harness.main()
