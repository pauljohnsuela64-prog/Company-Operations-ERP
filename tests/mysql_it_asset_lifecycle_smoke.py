"""Asset lifecycle integrity and real lock-wait races on disposable MySQL only."""
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


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur = connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_it_lifecycle')
        cur.execute('USE erp_it_lifecycle')
        for name in ['core', 'it_assets', 'it_asset_assignment', 'it_asset_maintenance', 'audit_logs']:
            for statement in re.sub(r'--[^\n]*', '', (harness.ROOT/'database'/f'{name}_schema.sql').read_text()).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        connection.commit()
    options['database'] = 'erp_it_lifecycle'
    def connect():
        return mysql.connector.connect(**options)
    def sql(query, params=(), fetch=False):
        with connect() as c:
            cur = c.cursor(); cur.execute(query, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            c.commit()
            return result
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Manager'),(2,'Viewer')")
    sql("INSERT INTO permissions(permission_code) VALUES('it_assets.view'),('it_assets.manage')")
    sql('INSERT INTO role_permissions SELECT 1,permission_id FROM permissions')
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code='it_assets.view'")
    for uid in [1,2]:
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES(%s,%s,%s,\'synthetic\')', (uid,uid,f'life-{uid}'))
        sql('INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(%s,%s,\'Synthetic\',\'Employee\')', (uid,f'LIFE-{uid}'))
    sql("INSERT INTO departments(department_id,department_code,department_name) VALUES(1,'LIFE','Lifecycle')")
    sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES(1,'LIFE','Lifecycle')")
    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-it-lifecycle', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        erp = importlib.import_module('app')
        repo = importlib.import_module('it_asset_repository')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        def asset(assigned=True, status=None):
            return repo.create_it_asset(uuid.uuid4().hex, 'Synthetic asset', 1, None, None, None,
                1, 1 if assigned else None, None, None, None,
                status or ('ASSIGNED' if assigned else 'AVAILABLE'), 'GOOD', None, 1)
        def state(aid):
            return sql('SELECT status,assigned_employee_id,department_id FROM it_assets WHERE asset_id=%s', (aid,), True)[0]
        def active(aid):
            return sql('SELECT assignment_id FROM it_asset_assignments WHERE asset_id=%s AND returned_at IS NULL', (aid,), True)[0][0]
        def returned(aid, assignment=None):
            return repo.unassign_it_asset(aid, 1, assignment if assignment is not None else active(aid))
        def maintain(aid):
            return repo.create_it_asset_maintenance(aid, 'Repair', 'Synthetic repair', None, None, '2026-10-01', None, 1)
        def snapshot():
            return [sql('SELECT * FROM '+table+' ORDER BY 1', fetch=True) for table in
                    ['it_assets', 'it_asset_assignments', 'it_asset_maintenance', 'audit_logs']]
        def rejects(action):
            before = snapshot()
            try:
                action()
            except ValueError:
                pass
            else:
                raise AssertionError('Expected rejected transition')
            assert snapshot() == before

        # Returned asset ID must not become the history INSERT's auto-increment ID.
        sql('ALTER TABLE it_asset_assignments AUTO_INCREMENT=1000')
        aid = asset(); assignment = active(aid)
        assert assignment != aid
        assert sql('SELECT employee_id,department_id,assigned_by,returned_at FROM it_asset_assignments WHERE assignment_id=%s', (assignment,), True) == [(1,1,1,None)]
        returned(aid, assignment)
        assert state(aid) == ('AVAILABLE',None,1)
        assert sql('SELECT returned_by,returned_at IS NOT NULL FROM it_asset_assignments WHERE assignment_id=%s', (assignment,), True) == [(1,1)]
        rejects(lambda: returned(aid, assignment))
        repo.assign_it_asset(aid, 1, 1, 1)
        new_assignment = active(aid)
        rejects(lambda: returned(aid, assignment))  # ABA: same employee, new custody.
        returned(aid, new_assignment)
        for status in ['LOST','MAINTENANCE','RETIRED']:
            a = asset()
            if status == 'LOST': repo.mark_it_asset_lost(a)
            elif status == 'MAINTENANCE': mid = maintain(a)
            else: sql("UPDATE it_assets SET status='RETIRED' WHERE asset_id=%s", (a,))  # legacy anomaly fixture only
            assignment = active(a)
            returned(a, assignment)
            assert state(a) == (status,None,1)
            rejects(lambda: returned(a, assignment))
            if status == 'MAINTENANCE': repo.complete_it_asset_maintenance(mid, '2026-10-02')
            else: repo.restore_it_asset(a)
            assert state(a)[0] == 'AVAILABLE'
        a = asset(); mid = maintain(a)
        repo.complete_it_asset_maintenance(mid, '2026-10-02')
        assert state(a)[0] == 'ASSIGNED'
        rejects(lambda: repo.complete_it_asset_maintenance(mid, '2026-10-02'))
        returned(a)
        print('PASS atomic initial history/asset ID, normal return, LOST/MAINTENANCE/RETIRED custody returns preserve lifecycle, restore/completion, duplicates and stale same-employee forms')

        for anomaly in ['missing', 'duplicate', 'employee', 'open-maintenance']:
            a = asset(); assignment = active(a)
            if anomaly == 'missing': sql('DELETE FROM it_asset_assignments WHERE asset_id=%s', (a,))
            elif anomaly == 'duplicate': sql('INSERT INTO it_asset_assignments(asset_id,employee_id,assigned_by) VALUES(%s,1,1)', (a,))
            elif anomaly == 'employee': sql('UPDATE it_asset_assignments SET employee_id=2 WHERE asset_id=%s', (a,))
            else:
                maintain(a)
                sql("UPDATE it_assets SET status='ASSIGNED' WHERE asset_id=%s", (a,))
            rejects(lambda: returned(a, assignment))
        a = asset(); sql("UPDATE it_assets SET status='AVAILABLE',assigned_employee_id=NULL WHERE asset_id=%s", (a,))
        rejects(lambda: repo.assign_it_asset(a, 2, 1, 1))
        a = asset(); mid = maintain(a)
        sql("UPDATE it_assets SET status='LOST' WHERE asset_id=%s", (a,))
        rejects(lambda: repo.complete_it_asset_maintenance(mid, '2026-10-02'))
        a = asset(); mid = maintain(a)
        sql("INSERT INTO it_asset_maintenance(asset_id,maintenance_type,description,start_date,created_by) VALUES(%s,'Repair','Legacy duplicate','2026-10-01',1)", (a,))
        rejects(lambda: repo.complete_it_asset_maintenance(mid, '2026-10-02'))
        print('PASS missing/duplicate/mismatched history and contradictory maintenance states fail closed without altering historical records')

        before = snapshot()
        sql("CREATE TRIGGER fail_initial_assignment BEFORE INSERT ON it_asset_assignments FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic history failure'")
        try:
            try: asset()
            except mysql.connector.Error: pass
            else: raise AssertionError('Expected history INSERT failure')
        finally: sql('DROP TRIGGER fail_initial_assignment')
        assert snapshot() == before
        a = asset(); assignment = active(a); before = snapshot()
        sql("CREATE TRIGGER fail_return_asset BEFORE UPDATE ON it_assets FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic late failure'")
        try:
            try: returned(a, assignment)
            except mysql.connector.Error: pass
            else: raise AssertionError('Expected late UPDATE failure')
        finally: sql('DROP TRIGGER fail_return_asset')
        assert snapshot() == before
        class CommitFailure:
            def __init__(self): self.inner = connect()
            def __getattr__(self, key): return getattr(self.inner, key)
            def commit(self): raise RuntimeError('Synthetic pre-commit failure')
        with patch.object(repo, 'get_connection', side_effect=CommitFailure):
            try: returned(a, assignment)
            except RuntimeError: pass
            else: raise AssertionError('Expected COMMIT failure')
        assert snapshot() == before
        returned(a, assignment)
        print('PASS real initial-history and late-return SQL failures plus pre-COMMIT failure roll back business/history writes and release locks')

        def race(aid, first, second):
            # Both transactions must actually wait behind the same locked asset.
            holder = connect(); holder.start_transaction()
            cur = holder.cursor(); cur.execute('SELECT asset_id FROM it_assets WHERE asset_id=%s FOR UPDATE', (aid,)); cur.fetchall()
            started = [threading.Event(), threading.Event()]
            def invoke(index, operation):
                started[index].set()
                try: operation(); return 'committed'
                except ValueError: return 'rejected'
            try:
                with ThreadPoolExecutor(2) as pool:
                    futures = [pool.submit(invoke, i, op) for i, op in enumerate([first,second])]
                    try:
                        assert all(event.wait(3) for event in started)
                        deadline = time.monotonic()+8
                        while True:
                            waits = sql("SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) FROM performance_schema.data_lock_waits WHERE ENGINE='INNODB'", fetch=True)[0][0]
                            if waits >= 2: break
                            if time.monotonic() > deadline:
                                print('Race process diagnostics:', sql('SHOW FULL PROCESSLIST', fetch=True))
                                print('Race lock diagnostics:', sql('SELECT * FROM performance_schema.data_lock_waits', fetch=True))
                                raise AssertionError(f'Two InnoDB waits required: waits={waits}, completed={[f.result() if f.done() else "waiting" for f in futures]}')
                            time.sleep(0.05)
                        assert not any(future.done() for future in futures)
                    finally:
                        holder.commit()
                    results = [future.result(timeout=10) for future in futures]
            finally:
                holder.rollback(); cur.close(); holder.close()
            return results
        a = asset(); assignment = active(a)
        assert sorted(race(a, lambda: returned(a, assignment), lambda: returned(a, assignment))) == ['committed','rejected']
        a = asset(); assignment = active(a)
        assert race(a, lambda: maintain(a), lambda: returned(a, assignment)) == ['committed','committed']
        assert state(a)[:2] == ('MAINTENANCE',None)
        a = asset(); assignment = active(a); mid = maintain(a)
        assert race(a, lambda: repo.complete_it_asset_maintenance(mid,'2026-10-02'), lambda: returned(a,assignment)) == ['committed','committed']
        assert state(a)[:2] == ('AVAILABLE',None)
        a = asset(); assignment = active(a)
        results = race(a, lambda: repo.assign_it_asset(a,2,1,1), lambda: returned(a,assignment))
        assert results[1] == 'committed'
        assert state(a)[:2] in [('AVAILABLE',None),('ASSIGNED',2)]
        if state(a)[1] == 2: assert active(a) != assignment
        a = asset(False)
        race(a, lambda: repo.assign_it_asset(a,2,1,1), lambda: maintain(a))
        assert state(a)[0] == 'MAINTENANCE'
        assert sql('SELECT COUNT(*) FROM it_asset_assignments WHERE asset_id=%s AND returned_at IS NULL', (a,), True)[0][0] == (1 if state(a)[1] == 2 else 0)
        a = asset(); assignment = active(a)
        assert race(a, lambda: repo.mark_it_asset_lost(a), lambda: returned(a,assignment)) == ['committed','committed']
        assert state(a)[:2] == ('LOST',None)
        print('PASS six actual two-waiter MySQL races: duplicate returns, maintenance/return, completion/return, assignment/return, assignment/maintenance, loss/return')

        def client(uid):
            c = erp.app.test_client()
            with c.session_transaction() as sess:
                stamp_session(erp.app,sess,user_state(user_id=uid,role_id=uid,username=f'life-{uid}',password_hash='synthetic'))
            return c
        manager, viewer = client(1), client(2)
        a = asset(); assignment = active(a)
        html = manager.get(f'/it/assets/{a}').get_data(as_text=True)
        assert f'name="assignment_id" value="{assignment}"' in html
        assert 'name="assignment_id"' not in viewer.get(f'/it/assets/{a}').get_data(as_text=True)
        body = dict(assignment_id=assignment,csrf_token=csrf_token_for(manager))
        path = f'/it/assets/{a}/unassign'; before = snapshot()
        assert manager.post(path,data={'assignment_id':assignment}).status_code == 400
        assert viewer.post(path,data=dict(body,csrf_token=csrf_token_for(viewer))).location.endswith('/dashboard')
        assert snapshot() == before
        assert manager.post(path,data={'csrf_token':body['csrf_token']}).status_code == 302
        with manager.session_transaction() as sess:
            assert not any(kind=='success' for kind,_ in sess.get('_flashes',[]))
        assert snapshot() == before
        sql("DELETE rp FROM role_permissions rp JOIN permissions p USING(permission_id) WHERE role_id=1 AND permission_code='it_assets.manage'")
        assert manager.post(path,data=body).location.endswith('/dashboard')
        assert snapshot() == before
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert manager.post(path,data=body).location.endswith('/login')
        assert snapshot() == before
        assert sql('SELECT COUNT(*) FROM audit_logs',fetch=True) == [(0,)]
        print('PASS rendered assignment token, viewer controls/forged POST, missing token, CSRF, real revocation/disabled account and zero false success/audit writes')
    print('SUCCESS: asset lifecycle checks used synthetic disposable MySQL only')


if __name__ == '__main__':
    harness.run = run
    harness.main()
