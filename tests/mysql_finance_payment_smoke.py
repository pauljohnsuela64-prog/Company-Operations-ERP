"""Atomic payments on a fresh, verified disposable MySQL instance only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
from decimal import Decimal
import importlib
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur = connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_finance_payment')
        cur.execute('USE erp_finance_payment')
        for name in ['core', 'inventory', 'procurement', 'finance', 'budget', 'audit_logs']:
            text = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', text).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        connection.commit()
    options['database'] = 'erp_finance_payment'
    local = threading.local()

    class Cursor:
        def __init__(self, cursor): self.cursor = cursor
        def __getattr__(self, name): return getattr(self.cursor, name)
        def execute(self, query, params=()):
            normalized = ' '.join(query.split())
            watch = getattr(local, 'watch', None)
            if watch and watch[0] in normalized:
                watch[1].set()
            result = self.cursor.execute(query, params)
            if getattr(local, 'fail_update', False) and normalized.startswith("UPDATE expenses SET status = 'PAID'"):
                raise mysql.connector.DatabaseError('Injected failure after real UPDATE', errno=1644)
            return result

    class Connection:
        def __init__(self): self.connection = mysql.connector.connect(**options)
        def __getattr__(self, name): return getattr(self.connection, name)
        def cursor(self, **kwargs): return Cursor(self.connection.cursor(**kwargs))
        def commit(self):
            hold = getattr(local, 'hold_commit', None)
            if hold:
                local.hold_commit = None
                hold[0].set()
                assert hold[1].wait(15), 'Commit release timed out'
            if getattr(local, 'fail_commit', False):
                raise mysql.connector.DatabaseError('Injected failure before COMMIT', errno=1644)
            self.connection.commit()

    def sql(query, params=(), fetch=False):
        with mysql.connector.connect(**options) as connection:
            cur = connection.cursor()
            cur.execute(query, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            return result

    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'Payer'),(2,'Viewer')")
    for uid in [1, 2]:
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES (%s,%s,%s,%s)',
            (uid, uid, f'finance-{uid}', 'synthetic-only'))
    sql("INSERT INTO permissions(permission_code) VALUES ('finance.expenses.pay')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES (1,'TEST','Test')")

    def department(amount='100.00', year=2026):
        did = sql("INSERT INTO departments(department_code,department_name) VALUES (LEFT(UUID(),20),UUID())")
        if amount is not None:
            sql('INSERT INTO department_budgets(department_id,budget_year,budget_amount,created_by) VALUES (%s,%s,%s,1)',
                (did, year, Decimal(amount)))
        return did

    def expense(did, amount='60.00', status='APPROVED', when='2026-01-01'):
        return sql("INSERT INTO expenses(expense_number,expense_date,category_id,department_id,description,amount,status,created_by) VALUES (UUID(),%s,1,%s,'Synthetic',%s,%s,1)",
                   (when, did, Decimal(amount), status))

    def state(eid):
        return sql('SELECT status,paid_at FROM expenses WHERE expense_id=%s', (eid,), True)[0]

    def audits():
        return sql("SELECT COUNT(*) FROM audit_logs WHERE module='FINANCE' AND action='MARK_PAID'", fetch=True)[0][0]

    def lock_budget(did):
        c = mysql.connector.connect(**options)
        c.start_transaction()
        cur = c.cursor()
        cur.execute('SELECT budget_id FROM department_budgets WHERE department_id=%s FOR UPDATE', (did,))
        cur.fetchall()
        return c

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-finance-payments', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=Connection))
        erp = importlib.import_module('app')
        expenses = importlib.import_module('expense_repository')
        budgets = importlib.import_module('budget_repository')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        stack.enter_context(patch.object(erp.app.logger, 'exception'))

        def client(uid=1):
            c = erp.app.test_client()
            with c.session_transaction() as sess:
                stamp_session(erp.app, sess, user_state(user_id=uid, role_id=uid,
                              username=f'finance-{uid}', password_hash='synthetic-only'))
            return c

        def pay(eid, **probes):
            for key, value in probes.items(): setattr(local, key, value)
            try:
                c = client()
                response = c.post(f'/finance/expenses/{eid}/paid', data={'csrf_token': csrf_token_for(c)})
                assert response.status_code == 302
                with c.session_transaction() as sess:
                    messages = sess.get('_flashes', [])
                return any(category == 'success' for category, _ in messages), str(messages)
            finally:
                for key in probes: delattr(local, key)

        did = department()
        good = expense(did, '100.00')
        count = audits()
        assert pay(good)[0] and state(good)[0] == 'PAID' and audits() == count + 1
        assert not pay(good)[0] and audits() == count + 1
        over = expense(did, '0.01')
        result = pay(over)
        assert not result[0] and '\u20b10.01' in result[1] and state(over) == ('APPROVED', None)
        missing = expense(department(None))
        result = pay(missing)
        assert not result[0] and 'does not have a budget for 2026' in result[1]
        assert audits() == count + 1
        no_dept = expense(None)
        assert pay(no_dept)[0]
        # Only paid expenses count, dates rather than pay date determine the year.
        exact = department('0.30')
        expense(exact, '999.00', status='APPROVED')
        expense(exact, '999.00', status='PAID', when='2025-12-31')
        assert pay(expense(exact, '0.10'))[0]
        assert pay(expense(exact, '0.20'))[0]
        assert not pay(expense(exact, '0.01'))[0]
        assert not pay(expense(exact, '0.01', when='2027-01-01'))[0]
        print('PASS valid/missing/insufficient/departmentless/duplicate, exact Decimal 0.10+0.20, annual date and paid-only policies')

        # Force two real payer transactions to queue on the same locked budget.
        for iteration in range(3):
            did = department()
            ids = [expense(did), expense(did)]
            events = [threading.Event(), threading.Event()]
            held = lock_budget(did)
            count = audits()
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(pay, eid, watch=('FROM department_budgets', event)) for eid, event in zip(ids, events)]
                try:
                    assert all(event.wait(10) for event in events)
                    deadline = time.monotonic() + 8
                    while sql("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_state='LOCK WAIT'", fetch=True)[0][0] < 2:
                        assert time.monotonic() < deadline, 'Both transactions must really be waiting in InnoDB'
                        time.sleep(0.05)
                    assert not any(f.done() for f in futures)
                finally:
                    held.commit(); held.close()
                results = [f.result(timeout=15) for f in futures]
            assert sum(result[0] for result in results) == 1, results
            assert sorted(state(eid)[0] for eid in ids) == ['APPROVED', 'PAID']
            assert audits() == count + 1
            spent = sql("SELECT SUM(amount) FROM expenses WHERE department_id=%s AND status='PAID'", (did,), True)[0][0]
            assert spent == Decimal('60.00')
        print('PASS 3 simultaneous same-budget races: two observed InnoDB LOCK WAIT transactions; exactly one 60/100 payment commits, one rejects, one audit')

        # The same expense cannot be paid twice, even when submitted concurrently.
        eid = expense(department())
        barrier = threading.Barrier(2)
        def same():
            barrier.wait(5)
            return pay(eid)
        count = audits()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(same) for _ in range(2)]
            assert sum(f.result(timeout=15)[0] for f in futures) == 1
        assert audits() == count + 1

        # Holding budget A does not block a payment against B.
        da, db = department(), department()
        ea, eb = expense(da), expense(db)
        held, waiting = lock_budget(da), threading.Event()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fa = pool.submit(pay, ea, watch=('FROM department_budgets', waiting))
            try:
                assert waiting.wait(10)
                assert pool.submit(pay, eb).result(timeout=10)[0]
                assert not fa.done()
            finally:
                held.commit(); held.close()
            assert fa.result(timeout=15)[0]
        print('PASS concurrent duplicate rejection and different-budget payments remain independent')

        # An actual budget edit holds its row until commit; the waiting payer
        # must see the edited amount, not a repeatable-read snapshot of 100.
        did = department()
        eid = expense(did)
        bid = sql('SELECT budget_id FROM department_budgets WHERE department_id=%s', (did,), True)[0][0]
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def edit_budget():
            local.hold_commit = (entered, release)
            try: budgets.update_department_budget(bid, did, 2026, Decimal('50.00'), None)
            finally: del local.hold_commit
        count = audits()
        with ThreadPoolExecutor(max_workers=2) as pool:
            editor = pool.submit(edit_budget)
            try:
                assert entered.wait(10)
                payer = pool.submit(pay, eid, watch=('FROM department_budgets', waiting))
                assert waiting.wait(10) and not payer.done()
            finally: release.set()
            editor.result(timeout=15)
            assert not payer.result(timeout=15)[0]
        assert state(eid) == ('APPROVED', None) and audits() == count

        # Conversely, a payment holds the budget through commit; a later edit
        # remains allowed to lower the budget under the pre-existing edit policy.
        did = department()
        eid = expense(did)
        bid = sql('SELECT budget_id FROM department_budgets WHERE department_id=%s', (did,), True)[0][0]
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def later_edit():
            local.watch = ('SELECT budget_id', waiting)
            try: budgets.update_department_budget(bid, did, 2026, Decimal('50.00'), None)
            finally: del local.watch
        with ThreadPoolExecutor(max_workers=2) as pool:
            payer = pool.submit(pay, eid, hold_commit=(entered, release))
            try:
                assert entered.wait(10)
                editor = pool.submit(later_edit)
                assert waiting.wait(10) and not editor.done()
            finally: release.set()
            assert payer.result(timeout=15)[0]
            editor.result(timeout=15)
        assert state(eid)[0] == 'PAID'
        print('PASS concurrent budget edits serialize in both orders; existing post-payment budget-reduction policy preserved')

        # Moving the matching budget to another year must not pay using its old key.
        did = department()
        eid = expense(did)
        bid = sql('SELECT budget_id FROM department_budgets WHERE department_id=%s', (did,), True)[0][0]
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def move_budget():
            local.hold_commit = (entered, release)
            try: budgets.update_department_budget(bid, did, 2027, Decimal('100.00'), None)
            finally: del local.hold_commit
        count = audits()
        with ThreadPoolExecutor(max_workers=2) as pool:
            mover = pool.submit(move_budget)
            try:
                assert entered.wait(10)
                payer = pool.submit(pay, eid, watch=('FROM department_budgets', waiting))
                assert waiting.wait(10) and not payer.done()
            finally: release.set()
            mover.result(timeout=15)
            result = payer.result(timeout=15)
            assert not result[0] and 'does not have a budget for 2026' in result[1]
        assert state(eid) == ('APPROVED', None) and audits() == count

        # Creation of a matching budget is resolved by InnoDB's unique-key lock.
        did = department(None)
        eid = expense(did)
        creator = mysql.connector.connect(**options)
        creator.start_transaction()
        cur = creator.cursor()
        cur.execute('INSERT INTO department_budgets(department_id,budget_year,budget_amount,created_by) VALUES (%s,2026,100,1)', (did,))
        waiting = threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pay, eid, watch=('FROM department_budgets', waiting))
            try: assert waiting.wait(10) and not future.done()
            finally: creator.commit(); creator.close()
            assert future.result(timeout=15)[0]

        did = department(None)
        eid = expense(did)
        creator = mysql.connector.connect(**options)
        creator.start_transaction()
        cur = creator.cursor()
        cur.execute('INSERT INTO department_budgets(department_id,budget_year,budget_amount,created_by) VALUES (%s,2026,100,1)', (did,))
        waiting = threading.Event()
        count = audits()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(pay, eid, watch=('FROM department_budgets', waiting))
            try: assert waiting.wait(10) and not future.done()
            finally: creator.rollback(); creator.close()
            assert not future.result(timeout=15)[0]
        assert state(eid) == ('APPROVED', None) and audits() == count

        # A draft edit cannot race a payment into accepting stale approval/data.
        eid = expense(department(), status='DRAFT')
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def edit_expense():
            local.hold_commit = (entered, release)
            try: expenses.update_expense(eid, '2027-01-01', 1, None, None, None, 'Edited', Decimal('99.99'), None, None, None)
            finally: del local.hold_commit
        with ThreadPoolExecutor(max_workers=2) as pool:
            editor = pool.submit(edit_expense)
            try:
                assert entered.wait(10)
                payer = pool.submit(pay, eid, watch=('FROM expenses WHERE expense_id', waiting))
                assert waiting.wait(10) and not payer.done()
            finally: release.set()
            editor.result(timeout=15)
            assert not payer.result(timeout=15)[0]
        assert state(eid) == ('DRAFT', None)

        # The opposite order: a draft editor queued behind a committed payment
        # rechecks PAID and cannot change amount/date/department afterwards.
        did = department()
        eid = expense(did)
        entered, release, waiting = threading.Event(), threading.Event(), threading.Event()
        def rejected_edit():
            local.watch = ('FROM expenses', waiting)
            try:
                try: expenses.update_expense(eid, '2027-01-01', 1, None, None, None, 'Invalid edit', Decimal('99.99'), None, None, None)
                except ValueError as error: return str(error)
                raise AssertionError('Paid expense edit succeeded')
            finally: del local.watch
        with ThreadPoolExecutor(max_workers=2) as pool:
            payer = pool.submit(pay, eid, hold_commit=(entered, release))
            try:
                assert entered.wait(10)
                editor = pool.submit(rejected_edit)
                assert waiting.wait(10) and not editor.done()
            finally: release.set()
            assert payer.result(timeout=15)[0]
            assert 'Only draft expenses' in editor.result(timeout=15)
        assert sql('SELECT amount,expense_date,department_id FROM expenses WHERE expense_id=%s', (eid,), True)[0] == (Decimal('60.00'), date(2026, 1, 1), did)
        print('PASS concurrent budget key move, budget creation commit/rollback and draft expense edit/payment interactions')

        for failure in ['fail_update', 'fail_commit']:
            eid = expense(department())
            count = audits()
            try: pay(eid, **{failure: True})
            except mysql.connector.DatabaseError: pass
            else: raise AssertionError('Injected failure must escape and roll back')
            assert state(eid) == ('APPROVED', None) and audits() == count
            assert pay(eid)[0]  # Locks released; valid retry succeeds once.

        eid = expense(department())
        count = audits()
        with patch.object(erp, 'create_audit_log', side_effect=RuntimeError('Synthetic audit outage')):
            assert pay(eid)[0]
        assert state(eid)[0] == 'PAID' and audits() == count
        assert not pay(eid)[0] and audits() == count

        eid = expense(department())
        count = audits()
        denied, allowed = client(2), client()
        for token in [None, 'forged']:
            assert allowed.post(f'/finance/expenses/{eid}/paid', data={} if token is None else {'csrf_token': token}).status_code == 400
        token = csrf_token_for(denied)
        assert denied.post(f'/finance/expenses/{eid}/paid', data={'csrf_token': token}).location.endswith('/dashboard')
        token = csrf_token_for(allowed)
        sql('DELETE FROM role_permissions WHERE role_id=1')
        assert allowed.post(f'/finance/expenses/{eid}/paid', data={'csrf_token': token}).location.endswith('/dashboard')
        assert state(eid) == ('APPROVED', None) and audits() == count
        print('PASS real UPDATE/COMMIT failure rollback, released locks, forged POST/CSRF/revocation and zero rejected-payment success audits')
    print('SUCCESS: atomic Finance payment checks used disposable MySQL only')


if __name__ == '__main__':
    harness.run = run
    harness.main()
