"""PO eligibility/lock ordering on a verified fresh disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
import time
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
        cursor.execute('CREATE DATABASE erp_po_supplier_test')
        cursor.execute('USE erp_po_supplier_test')
        for name in ('core', 'inventory', 'procurement', 'finance', 'budget', 'audit_logs'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                statement = statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b', statement, re.I):
                    cursor.execute(statement)
        connection.commit()
    options['database'] = 'erp_po_supplier_test'
    local = threading.local()

    class Connection:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def commit(self):
            if getattr(local, 'hold', None):
                entered, release = local.hold
                entered.set()
                assert release.wait(15), 'Commit release timed out'
            if getattr(local, 'fail_commit', False):
                raise mysql.connector.Error('Synthetic precommit failure', errno=2013)
            return self.connection.commit()

    def connect():
        return Connection(mysql.connector.connect(**options))

    def sql(query, params=(), fetch=False):
        with mysql.connector.connect(**options) as connection:
            cursor = connection.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall() if fetch else cursor.lastrowid
            connection.commit()
            return result

    def fails(action, message):
        try:
            action()
        except ValueError as error:
            assert message in str(error), str(error)
        else:
            raise AssertionError('Expected rejection')

    def wait_for_lock(table):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            rows = sql('''SELECT r.OBJECT_NAME FROM performance_schema.data_lock_waits w
                JOIN performance_schema.data_locks r
                ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID AND r.ENGINE=w.ENGINE
                WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME=%s''', (table,), True)
            if rows:
                return
            time.sleep(.03)
        raise AssertionError(f'No observed InnoDB wait on {table}')

    def held(action, entered, release):
        local.hold = (entered, release)
        try:
            return action()
        finally:
            local.hold = None

    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'synthetic','unused')")
    sql("INSERT INTO suppliers(supplier_id,supplier_code,supplier_name) VALUES(1,'SYN','Synthetic')")
    sql("INSERT INTO inventory_items(item_id,item_code,item_name) VALUES(1,'SYN','Synthetic')")
    sql("INSERT INTO warehouses(warehouse_id,warehouse_code,warehouse_name) VALUES(1,'SYN','Synthetic')")
    sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES(1,'SYN','Synthetic')")

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        # Fail closed on any accidental use of the configured business connection.
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=AssertionError('Company DB forbidden')))
        pr, po, suppliers, receiving = [importlib.import_module(name) for name in
            ('purchase_request_repository', 'purchase_order_repository', 'supplier_repository', 'goods_receipt_repository')]
        for module in (pr, po, suppliers, receiving):
            stack.enter_context(patch.object(module, 'get_connection', side_effect=connect))

        def approved(items=True):
            rid, _ = pr.create_purchase_request(1, None, 'Synthetic eligibility test')
            if items:
                pr.add_purchase_request_item(rid, 1, '3.25', '2.50', 'Copied note')
            sql("UPDATE purchase_requests SET status='APPROVED' WHERE request_id=%s", (rid,))
            return rid

        def create(rid, supplier=1):
            return po.create_purchase_order_from_request(rid, supplier, 1, notes='PO note')

        def history():
            return [sql('SELECT * FROM ' + table + ' ORDER BY 1', fetch=True) for table in
                ('purchase_orders', 'purchase_order_items', 'goods_receipts', 'goods_receipt_items',
                 'inventory_stock', 'stock_movements', 'expenses', 'audit_logs')]

        rid = approved()
        before = history()
        for supplier in (None, '', True, 0, -1, 'bad', '1.0', 2147483648, 999999):
            fails(lambda: create(rid, supplier), 'supplier')
            assert history() == before
        suppliers.set_supplier_active_status(1, False)
        fails(lambda: create(rid), 'invalid or inactive')
        assert history() == before
        suppliers.set_supplier_active_status(1, True)
        print('PASS missing, malformed, nonexistent and inactive supplier rejection without PO/history writes')

        # Status commits first: the PO owns its PR lock, waits on the supplier,
        # then performs a current read of the committed inactive status.
        entered, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(held, lambda: suppliers.set_supplier_active_status(1, False), entered, release)
            try:
                assert entered.wait(8)
                second = pool.submit(fails, lambda: create(rid), 'invalid or inactive')
                wait_for_lock('suppliers')
                assert not second.done()
            finally:
                release.set()
            assert first.result(timeout=10)
            second.result(timeout=10)
        assert history() == before
        suppliers.set_supplier_active_status(1, True)
        print('PASS deactivation-first observed supplier lock wait, current eligibility rejection and rollback')

        # PO commits first: the real repository has validated and written the PO;
        # its shared supplier lock prevents deactivation until that commit.
        entered, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(held, lambda: create(rid), entered, release)
            try:
                assert entered.wait(8)
                second = pool.submit(suppliers.set_supplier_active_status, 1, False)
                wait_for_lock('suppliers')
                assert not second.done()
            finally:
                release.set()
            oid, number = first.result(timeout=10)
            assert second.result(timeout=10)
        assert number == f'PO-{oid:06d}'
        assert sql('SELECT supplier_id,status,notes FROM purchase_orders WHERE purchase_order_id=%s', (oid,), True) == [(1, 'DRAFT', 'PO note')]
        assert sql('SELECT item_id,quantity,unit_cost,notes FROM purchase_order_items WHERE purchase_order_id=%s', (oid,), True) == [(1, Decimal('3.25'), Decimal('2.50'), 'Copied note')]
        assert sql('SELECT is_active FROM suppliers WHERE supplier_id=1', fetch=True) == [(0,)]
        print('PASS PO-first observed deactivation wait, valid numbering/copied items and subsequent deactivation')

        # Previously created orders remain sendable/receivable for inactive suppliers.
        assert po.send_purchase_order(oid)
        line = po.get_purchase_order_items(oid)[0]['purchase_order_item_id']
        receiving.create_goods_receipt(oid, 1, 1, {line: '3.25'}, submission_id=str(uuid.uuid4()))
        assert po.get_purchase_order_by_id(oid)['status'] == 'RECEIVED'
        assert pr.get_purchase_request_by_id(rid)['status'] == 'COMPLETED'
        assert sql('SELECT quantity FROM inventory_stock', fetch=True) == [(Decimal('3.25'),)]
        sql("INSERT INTO expenses(expense_number,expense_date,category_id,supplier_id,purchase_order_id,description,amount,status,created_by) VALUES('HISTORY','2026-01-01',1,1,%s,'Historical',10,'PAID',1)", (oid,))
        before = history()
        suppliers.set_supplier_active_status(1, True)
        suppliers.set_supplier_active_status(1, False)
        assert history() == before
        suppliers.set_supplier_active_status(1, True)
        print('PASS inactive-supplier historical receiving, PR completion and unchanged financial/inventory history')

        rid = approved()
        before = history()
        sql("CREATE TRIGGER po_supplier_failure BEFORE INSERT ON purchase_order_items FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
        try:
            try:
                create(rid)
            except mysql.connector.Error:
                pass
            else:
                raise AssertionError('Expected SQL failure')
        finally:
            sql('DROP TRIGGER po_supplier_failure')
        assert history() == before
        local.fail_commit = True
        try:
            try:
                create(rid)
            except mysql.connector.Error:
                pass
            else:
                raise AssertionError('Expected precommit failure')
        finally:
            local.fail_commit = False
        assert history() == before
        empty = approved(items=False)
        fails(lambda: create(empty), 'no items')
        assert history() == before
        assert suppliers.set_supplier_active_status(1, False)
        assert suppliers.set_supplier_active_status(1, True)
        print('PASS late SQL/precommit/empty-request rollback and released supplier locks')

        entered, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(held, lambda: create(rid), entered, release)
            try:
                assert entered.wait(8)
                second = pool.submit(fails, lambda: create(rid), 'already exists')
                wait_for_lock('purchase_requests')
                assert not second.done()
            finally:
                release.set()
            first.result(timeout=10)
            second.result(timeout=10)
        assert sql("SELECT COUNT(*) FROM purchase_orders WHERE request_id=%s AND status<>'CANCELLED'", (rid,), True) == [(1,)]
        print('PASS concurrent duplicate conversion waits on PR and creates exactly one active PO')
    print('SUCCESS: PO supplier eligibility on disposable MySQL; company database never accessed')


if __name__ == '__main__':
    harness.run = run
    harness.main()
