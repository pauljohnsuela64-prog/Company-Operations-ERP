"""Run with .venv/Scripts/python tests/mysql_procurement_smoke.py.

Starts a disposable MySQL server using the existing isolated smoke harness.
Never uses the configured company database or its credentials.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
import uuid
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT @@datadir')
        assert Path(cursor.fetchone()[0]).resolve() == data_dir.resolve()
        cursor.execute('CREATE DATABASE erp_procurement_test')
        cursor.execute('USE erp_procurement_test')
        for name in ('core', 'inventory', 'procurement'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                statement = statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b', statement, re.I):
                    cursor.execute(statement)
        connection.commit()
    options['database'] = 'erp_procurement_test'

    def connect():
        return mysql.connector.connect(**options)

    def sql(query, params=(), fetch=False):
        with connect() as connection:
            cursor = connection.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall() if fetch else cursor.lastrowid
            connection.commit()
            return result

    def fails(action, message=None):
        try:
            action()
        except ValueError as error:
            if message:
                assert message in str(error), str(error)
        else:
            raise AssertionError('Invalid operation succeeded')

    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Test')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES (1,1,'test','unused')")
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES (1,'TEST','Test')")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES (1,'TEST','Test'),(2,'OTHER','Other')")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name) VALUES (1,'TEST','Test')")
    with ExitStack() as stack:
        modules = [importlib.import_module(name) for name in ('purchase_request_repository', 'purchase_order_repository', 'goods_receipt_repository')]
        for module in modules:
            stack.enter_context(patch.object(module, 'get_connection', side_effect=connect))
        pr, po, gr = modules
        def receive(*args, **kwargs):
            kwargs.setdefault('submission_id', str(uuid.uuid4()))
            return gr.create_goods_receipt(*args, **kwargs)
        # Inspect the actual disposable MySQL schema, not just the SQL source.
        for table, column in [('purchase_orders','notes'), ('purchase_requests','rejection_reason'), ('goods_receipts','notes'), ('stock_movements','notes')]:
            assert sql('SELECT CHARACTER_MAXIMUM_LENGTH FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s', (table,column), True) == [(255,)]
        for table, column in [('purchase_request_items','quantity'), ('purchase_request_items','estimated_unit_cost'), ('purchase_order_items','unit_cost'), ('goods_receipt_items','quantity_received')]:
            assert sql('SELECT NUMERIC_PRECISION,NUMERIC_SCALE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name=%s', (table,column), True) == [(12,2)]
        print('PASS actual MySQL column compatibility')

        def draft():
            rid, _ = pr.create_purchase_request(1, None, 'Isolated test')
            pr.add_purchase_request_item(rid, 1, '10.25', '2.50')
            iid = sql('SELECT request_item_id FROM purchase_request_items WHERE request_id=%s', (rid,), True)[0][0]
            return rid, iid

        def order():
            rid, iid = draft()
            assert pr.submit_purchase_request(rid)
            assert pr.approve_purchase_request(rid, 1)
            oid, _ = po.create_purchase_order_from_request(rid, 1, 1, notes='x'*255)
            oi = sql('SELECT purchase_order_item_id FROM purchase_order_items WHERE purchase_order_id=%s', (oid,), True)[0][0]
            return rid, oid, oi

        rid, oid, oi = order()
        assert po.get_purchase_order_by_id(oid)['status'] == 'DRAFT'
        fails(lambda: po.create_purchase_order_from_request(rid,1,1), 'already exists')
        fails(lambda: receive(oid,1,1,{oi:'1'}), 'not available')
        po.update_purchase_order_item_cost(oi, '3.75')
        assert po.send_purchase_order(oid)
        assert not po.send_purchase_order(oid)
        fails(lambda: po.update_purchase_order_item_cost(oi,'9'), 'DRAFT')
        receipt, _, _ = receive(oid,1,1,{oi:'4.25'}, notes='first')
        assert po.get_purchase_order_by_id(oid)['status'] == 'PARTIALLY_RECEIVED'
        fails(lambda: po.cancel_purchase_order(oid))
        fails(lambda: receive(oid,1,1,{oi:'6.01'}), 'remaining')
        receive(oid,1,1,{oi:'6.00'})
        assert po.get_purchase_order_by_id(oid)['status'] == 'RECEIVED'
        assert pr.get_purchase_request_by_id(rid)['status'] == 'COMPLETED'
        assert sql('SELECT warehouse_id,quantity FROM inventory_stock', fetch=True) == [(1,Decimal('10.25'))]
        rows = sql('SELECT quantity,reference_type,reference_id,notes FROM stock_movements ORDER BY movement_id', fetch=True)
        assert [row[0] for row in rows] == [Decimal('4.25'),Decimal('6')]
        assert rows[0][1:3] == ('GOODS_RECEIPT',receipt) and rows[0][3].endswith(' - first')
        fails(lambda: receive(oid,1,1,{oi:'1'}))
        print('PASS full lifecycle, warehouse balances, movement references, failed transitions')

        rid, iid = draft()
        invalid = ['NaN','sNaN','Infinity','-Infinity','-1','0.001','10000000000','junk','1e999999',None]
        for value in invalid + ['0']:
            fails(lambda: pr.add_purchase_request_item(rid,1,value))
            fails(lambda: pr.update_purchase_request_item(iid,1,value))
        for value in invalid:
            fails(lambda: pr.update_purchase_request_item(iid,1,'1',value) if value is not None else po.update_purchase_order_item_cost(oi,value))
        fails(lambda: pr.add_purchase_request_item(rid,1,'1',notes='x'*256), '255')
        fails(lambda: pr.reject_purchase_request(rid,'x'*256), '255')
        fails(lambda: po.create_purchase_order_from_request(rid,1,1,notes='x'*256), '255')
        assert len(pr.get_purchase_request_items(rid)) == 1
        print('PASS numeric and field length rejection without item writes')

        rid, oid, oi = order()
        assert po.send_purchase_order(oid)
        def snapshot():
            return [sql('SELECT * FROM '+table, fetch=True) for table in ('goods_receipts','goods_receipt_items','inventory_stock','stock_movements','purchase_orders','purchase_requests')]
        before = snapshot()
        for value in invalid:
            fails(lambda: receive(oid,1,1,{oi:value}))
        fails(lambda: receive(oid,1,1,{oi:'1'},notes='x'*255), 'references')
        assert snapshot() == before
        sql("CREATE TRIGGER procurement_failure BEFORE INSERT ON stock_movements FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test failure'")
        try:
            try:
                receive(oid,1,1,{oi:'1'})
            except ValueError as error:
                assert isinstance(error.__cause__, mysql.connector.Error)
            else:
                raise AssertionError('Expected injected failure')
            assert snapshot() == before
        finally:
            sql('DROP TRIGGER procurement_failure')
        print('PASS receipt validation and late write failure roll back all business data')

        # Force transitions to hold the parent row while an edit attempts to lock it.
        # The edit must wait, then see the committed non-draft status and reject.
        for kind in ('add','update','delete','cost'):
            rid, iid = draft()
            if kind == 'cost':
                pr.submit_purchase_request(rid)
                pr.approve_purchase_request(rid,1)
                oid,_ = po.create_purchase_order_from_request(rid,1,1)
                oi = po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
            table,key,ident,status = ('purchase_orders','purchase_order_id',oid,'SENT') if kind=='cost' else ('purchase_requests','request_id',rid,'SUBMITTED')
            action = {'add':lambda:pr.add_purchase_request_item(rid,1,'1'), 'update':lambda:pr.update_purchase_request_item(iid,1,'99'), 'delete':lambda:pr.delete_purchase_request_item(iid), 'cost':lambda:po.update_purchase_order_item_cost(oi,'99')}[kind]
            with connect() as blocker, ThreadPoolExecutor(max_workers=1) as executor:
                cur=blocker.cursor()
                cur.execute(f'UPDATE {table} SET status=%s WHERE {key}=%s',(status,ident))
                entered=threading.Event()
                original=modules[1 if kind=='cost' else 0].lock_item_parent if kind!='add' else pr.lock_draft
                def observed(*args):
                    entered.set()
                    return original(*args)
                attr='lock_draft' if kind=='add' else 'lock_item_parent'
                with patch.object(modules[1 if kind=='cost' else 0],attr,side_effect=observed):
                    future=executor.submit(fails, action, 'DRAFT')
                    assert entered.wait(3)
                    assert not future.done()
                    blocker.commit()
                    future.result(timeout=5)
            assert pr.get_purchase_request_item_by_id(iid)['quantity'] == Decimal('10.25')
            assert len(pr.get_purchase_request_items(rid)) == 1
            if kind=='cost':
                assert po.get_purchase_order_item_by_id(oi)['unit_cost'] == Decimal('2.50')
        print('PASS concurrent submission/sending blocks and rejects add/update/delete/cost edits')

        # Exercise the opposite ordering with actual repository transitions:
        # a writer holds the draft lock; submission/sending must wait for it.
        for kind in ('delete', 'cost'):
            rid, iid = draft()
            if kind == 'cost':
                pr.submit_purchase_request(rid)
                pr.approve_purchase_request(rid, 1)
                oid, _ = po.create_purchase_order_from_request(rid, 1, 1)
                oi = po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
            module = po if kind == 'cost' else pr
            locked, release = threading.Event(), threading.Event()
            original = module.lock_item_parent
            def hold(*args):
                original(*args)
                locked.set()
                assert release.wait(5)
            edit = (lambda: po.update_purchase_order_item_cost(oi, '7.25')) if kind == 'cost' else (lambda: pr.delete_purchase_request_item(iid))
            transition = (lambda: po.send_purchase_order(oid)) if kind == 'cost' else (lambda: pr.submit_purchase_request(rid))
            with ThreadPoolExecutor(max_workers=2) as executor, patch.object(module, 'lock_item_parent', side_effect=hold):
                editing = executor.submit(edit)
                assert locked.wait(3)
                transitioning = executor.submit(transition)
                try:
                    assert not transitioning.done()
                finally:
                    release.set()
                editing.result(timeout=5)
                assert transitioning.result(timeout=5) == (kind == 'cost')
            if kind == 'cost':
                assert po.get_purchase_order_by_id(oid)['status'] == 'SENT'
                assert po.get_purchase_order_item_by_id(oi)['unit_cost'] == Decimal('7.25')
            else:
                assert pr.get_purchase_request_by_id(rid)['status'] == 'DRAFT'
        print('PASS edits commit before transitions; last-item deletion prevents empty submission')

        # Real route validation with isolated persisted fixtures and rendered errors.
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        erp = importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True, SECRET_KEY='isolated-test'))
        rid, iid = draft()
        client = erp.app.test_client()
        with client.session_transaction() as session:
            session.update(user_id=1, username='test', permissions=['procurement.requests.create','procurement.requests.approve','procurement.orders.create','procurement.orders.manage'])
        def post(endpoint, data, expected, **values):
            with erp.app.test_request_context():
                from flask import url_for
                path = url_for(endpoint, **values)
            response = client.post(path, data=data)
            assert response.status_code in (200,302), response.status_code
            with client.session_transaction() as session:
                messages = str(session.pop('_flashes', []))
            assert expected in response.get_data(as_text=True) + messages, (endpoint, messages)
        post('add_purchase_request_item_route', {'item_id':'1','quantity':'NaN'}, 'finite', request_id=rid)
        post('edit_purchase_request_item_route', {'item_id':'1','quantity':'1.001'}, 'two decimal', request_id=rid, request_item_id=iid)
        pr.submit_purchase_request(rid)
        post('reject_purchase_request_route', {'rejection_reason':'x'*256}, '255', request_id=rid)
        pr.approve_purchase_request(rid,1)
        post('create_purchase_order', {'supplier_id':'1','notes':'x'*256}, '255', request_id=rid)
        oid, _ = po.create_purchase_order_from_request(rid,1,1)
        oi=po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
        post('edit_purchase_order_item_cost_route', {'unit_cost':'Infinity'}, 'finite', purchase_order_id=oid, purchase_order_item_id=oi)
        with patch.object(erp,'update_purchase_order_item_cost', side_effect=ValueError('Parent is no longer DRAFT.')):
            post('edit_purchase_order_item_cost_route', {'unit_cost':'1'}, 'DRAFT', purchase_order_id=oid, purchase_order_item_id=oi)
        print('PASS route validation errors and status-race error handling')

        # Step 3: real repository quantities and linked-order navigation rendered
        # through the existing permission decorators, using only this server.
        with client.session_transaction() as session:
            session['permissions'] = ['procurement.view', 'procurement.orders.manage', 'procurement.receipts.manage']
        rid, oid, oi = order()
        path = f'/procurement/orders/{oid}'
        request_path = f'/procurement/requests/{rid}'
        html = client.get(request_path).get_data(as_text=True)
        assert po.get_purchase_orders_by_request(rid)[0]['purchase_order_id'] == oid
        assert f'/procurement/orders/{oid}' in html
        assert f'/procurement/requests/{rid}/create-order' not in html
        assert client.get(request_path+'/create-order').location.endswith(path)
        html = client.get(path).get_data(as_text=True)
        assert 'Mark as Sent' in html and f'/procurement/orders/{oid}/cancel' in html
        assert client.post(path+'/send').status_code == 302
        assert po.get_purchase_order_by_id(oid)['status'] == 'SENT'
        html = client.get(path).get_data(as_text=True)
        assert f'/procurement/receipts/{oid}/receive' in html
        receive(oid, 1, 1, {oi:'4.25'})
        item = po.get_purchase_order_items(oid)[0]
        assert item['received_quantity'] == Decimal('4.25') and item['remaining_quantity'] == Decimal('6')
        html = client.get(path).get_data(as_text=True)
        assert 'class="received-quantity">4.25 pcs' in html
        assert 'class="remaining-quantity">6.00 pcs' in html
        assert f'/procurement/orders/{oid}/cancel' not in html
        receive(oid, 1, 1, {oi:'6'})
        item = po.get_purchase_order_items(oid)[0]
        assert item['received_quantity'] == Decimal('10.25') and item['remaining_quantity'] == 0
        html = client.get(path).get_data(as_text=True)
        assert f'/procurement/receipts/{oid}/receive' not in html
        assert 'Received' in html
        printable = client.get(path+'/print')
        assert printable.status_code == 200
        assert '25.63' in printable.get_data(as_text=True)
        assert po.get_purchase_order_by_id(oid)['status'] == 'RECEIVED'
        # Cancelled history remains linked but permits a replacement active PO.
        rid, oid, oi = order()
        assert client.post(f'/procurement/orders/{oid}/cancel').status_code == 302
        html = client.get(f'/procurement/requests/{rid}').get_data(as_text=True)
        assert 'Cancelled' in html and f'/procurement/requests/{rid}/create-order' in html
        response = client.post(f'/procurement/requests/{rid}/create-order', data={'supplier_id':'1'})
        assert response.status_code == 302
        linked = po.get_purchase_orders_by_request(rid)
        assert len(linked) == 2 and [row['status'] for row in linked] == ['DRAFT','CANCELLED']
        print('PASS PO UI transitions, linked orders/replacement, receipt quantities and printable totals on real MySQL')


    print('SUCCESS: procurement checks passed on disposable MySQL; company database never accessed')


if __name__ == '__main__':
    harness.run = run
    harness.main()

