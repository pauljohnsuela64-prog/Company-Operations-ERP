"""Existing payroll nonoverlap rule under concurrent writes; disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import date
import importlib
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_cleanup_payroll_schedule')
        cur.execute('USE erp_cleanup_payroll_schedule')
        for name in ('core', 'payroll_period'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic payroll operator')")
        cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'synthetic-payroll','test-only')")
        cur.execute("INSERT INTO permissions(permission_code) VALUES('payroll.process')")
        db.commit()
    options['database'] = 'erp_cleanup_payroll_schedule'

    def connect():
        return mysql.connector.connect(**options)

    def sql(statement, params=(), fetch=False):
        with connect() as db:
            cur = db.cursor()
            cur.execute(statement, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            db.commit()
            return result

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        repo = importlib.import_module('payroll_period_repository')
        stack.enter_context(patch.object(repo, 'get_connection', side_effect=connect))
        start, end, payday = date(2026, 1, 1), date(2026, 1, 15), date(2026, 1, 16)
        barrier = threading.Barrier(2)

        def create(name):
            # Both HTTP-style preflight checks pass before either writer begins.
            assert repo.has_overlapping_payroll_period(start, end) is None
            barrier.wait(timeout=10)
            try:
                return repo.create_payroll_period(name, start, end, payday, None, 1)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, ('Concurrent A', 'Concurrent B')))
        assert sum(value is not None for value in outcomes) == 1, outcomes
        assert sql("SELECT COUNT(*) FROM payroll_periods WHERE status<>'CANCELLED'", fetch=True) == [(1,)]
        print('PASS both preflight checks pass; concurrent payroll creates commit exactly one nonoverlapping period')

        with connect() as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            blocker.start_transaction()
            cur = blocker.cursor()
            cur.execute("SELECT permission_id FROM permissions WHERE permission_code='payroll.process' FOR UPDATE")
            cur.fetchone()
            future = pool.submit(repo.create_payroll_period, 'Observed wait', date(2028, 1, 1),
                                 date(2028, 1, 15), date(2028, 1, 16), None, 1)
            try:
                deadline = time.monotonic() + 10
                while not sql("""SELECT COUNT(*) FROM performance_schema.data_lock_waits w
                    JOIN performance_schema.data_locks r ON r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID AND r.ENGINE=w.ENGINE
                    WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME='permissions'""", fetch=True)[0][0]:
                    assert time.monotonic() < deadline, 'Schedule writer did not enter observed InnoDB lock wait'
                    time.sleep(0.02)
                assert not future.done()
            finally:
                blocker.rollback()
            assert future.result(timeout=10)
        print('PASS observed actual InnoDB wait on the existing schedule writer gate')

        for isolation in ('REPEATABLE READ', 'READ COMMITTED'):
            options['init_command'] = 'SET SESSION TRANSACTION ISOLATION LEVEL ' + isolation
            sql('DELETE FROM payroll_periods')  # This isolated suite has synthetic rows only.
            first = repo.create_payroll_period('January', start, end, payday, None, 1)
            target_start, target_end, target_pay = date(2026, 2, 1), date(2026, 2, 15), date(2026, 2, 16)
            barrier = threading.Barrier(2)

            def contend(editing):
                assert repo.has_overlapping_payroll_period(target_start, target_end, first if editing else None) is None
                barrier.wait(timeout=10)
                try:
                    args = ('Moved January' if editing else 'February', target_start, target_end, target_pay, None, 1)
                    return repo.update_payroll_period(first, *args) if editing else repo.create_payroll_period(*args)
                except repo.PayrollScheduleError as error:
                    assert error.status_code == 409
                    return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(contend, (False, True)))
            assert sum(value is not None for value in outcomes) == 1, outcomes
            assert sql('SELECT COUNT(*) FROM payroll_periods WHERE start_date=%s', (target_start,), True) == [(1,)]
            print('PASS create/edit schedule race, exactly one winner:', isolation)

            sql('DELETE FROM payroll_periods')
            first = repo.create_payroll_period('January', start, end, payday, None, 1)
            second = repo.create_payroll_period('March', date(2026, 3, 1), date(2026, 3, 15), date(2026, 3, 16), None, 1)
            barrier = threading.Barrier(2)

            def move(identity):
                assert repo.has_overlapping_payroll_period(target_start, target_end, identity) is None
                barrier.wait(timeout=10)
                try:
                    return repo.update_payroll_period(identity, 'Moved ' + str(identity), target_start, target_end, target_pay, None, 1)
                except repo.PayrollScheduleError as error:
                    assert error.status_code == 409
                    return None

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(move, (first, second)))
            assert outcomes.count(True) == 1 and outcomes.count(None) == 1, outcomes
            assert sql('SELECT COUNT(*) FROM payroll_periods WHERE start_date=%s', (target_start,), True) == [(1,)]
            print('PASS competing period edits cannot overlap:', isolation)

        sql('DELETE FROM payroll_periods')
        first = repo.create_payroll_period('Inclusive', start, end, payday, None, 1)
        before = sql('SELECT * FROM payroll_periods', fetch=True)
        try:
            repo.create_payroll_period('Boundary overlap', end, date(2026, 1, 31), date(2026, 2, 1), None, 1)
            raise AssertionError('Inclusive end-date overlap allowed')
        except repo.PayrollScheduleError as error:
            assert error.status_code == 409
        assert sql('SELECT * FROM payroll_periods', fetch=True) == before
        assert repo.update_payroll_period(first, 'Same range', start, end, payday, None, 1)
        repo.create_payroll_period('Adjacent', payday, date(2026, 1, 31), date(2026, 2, 1), None, 1)
        assert repo.cancel_payroll_period(first, 1)
        replacement = repo.create_payroll_period('Replaces cancelled', start, end, payday, None, 1)
        sql("UPDATE payroll_periods SET status='PAID' WHERE period_name='Replaces cancelled'")
        assert not repo.update_payroll_period(replacement, 'Must remain paid', start, end, payday, None, 1)
        assert sql("SELECT period_name,status FROM payroll_periods WHERE period_name='Replaces cancelled'", fetch=True) == [('Replaces cancelled', 'PAID')]
        sql("DELETE FROM permissions WHERE permission_code='payroll.process'")
        before = sql('SELECT * FROM payroll_periods', fetch=True)
        try:
            repo.create_payroll_period('Missing gate', date(2027, 1, 1), date(2027, 1, 15), date(2027, 1, 16), None, 1)
            raise AssertionError('Missing schedule gate allowed a write')
        except repo.PayrollScheduleError as error:
            assert error.status_code == 503
        assert sql('SELECT * FROM payroll_periods', fetch=True) == before
        print('PASS inclusive boundaries, adjacent ranges, self exclusion, cancelled eligibility, paid edit guard and missing gate fail closed')

    print('SUCCESS: payroll schedule regression used only verified disposable MySQL')


if __name__ == '__main__':
    harness.run = run
    harness.main()
