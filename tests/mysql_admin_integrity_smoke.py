"""Actual Administration routes and races on a verified disposable MySQL only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
import threading
import time
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_admin_integrity_test')
        cur.execute('USE erp_admin_integrity_test')
        for name in ('core', 'inventory', 'procurement', 'audit_logs'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                statement = statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        db.commit()
    options['database'] = 'erp_admin_integrity_test'
    local = threading.local()

    class Connection:
        def __init__(self, db): self.db = db
        def __getattr__(self, key): return getattr(self.db, key)
        def commit(self):
            if getattr(local, 'hold', None):
                entered, release = local.hold
                entered.set()
                assert release.wait(15), 'Commit release timed out'
            failure = getattr(local, 'failure', None)
            if failure == 'before': raise mysql.connector.Error('Synthetic precommit failure', errno=2013)
            result = self.db.commit()
            if failure == 'after': raise mysql.connector.Error('Synthetic lost commit acknowledgment', errno=2013)
            return result

    def connect():
        db = mysql.connector.connect(**options)
        if getattr(local, 'short_timeout', False):
            cur = db.cursor(); cur.execute('SET SESSION innodb_lock_wait_timeout=1'); cur.close()
        return Connection(db)
    def sql(query, params=(), fetch=False):
        with mysql.connector.connect(**options) as db:
            cur = db.cursor(); cur.execute(query, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            db.commit(); return result
    def events(): return sql("SELECT action,entity_id,description FROM audit_logs WHERE module='ADMINISTRATION' ORDER BY audit_log_id", fetch=True)
    def state(): return sql('SELECT user_id,role_id,is_active,password_hash FROM users ORDER BY user_id', fetch=True)
    def active_count(): return sql('SELECT COUNT(*) FROM users WHERE role_id=1 AND is_active=1', fetch=True)[0][0]
    def wait_for_guard(table='permissions'):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if sql('''SELECT COUNT(*) FROM performance_schema.data_lock_waits w
                JOIN performance_schema.data_locks r ON r.ENGINE=w.ENGINE AND r.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID
                WHERE r.OBJECT_SCHEMA=DATABASE() AND r.OBJECT_NAME=%s ''', (table,), True)[0][0]: return
            time.sleep(.03)
        raise AssertionError('Expected actual InnoDB permission guard wait')

    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Super Admin'),(2,'Operator'),(3,'Employee')")
    sql("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'admin.a','synthetic'),(2,1,'admin.b','synthetic'),(3,2,'operator','synthetic'),(4,3,'target','synthetic')")
    # Synthetic authorization fixtures only, not application/production grants.
    for code in ('users.manage', 'it_assets.view', 'it_assets.manage', 'helpdesk.view', 'helpdesk.manage'):
        pid = sql('INSERT INTO permissions(permission_code) VALUES(%s)', (code,))
        if code == 'users.manage':
            for role in (1, 2): sql('INSERT INTO role_permissions VALUES(%s,%s)', (role, pid))
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-admin-mysql', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        erp = importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        stack.enter_context(patch.object(erp.app.logger, 'exception'))
        def client(uid=3):
            c = csrf_client(erp.app)
            with c.session_transaction() as session: stamp_session(erp.app, session, erp.get_authorization_state(uid))
            return c
        def post(uid, target, kind, value):
            return client(uid).post(f'/admin/users/{target}/{kind}', data={('role_id' if kind == 'role' else 'is_active'): str(value)})
        def hold(action, entered, release):
            local.hold = (entered, release)
            try: return action()
            finally: local.hold = None

        # Authenticate both requests while both admins still have committed access;
        # hold the first at COMMIT, then prove the second is waiting on the gate.
        for first_kind, second_kind in (('status', 'status'), ('role', 'role'), ('role', 'status'), ('status', 'role')):
            sql('UPDATE users SET role_id=1,is_active=1 WHERE user_id IN (1,2)')
            a, b = client(1), client(2)
            entered, release = threading.Event(), threading.Event()
            before = len(events())
            def request(c, target, kind):
                return c.post(f'/admin/users/{target}/{kind}', data={'role_id': '3'} if kind == 'role' else {'is_active': '0'})
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(hold, lambda: request(a, 2, first_kind), entered, release)
                try:
                    assert entered.wait(8)
                    second = pool.submit(request, b, 1, second_kind)
                    wait_for_guard()
                    assert not second.done()
                    assert len(events()) == before
                finally: release.set()
                assert first.result(timeout=10).status_code == 302
                losing = second.result(timeout=10)
                assert losing.status_code == 409, losing.get_data(as_text=True)
            assert active_count() == 1
            assert len(events()) == before + 1
            assert events()[-1][0] == ('UPDATE' if first_kind == 'role' else 'DEACTIVATE')
        print('PASS four observed guard races: cross-deactivation, cross-demotion and both mixed orders; one active admin and one audit remain')

        sql('UPDATE users SET role_id=1,is_active=1 WHERE user_id IN (1,2)')
        before = len(events())
        assert post(3, 2, 'role', 3).status_code == 302 and active_count() == 1
        assert post(3, 1, 'status', 0).status_code == 409 and active_count() == 1
        assert post(3, 2, 'role', 1).status_code == 302 and active_count() == 2
        assert post(3, 2, 'status', 0).status_code == 302 and active_count() == 1
        assert post(3, 2, 'status', 1).status_code == 302 and active_count() == 2
        assert [e[0] for e in events()[before:]] == ['UPDATE', 'UPDATE', 'DEACTIVATE', 'ACTIVATE']
        print('PASS valid changes with remaining admin, reactivation/promotion recovery and last-admin rejection')

        before, audit_before = state(), events()
        for kind, value in (('role', 3), ('status', 1)):
            assert post(3, 4, kind, value).status_code == 302  # Unchanged target.
        for kind in ('role', 'status'):
            assert post(3, 999999, kind, 1).status_code == 404
        assert post(3, 4, 'role', 999999).status_code == 400
        assert post(3, 4, 'role', 'bad').status_code == 400
        c = client()
        for data in ({}, {'is_active': 'bad'}, [('is_active', '0'), ('is_active', '1')]):
            from werkzeug.datastructures import MultiDict
            assert c.post('/admin/users/4/status', data=MultiDict(data)).status_code == 400
        assert post(3, 3, 'role', 1).status_code == 302
        assert post(3, 3, 'status', 0).status_code == 302
        assert state() == before and events() == audit_before
        # Identical and stale explicit deactivation never toggle back on.
        assert post(3, 4, 'status', 0).status_code == 302
        before, audit_before = state(), events()
        assert post(3, 4, 'status', 0).status_code == 302
        assert state() == before and events() == audit_before
        print('PASS missing/invalid targets, self protection, no-op roles and replay-safe explicit status')

        for kind, value in (('role', 2), ('status', 1)):
            before, audit_before = state(), events()
            sql("CREATE TRIGGER admin_write_failure BEFORE UPDATE ON users FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic failure'")
            try: assert post(3, 4, kind, value).status_code == 503
            finally: sql('DROP TRIGGER admin_write_failure')
            assert state() == before and events() == audit_before
            local.failure = 'before'
            try: assert post(3, 4, kind, value).status_code == 503
            finally: local.failure = None
            assert state() == before and events() == audit_before
        print('PASS actual SQL/precommit failure rollback and no success audits for role/status')

        before, audit_before = state(), events()
        def timed_change():
            local.short_timeout = True
            try: return post(3, 4, 'role', 2)
            finally: local.short_timeout = False
        with mysql.connector.connect(**options) as blocker, ThreadPoolExecutor(max_workers=1) as pool:
            cur = blocker.cursor()
            cur.execute("SELECT permission_id FROM permissions WHERE permission_code='users.manage' FOR UPDATE")
            cur.fetchall()
            try:
                waiting = pool.submit(timed_change)
                wait_for_guard()
                assert waiting.result(timeout=8).status_code == 409
            finally: blocker.rollback()
        assert state() == before and events() == audit_before
        print('PASS actual 1205 lock timeout rolls back with conflict and no success audit')

        # Help Desk reads a technician before its role. Both role reads must stay
        # shared while an Administration request waits for the held user record.
        with mysql.connector.connect(**options) as technician, ThreadPoolExecutor(max_workers=1) as pool:
            cur = technician.cursor()
            cur.execute('SELECT user_id FROM users WHERE user_id=2 FOR SHARE'); cur.fetchall()
            try:
                waiting = pool.submit(post, 3, 2, 'status', 0)
                wait_for_guard('users')
                cur.execute('SELECT role_id FROM roles WHERE role_id=1 FOR SHARE'); cur.fetchall()
            finally: technician.commit()
            assert waiting.result(timeout=10).status_code == 302
        assert active_count() == 1
        assert post(3, 2, 'status', 1).status_code == 302
        print('PASS user-then-role shared reads complete while Administration waits, without a role/user lock inversion')

        local.failure = 'after'
        audit_before = events()
        try: assert post(3, 4, 'status', 1).status_code == 503
        finally: local.failure = None
        assert sql('SELECT is_active FROM users WHERE user_id=4', fetch=True) == [(1,)]
        assert events() == audit_before
        assert post(3, 4, 'status', 1).status_code == 302 and events() == audit_before
        print('PASS uncertain committed status reconciles as no-op, no automatic retry or invented audit')

        for kind, value in (('role', 2), ('status', 0)):
            audit_before = events()
            sql("CREATE TRIGGER admin_audit_failure BEFORE INSERT ON audit_logs FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic audit outage'")
            try: assert post(3, 4, kind, value).status_code == 302
            finally: sql('DROP TRIGGER admin_audit_failure')
            assert events() == audit_before
        assert sql('SELECT role_id,is_active FROM users WHERE user_id=4', fetch=True) == [(2, 0)]
        assert all('synthetic' not in str(e) and 'hash' not in e[2] for e in events())
        print('PASS central audit SQL failure isolation; committed role/status retained without sensitive payloads')

        before, audit_before = state(), events()
        denied = client(4)  # Disabled accounts cannot write.
        assert denied.post('/admin/users/1/status', data={'is_active': '0'}).status_code == 302
        raw = erp.app.test_client()
        with raw.session_transaction() as session: stamp_session(erp.app, session, erp.get_authorization_state(3))
        assert raw.post('/admin/users/1/status', data={'is_active': '0'}).status_code == 400
        assert state() == before and events() == audit_before
        print('PASS disabled-account refresh and CSRF block writes')
    print('SUCCESS: Administration integrity used verified disposable MySQL only')


if __name__ == '__main__':
    harness.run = run
    harness.main()
