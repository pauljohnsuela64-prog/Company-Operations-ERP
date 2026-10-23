"""Release-blocker probe: stale payroll must not pass same-second source edits.

This is an explicit audit gate, not a passing smoke-suite claim. A nonzero exit
documents an unresolved mainline defect. Uses the verified disposable harness.
"""
from contextlib import ExitStack
from datetime import date, timedelta
import importlib
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor()
        cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
        cur.execute('CREATE DATABASE erp_cleanup_freshness_audit')
        cur.execute('USE erp_cleanup_freshness_audit')
        for name in ('core', 'attendance', 'leave', 'payroll', 'payroll_period', 'payroll_entries', 'payroll_calculation', 'payroll_approval', 'payroll_adjustments'):
            source = (harness.ROOT / 'database' / f'{name}_schema.sql').read_text()
            for statement in re.sub(r'--[^\n]*', '', source).split(';'):
                if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b', statement, re.I):
                    cur.execute(statement)
        cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic payroll auditor')")
        cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'synthetic-auditor','test-only')")
        cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(1,'AUDIT','Synthetic','Employee')")
        cur.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(1,1,'MONTHLY',1000,'2026-01-01',1)")
        cur.execute("INSERT INTO payroll_periods(payroll_period_id,period_number,period_name,start_date,end_date,pay_date,created_by) VALUES(1,'AUDIT','Synthetic audit','2026-01-01','2026-01-15','2026-01-16',1)")
        cur.execute("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,generated_by) VALUES(1,1,1,'MONTHLY',1000,1)")
        db.commit()
    options.update(database='erp_cleanup_freshness_audit', init_command='SET timestamp=1768564800')

    def connect():
        return mysql.connector.connect(**options)

    with ExitStack() as stack:
        stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
        database = importlib.import_module('database')
        stack.enter_context(patch.object(database, 'get_connection', side_effect=connect))
        attendance = importlib.import_module('attendance_repository')
        calculation = importlib.import_module('payroll_calculation_repository')
        workflow = importlib.import_module('payroll_workflow_repository')
        for module in (attendance, calculation, workflow):
            stack.enter_context(patch.object(module, 'get_connection', side_effect=connect))
        current = date(2026, 1, 1)
        while current <= date(2026, 1, 15):
            if current.weekday() < 5:
                identity = attendance.create_attendance_record(1, current, None, None, 'PRESENT', None, 1)
                if current == date(2026, 1, 5):
                    changed = identity
            current += timedelta(days=1)
        calculation.calculate_monthly_payroll_period(1, 1)
        attendance.update_attendance_record(changed, 1, date(2026, 1, 5), None, None, 'ABSENT', None, 1)
        with connect() as db:
            cur = db.cursor()
            cur.execute('SELECT ar.updated_at,pe.calculated_at FROM attendance_records ar CROSS JOIN payroll_entries pe WHERE ar.attendance_id=%s', (changed,))
            updated, calculated = cur.fetchone()
            assert updated == calculated, 'Probe requires an actual same-second collision'
        try:
            workflow.submit_payroll_for_approval(1, 1)
        except ValueError:
            print('PASS stale same-second attendance rejected before payroll submission')
            return
        raise AssertionError('P1 RELEASE BLOCKER: real same-second PRESENT->ABSENT edit accepted for payroll submission without recalculation')


if __name__ == '__main__':
    harness.run = run
    harness.main()
