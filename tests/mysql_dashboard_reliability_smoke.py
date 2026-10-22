"""Aggregate parity, read boundaries and HTTP behavior on disposable MySQL only."""
from contextlib import ExitStack
from datetime import date, timedelta
import importlib
from pathlib import Path
import re
from unittest.mock import patch
import mysql.connector
import mysql_audit_smoke as harness
from security_helpers import csrf_client, stamp_session


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor(); cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_dashboard_test'); cur.execute('USE erp_dashboard_test')
        for name in ('core', 'inventory', 'procurement', 'finance', 'budget', 'attendance', 'leave',
                     'payroll_period', 'it_assets', 'it_asset_assignment', 'it_asset_maintenance',
                     'help_desk', 'help_desk_history', 'audit_logs'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                statement = statement.strip()
                if statement and not re.match(r'(CREATE DATABASE|USE)\b', statement, re.I): cur.execute(statement)
        db.commit()
    options['database'] = 'erp_dashboard_test'
    def connect(): return mysql.connector.connect(**options)
    def sql(query, params=(), fetch=False):
        with connect() as db:
            cur = db.cursor(); cur.execute(query, params)
            result = cur.fetchall() if fetch else cur.lastrowid
            db.commit(); return result
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'HR Manager'),(2,'Synthetic all'),(3,'Denied'),(4,'Payroll reader')")
    for uid in (1, 2, 3, 4):
        sql('INSERT INTO users(user_id,role_id,username,password_hash) VALUES(%s,%s,%s,%s)', (uid, uid, f'dashboard.{uid}', 'synthetic-unused'))

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        stack.enter_context(patch.dict('os.environ', SECRET_KEY='isolated-dashboard-mysql', ERP_ENV='testing', ERP_DEBUG='false'))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        repo = importlib.import_module('dashboard_repository')
        erp = importlib.import_module('app')
        stack.enter_context(patch.dict(erp.app.config, TESTING=True))
        all_permissions = {spec[0] for spec in repo.SECTIONS.values()}
        for code in sorted(all_permissions | {'departments.view', 'it_assets.manage', 'helpdesk.manage'}):
            pid = sql('INSERT INTO permissions(permission_code) VALUES(%s) ON DUPLICATE KEY UPDATE permission_id=LAST_INSERT_ID(permission_id)', (code,))
            sql('INSERT INTO role_permissions VALUES(2,%s)', (pid,))
            if code in ('employees.view', 'attendance.view', 'leave.view', 'departments.view'):
                sql('INSERT INTO role_permissions VALUES(1,%s)', (pid,))
            if code == 'payroll.view': sql('INSERT INTO role_permissions VALUES(4,%s)', (pid,))
        from schema_compatibility import inspect_schema
        with connect() as db: assert inspect_schema(db, options['database']).compatible
        def client(uid=1):
            c = csrf_client(erp.app)
            with c.session_transaction() as session: stamp_session(erp.app, session, erp.get_authorization_state(uid))
            return c
        def summary(permissions=all_permissions): return repo.get_dashboard_summary(permissions)
        empty = summary()
        for section in repo.SECTIONS:
            assert empty[section] is not None, section
            for key, value in empty[section].items(): assert value is None if key == 'latest_paid' else value == 0
        print('PASS real compatible schema and all nine empty aggregates return zero; no paid period is None')

        today = date.today()
        for eid, status in enumerate(('Active', ' active ', '\tOn Leave\n', '\x1cInactive\x1f', 'ÁCTIVE', 'Other'), 1):
            sql('INSERT INTO employees(employee_id,employee_number,first_name,last_name,employment_status) VALUES(%s,%s,%s,%s,%s)', (eid, f'DASH-{eid}', 'Synthetic', 'Employee', status))
        for eid, status in enumerate(('PRESENT', 'LATE', 'ABSENT', 'ON_LEAVE', 'HALF_DAY'), 1):
            sql('INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(%s,%s,%s,1)', (eid, today, status))
        sql("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(1,%s,'PRESENT',1)", (today - timedelta(days=1),))
        leave_type = sql('SELECT MIN(leave_type_id) FROM leave_types', fetch=True)[0][0]
        for i, status in enumerate(('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'), 1):
            sql('INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(%s,1,%s,%s,%s,1,%s,%s,1)', (f'DASH-L-{i}', leave_type, today, today, 'Synthetic', status))
        for i in range(1005):
            sql('INSERT INTO inventory_items(item_code,item_name,is_active) VALUES(%s,%s,%s)', (f'DASH-I-{i}', 'Synthetic', (1, 0, 2)[i % 3]))
        for i, status in enumerate(('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'COMPLETED'), 1):
            sql('INSERT INTO purchase_requests(request_number,requested_by,purpose,status) VALUES(%s,1,%s,%s)', (f'DASH-PR-{i}', 'Synthetic', status))
        sql("INSERT INTO expense_categories(category_id,category_code,category_name) VALUES(1,'DASH','Synthetic')")
        for i, status in enumerate(('DRAFT', 'APPROVED', 'PAID', 'CANCELLED'), 1):
            sql('INSERT INTO expenses(expense_number,expense_date,category_id,description,amount,status,created_by) VALUES(%s,%s,1,%s,1,%s,1)', (f'DASH-E-{i}', today - timedelta(days=i*400), 'Synthetic', status))
        sql("INSERT INTO it_asset_categories(category_id,category_code,category_name) VALUES(1,'DASH','Synthetic')")
        for i, status in enumerate(('AVAILABLE', 'ASSIGNED', 'MAINTENANCE', 'RETIRED', 'LOST'), 1):
            sql('INSERT INTO it_assets(asset_tag,asset_name,category_id,status,created_by) VALUES(%s,%s,1,%s,1)', (f'DASH-A-{i}', 'Synthetic', status))
        sql("INSERT INTO helpdesk_categories(category_id,category_code,category_name) VALUES(1,'DASH','Synthetic')")
        for i, (status, priority) in enumerate((('OPEN', 'URGENT'), ('IN_PROGRESS', 'URGENT'), ('OPEN', 'LOW'), ('RESOLVED', 'URGENT'), ('CLOSED', 'LOW'), ('CANCELLED', 'URGENT')), 1):
            sql('INSERT INTO helpdesk_tickets(ticket_number,employee_id,category_id,subject,description,priority,status,created_by) VALUES(%s,1,1,%s,%s,%s,%s,1)', (f'DASH-T-{i}', 'Synthetic', 'Synthetic', priority, status))
        for i, status in enumerate(('DRAFT', 'PROCESSING', 'APPROVED', 'PAID', 'CANCELLED', 'PAID', 'PAID'), 1):
            start = date(2025, 1, 1) if i == 7 else date(2026, 1, 1)
            sql('INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by,paid_at) VALUES(%s,%s,%s,%s,%s,%s,1,%s)', (f'DASH-P-{i}', f'Synthetic {i}', start, start, start, status, '2026-10-22 12:00:00' if i == 7 else None))

        readers = {
            'employees': ('employee_repository', 'get_all_employees'),
            'attendance': ('attendance_repository', 'get_filtered_attendance_records'),
            'leave': ('leave_repository', 'get_all_leave_requests'),
            'inventory': ('inventory_item_repository', 'get_all_inventory_items'),
            'procurement': ('purchase_request_repository', 'get_all_purchase_requests'),
            'finance': ('expense_repository', 'get_all_expenses'),
            'it_assets': ('it_asset_repository', 'get_all_it_assets'),
            'helpdesk': ('help_desk_repository', 'get_all_helpdesk_tickets'),
            'payroll': ('payroll_period_repository', 'get_all_payroll_periods')}
        data = summary()
        for section, (module, method) in readers.items():
            reader = getattr(importlib.import_module(module), method)
            rows = reader(attendance_date=today) if section == 'attendance' else reader()
            _, _, _, statuses, total = repo.SECTIONS[section]
            expected = {key: sum(str(row.get('employment_status' if section == 'employees' else 'status', '')).strip().upper() == status for row in rows) for key, status in statuses.items()}
            if total: expected[total] = len(rows)
            if section == 'inventory': expected['active_items'] = sum(bool(row['is_active']) for row in rows)
            if section == 'helpdesk':
                expected['open'] = sum(row['status'] in ('OPEN', 'IN_PROGRESS') for row in rows)
                expected['urgent_open'] = sum(row['status'] in ('OPEN', 'IN_PROGRESS') and row['priority'] == 'URGENT' for row in rows)
            if section == 'payroll': expected['latest_paid'] = next((row for row in rows if row['status'] == 'PAID'), None)
            assert data[section] == expected, (section, data[section], expected)
        assert data['attendance']['total'] == 5 and data['helpdesk']['urgent_open'] == 2
        assert data['payroll']['latest_paid']['period_number'] == 'DASH-P-6'
        print('PASS all original-reader counts and paid-record fields, 1005 items, Unicode employment states, application-date Attendance, urgent/open tickets and start-date/ID Payroll ordering')

        observed = []; inserted = False
        class SnapshotCursor:
            def __init__(self, cursor): self.cursor = cursor; self.payroll_count = False
            def __getattr__(self, name): return getattr(self.cursor, name)
            def execute(self, query, params=()):
                self.payroll_count = 'FROM payroll_periods' in query and 'SUM(' in query
                observed.append((query, params)); return self.cursor.execute(query, params)
            def fetchone(self):
                nonlocal inserted
                result = self.cursor.fetchone()
                if self.payroll_count and not inserted:
                    inserted = True
                    sql("INSERT INTO payroll_periods(period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES('DASH-CONCURRENT','Synthetic','2027-01-01','2027-01-01','2027-01-01','PAID',1)")
                return result
            def fetchall(self): raise AssertionError('Dashboard must not materialize full datasets')
        class SnapshotConnection:
            def __init__(self, db): self.db = db
            def __getattr__(self, name): return getattr(self.db, name)
            def cursor(self, *args, **kwargs): return SnapshotCursor(self.db.cursor(*args, **kwargs))
        with patch.object(repo, 'get_connection', side_effect=lambda: SnapshotConnection(connect())):
            concurrent = summary()
        assert len(observed) == 10 and concurrent['payroll'] == data['payroll']
        assert summary()['payroll']['latest_paid']['period_number'] == 'DASH-CONCURRENT'
        print('PASS bounded fetchone-only results: nine aggregates plus LIMIT 1; Payroll count/latest share snapshot during an actual concurrent commit')

        tables = ('employees', 'attendance_records', 'leave_requests', 'inventory_items', 'purchase_requests', 'expenses', 'it_assets', 'helpdesk_tickets', 'payroll_periods', 'audit_logs', 'role_permissions')
        def snapshot(): return [sql('SELECT * FROM ' + table + ' ORDER BY 1', fetch=True) for table in tables]
        before = snapshot(); hr = client()
        html = hr.get('/dashboard').get_data(as_text=True)
        assert 'href="/attendance"' in html and 'href="/leave/requests"' in html and 'href="/admin/users"' not in html
        assert hr.get('/attendance').status_code == 200 and hr.get('/leave/requests').status_code == 200
        assert hr.get('/admin/users').location.endswith('/dashboard')
        assert snapshot() == before
        assert hr.post('/logout').status_code == 302  # Existing genuine CSRF helper.
        # Logout auditing is existing intentional behavior, not a dashboard write.
        before = snapshot()
        assert client(3).get('/dashboard').status_code == 200
        sql('RENAME TABLE payroll_periods TO dashboard_saved_payroll')
        try:
            with patch.object(repo, '_read_section', wraps=repo._read_section) as read:
                assert client().get('/dashboard').status_code == 200
                assert 'payroll' not in [call.args[0] for call in read.call_args_list]
            html = client(2).get('/dashboard').get_data(as_text=True)
            assert 'Currently unavailable.' in html and 'No paid payroll period yet.' not in html
            assert 'dashboard_saved_payroll' not in html and 'payroll_periods' not in html
            sql('RENAME TABLE leave_requests TO dashboard_saved_leave')
            try:
                html = client().get('/dashboard').get_data(as_text=True)
                assert 'Currently unavailable.' in html and 'Attendance Today' in html
            finally: sql('RENAME TABLE dashboard_saved_leave TO leave_requests')
        finally: sql('RENAME TABLE dashboard_saved_payroll TO payroll_periods')
        assert snapshot() == before
        print('PASS HR-only navigation/routes, no Payroll query despite missing table, authorized unavailable sections and unchanged business/audit/grant snapshots')
        # Permission revocation must affect this already-authenticated HR client.
        hr = client()
        sql("DELETE rp FROM role_permissions rp JOIN permissions p ON p.permission_id=rp.permission_id WHERE rp.role_id=1 AND p.permission_code='leave.view'")
        html = hr.get('/dashboard').get_data(as_text=True)
        assert 'href="/leave/requests"' not in html and 'href="/attendance"' in html
        assert hr.get('/leave/requests').location.endswith('/dashboard')
        sql('UPDATE users SET is_active=0 WHERE user_id=1')
        assert hr.get('/dashboard').location.endswith('/login')
        print('PASS committed permission refresh, disabled-account rejection and unchanged authorization/CSRF boundaries')
    print('SUCCESS: Dashboard reliability used verified disposable MySQL only')


if __name__ == '__main__':
    harness.run = run
    harness.main()
