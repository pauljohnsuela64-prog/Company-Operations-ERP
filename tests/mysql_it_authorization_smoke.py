"""Real routes/templates/repositories on a verified disposable MySQL server only."""
from contextlib import ExitStack
import importlib
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
from werkzeug.security import generate_password_hash

import mysql_audit_smoke as harness
from security_helpers import stamp_session, user_state, csrf_token_for
from test_it_authorization import route_contract


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as connection:
        cur = connection.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_it_authorization')
        cur.execute('USE erp_it_authorization')
        for name in ['core', 'it_assets', 'it_asset_assignment', 'it_asset_maintenance',
                     'help_desk', 'help_desk_history', 'audit_logs']:
            for statement in re.sub(r'--[^\n]*', '', (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()).split(';'):
                statement = statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        connection.commit()
    options['database'] = 'erp_it_authorization'

    def connect():
        return mysql.connector.connect(**options)

    def sql(statement, params=(), fetch=False):
        with connect() as connection:
            cur = connection.cursor()
            cur.execute(statement, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            connection.commit()
            return result

    sql("INSERT INTO roles(role_id,role_name) VALUES (1,'IT Manager'),(2,'Viewer'),(3,'Super Admin'),(4,'Unrelated')")
    migration = (harness.ROOT / 'database/migrations/003_it_helpdesk_permissions.sql').read_text()
    for _ in range(2):
        with connect() as connection:
            cur = connection.cursor()
            for statement in re.sub(r'--[^\n]*', '', migration).split(';'):
                if statement.strip():
                    cur.execute(statement)
    assert sql('SELECT COUNT(*) FROM role_permissions WHERE role_id IN (1,3)', fetch=True) == [(8,)]
    assert sql('SELECT COUNT(*) FROM role_permissions WHERE role_id IN (2,4)', fetch=True) == [(0,)]
    sql("INSERT INTO role_permissions SELECT 2,permission_id FROM permissions WHERE permission_code IN ('it_assets.view','helpdesk.view')")
    password_hash = generate_password_hash('synthetic-test-password')
    for uid, role in [(1, 1), (2, 2), (3, 4)]:
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES (%s,%s,%s,%s)',
            (uid, role, f'test-{uid}', password_hash))
    sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES (1,'SYNTHETIC','Test','Employee')")
    sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES (1,'TEST','Test')")
    sql("INSERT INTO helpdesk_categories(category_id,category_code,category_name) VALUES (1,'TEST','Test')")

    def snapshot():
        return [sql('SELECT * FROM ' + table + ' ORDER BY 1', fetch=True) for table in
                ['it_assets', 'it_asset_categories', 'it_asset_assignments', 'it_asset_maintenance',
                 'helpdesk_tickets', 'helpdesk_ticket_history', 'audit_logs']]

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-it-mysql-test-key', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        erp = importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))

        def client(uid):
            c = erp.app.test_client()
            with c.session_transaction() as mapping:
                stamp_session(erp.app, mapping, user_state(user_id=uid, username=f'test-{uid}',
                              role_id={1: 1, 2: 2, 3: 4}[uid], password_hash=password_hash))
            return c

        manager, viewer, denied = client(1), client(2), client(3)
        mt, vt, dt = [csrf_token_for(c) for c in (manager, viewer, denied)]

        def post(path, body=None):
            response = manager.post(path, data=dict(body or {}, csrf_token=mt))
            assert response.status_code == 302, (path, response.status_code)
            return response

        # Every write route rejects a valid-token viewer/no-permission request.
        before = snapshot()
        for path, methods, permission, _ in route_contract():
            if 'POST' not in methods:
                continue
            for c, token in [(viewer, vt), (denied, dt)]:
                response = c.post(path, data={'csrf_token': token, 'employee_id': '1', 'assigned_to': '1'})
                assert response.status_code == 302 and response.location.endswith('/dashboard'), path
            for token in [None, 'forged']:
                response = manager.post(path, data={} if token is None else {'csrf_token': token})
                assert response.status_code == 400, path
            if 'GET' in methods:
                assert viewer.get(path).location.endswith('/dashboard'), path
        assert snapshot() == before
        print('PASS all 17 forged POST routes, management GET denial and CSRF: no business/history/audit changes')

        # Exercise every management route with genuine repository writes.
        post('/it/assets/categories/add', dict(category_code='NEW', category_name='New'))
        assert sql("SELECT COUNT(*) FROM it_asset_categories WHERE category_code='NEW'", fetch=True) == [(1,)]
        post('/it/assets/categories/1/edit', dict(category_code='TEST', category_name='Updated'))
        assert sql('SELECT category_name FROM it_asset_categories WHERE category_id=1', fetch=True) == [('Updated',)]
        post('/it/assets/categories/1/status')
        assert sql('SELECT is_active FROM it_asset_categories WHERE category_id=1', fetch=True) == [(0,)]
        post('/it/assets/categories/1/status')
        asset_body = dict(asset_tag='SYNTHETIC', asset_name='Test Asset', category_id='1', condition_status='GOOD')
        post('/it/assets/add', asset_body)
        aid = sql("SELECT asset_id FROM it_assets WHERE asset_tag='SYNTHETIC'", fetch=True)[0][0]
        asset_body['asset_name'] = 'Edited Asset'
        post(f'/it/assets/{aid}/edit', asset_body)
        assert sql('SELECT asset_name FROM it_assets WHERE asset_id=%s', (aid,), True) == [('Edited Asset',)]

        def asset_status(expected):
            assert sql('SELECT status FROM it_assets WHERE asset_id=%s', (aid,), True) == [(expected,)]

        # Real rendered controls across available, assigned, maintenance, retired, lost.
        def controls(path, suffix, shown):
            for c, expected in [(viewer, False), (manager, shown)]:
                response = c.get(path)
                assert response.status_code == 200, path
                assert (suffix in response.get_data(as_text=True)) == expected, (path, suffix, expected)

        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/edit', True)
        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/maintenance/add', True)
        controls('/it/assets/categories', '/it/assets/categories/1/edit', True)
        controls('/it/assets/categories', '/it/assets/categories/1/status', True)
        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/assign', True)
        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/retire', True)
        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/lost', True)
        post(f'/it/assets/{aid}/assign', {'employee_id': '1'})
        asset_status('ASSIGNED')
        controls(f'/it/assets/{aid}', f'/it/assets/{aid}/unassign', True)
        post(f'/it/assets/{aid}/unassign')
        asset_status('AVAILABLE')
        assert sql('SELECT COUNT(*) FROM it_asset_assignments WHERE returned_at IS NOT NULL', fetch=True) == [(1,)]
        post(f'/it/assets/{aid}/maintenance/add', dict(maintenance_type='Repair', description='Synthetic', start_date='2026-10-01'))
        asset_status('MAINTENANCE')
        mid = sql('SELECT maintenance_id FROM it_asset_maintenance', fetch=True)[0][0]
        controls(f'/it/assets/{aid}', f'/it/assets/maintenance/{mid}/complete', True)
        post(f'/it/assets/maintenance/{mid}/complete', {'completed_date': '2026-10-02'})
        asset_status('AVAILABLE')
        for action, expected in [('retire', 'RETIRED'), ('restore', 'AVAILABLE'), ('lost', 'LOST'), ('restore', 'AVAILABLE')]:
            post(f'/it/assets/{aid}/{action}')
            asset_status(expected)
            if expected in ('RETIRED', 'LOST'):
                controls(f'/it/assets/{aid}', f'/it/assets/{aid}/restore', True)

        post('/it/help-desk/add', dict(employee_id='1', category_id='1', subject='Synthetic ticket', description='Test', priority='MEDIUM'))
        tid = sql('SELECT ticket_id FROM helpdesk_tickets', fetch=True)[0][0]
        for action, body, expected in [('assign', {'assigned_to': '1'}, 'OPEN'), ('start', {}, 'IN_PROGRESS'),
                                       ('resolve', {'resolution': 'Fixed'}, 'RESOLVED'), ('close', {}, 'CLOSED')]:
            controls(f'/it/help-desk/{tid}', f'/it/help-desk/{tid}/{action}', True)
            post(f'/it/help-desk/{tid}/{action}', body)
            assert sql('SELECT status FROM helpdesk_tickets WHERE ticket_id=%s', (tid,), True) == [(expected,)]
        assert sql('SELECT COUNT(*) FROM helpdesk_ticket_history', fetch=True)[0][0] >= 4
        print('PASS all 17 authorized mutation routes with persisted state and existing transactional history')

        for path, methods, permission, _ in route_contract():
            if 'GET' in methods:
                if permission.endswith('.view'):
                    assert viewer.get(path).status_code == 200, path
                else:
                    assert manager.get(path).status_code == 200, path
        for path, action in [('/it/assets', '/it/assets/add'), ('/it/assets/categories', '/it/assets/categories/add'),
                             ('/it/help-desk', '/it/help-desk/add')]:
            controls(path, action, True)

        # Actual DB role changes must affect the existing signed session immediately.
        for code, view_path, wrong_view, mutation in [
                ('helpdesk.view', '/it/help-desk', '/it/assets', f'/it/help-desk/{tid}/start'),
                ('it_assets.view', '/it/assets', '/it/help-desk', f'/it/assets/{aid}/retire')]:
            sql('DELETE FROM role_permissions WHERE role_id=4')
            sql('INSERT INTO role_permissions SELECT 4,permission_id FROM permissions WHERE permission_code=%s', (code,))
            assert denied.get(view_path).status_code == 200
            assert denied.get(wrong_view).location.endswith('/dashboard')
            html = denied.get(view_path).get_data(as_text=True)
            nav = html.split('<nav', 1)[1].split('</nav>', 1)[0]
            assert f'href="{view_path}"' in nav and f'href="{wrong_view}"' not in nav
            assert denied.post(mutation, data={'csrf_token': dt}).location.endswith('/dashboard')

        before = snapshot()
        sql('DELETE FROM role_permissions WHERE role_id=1')
        for path in [f'/it/assets/{aid}/retire', f'/it/help-desk/{tid}/start']:
            assert manager.post(path, data={'csrf_token': mt}).location.endswith('/dashboard')
        sql('UPDATE users SET is_active=0 WHERE user_id=2')
        assert viewer.get('/it/help-desk').location.endswith('/login')
        disabled = client(2)
        disabled_token = csrf_token_for(disabled)
        assert disabled.post(f'/it/assets/{aid}/retire', data={'csrf_token': disabled_token}).location.endswith('/login')
        assert snapshot() == before
        print('PASS read-only GET/export pages, real action visibility, independent navigation, DB revocation and disabled accounts')
    print('SUCCESS: IT authorization checks completed using disposable MySQL only')


if __name__ == '__main__':
    harness.run = run
    harness.main()
