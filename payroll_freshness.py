"""Durable scoped Attendance evidence. No connections, DDL or grants on import."""
from datetime import timedelta
import re

VERSION = 1
MAX_GENERATION = 9223372036854775807
GUARD_DDL = """CREATE TABLE IF NOT EXISTS payroll_attendance_guard (
    guard_id TINYINT NOT NULL PRIMARY KEY,
    CONSTRAINT ck_payroll_attendance_guard_singleton CHECK (guard_id = 1)
) ENGINE=InnoDB"""
GENERATIONS_DDL = """CREATE TABLE IF NOT EXISTS payroll_attendance_generations (
    employee_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    generation BIGINT NOT NULL DEFAULT 1,
    PRIMARY KEY (employee_id, attendance_date),
    CONSTRAINT ck_payroll_attendance_generation_positive CHECK (generation >= 1)
) ENGINE=InnoDB"""
SNAPSHOTS_DDL = """CREATE TABLE IF NOT EXISTS payroll_attendance_snapshots (
    payroll_entry_id INT NOT NULL,
    attendance_date DATE NOT NULL,
    employee_id INT NOT NULL,
    generation BIGINT NOT NULL,
    PRIMARY KEY (payroll_entry_id, attendance_date),
    CONSTRAINT ck_payroll_attendance_snapshot_nonnegative CHECK (generation >= 0),
    CONSTRAINT fk_payroll_attendance_snapshot_entry FOREIGN KEY (payroll_entry_id)
        REFERENCES payroll_entries(payroll_entry_id) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB"""
EVIDENCE_COLUMNS = {
    'attendance_evidence_version': 'smallint unsigned',
    'attendance_scope_start': 'date',
    'attendance_scope_end': 'date',
}
TABLES = {
    'payroll_attendance_guard': ({'guard_id': ('tinyint', 'NO')}, 'guard_id',
                               'ck_payroll_attendance_guard_singleton', 'guard_id=1'),
    'payroll_attendance_generations': (
        {'employee_id': ('int', 'NO'), 'attendance_date': ('date', 'NO'), 'generation': ('bigint', 'NO')},
        'employee_id,attendance_date', 'ck_payroll_attendance_generation_positive', 'generation>=1'),
    'payroll_attendance_snapshots': (
        {'payroll_entry_id': ('int', 'NO'), 'attendance_date': ('date', 'NO'),
         'employee_id': ('int', 'NO'), 'generation': ('bigint', 'NO')},
        'payroll_entry_id,attendance_date', 'ck_payroll_attendance_snapshot_nonnegative', 'generation>=0'),
}


class FreshnessError(ValueError):
    status_code = 503


def value(row, name, index=0):
    return row[name] if isinstance(row, dict) else row[index]


def _type(kind):
    return re.sub(r'\b(tinyint|smallint|int|bigint)\(\d+\)', r'\1', kind.lower())


def inspect_table(cursor, table):
    cursor.execute('SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s', (table,))
    row = cursor.fetchone()
    if not row or value(row, 'ENGINE') != 'InnoDB':
        raise FreshnessError('Payroll attendance integrity schema is unavailable. An operator must verify migration 010.')
    columns, primary, constraint, expression = TABLES[table]
    cursor.execute('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,EXTRA FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s', (table,))
    actual = {value(r, 'COLUMN_NAME'): (_type(value(r, 'COLUMN_TYPE', 1)), value(r, 'IS_NULLABLE', 2), value(r, 'EXTRA', 3)) for r in cursor.fetchall()}
    if set(actual) != set(columns) or any(actual[k] != (*definition, '') for k, definition in columns.items()):
        raise FreshnessError('Payroll attendance integrity columns are incompatible. An operator must verify migration 010.')
    cursor.execute("SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS names,MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=%s AND INDEX_NAME='PRIMARY' GROUP BY INDEX_NAME", (table,))
    row = cursor.fetchone()
    if not row or value(row, 'names') != primary or value(row, 'prefix_length', 1):
        raise FreshnessError('Payroll attendance integrity keys are incompatible. An operator must verify migration 010.')
    cursor.execute('SELECT t.ENFORCED,c.CHECK_CLAUSE FROM information_schema.table_constraints t JOIN information_schema.check_constraints c ON c.CONSTRAINT_SCHEMA=t.CONSTRAINT_SCHEMA AND c.CONSTRAINT_NAME=t.CONSTRAINT_NAME WHERE t.CONSTRAINT_SCHEMA=DATABASE() AND t.TABLE_NAME=%s AND t.CONSTRAINT_NAME=%s', (table, constraint))
    row = cursor.fetchone()
    if (not row or value(row, 'ENFORCED') != 'YES'
            or re.sub(r'[\s()]+', '', value(row, 'CHECK_CLAUSE', 1).replace(chr(96), '')).lower() != expression):
        raise FreshnessError('Payroll attendance integrity checks are incompatible. An operator must verify migration 010.')


def inspect_snapshot_reference(cursor):
    cursor.execute("SELECT k.COLUMN_NAME,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='payroll_attendance_snapshots'")
    rows = cursor.fetchall()
    cursor.execute('SELECT DATABASE() AS db')
    database = value(cursor.fetchone(), 'db')
    if len(rows) != 1 or tuple(value(rows[0], name, index) for index, name in enumerate(
            ('COLUMN_NAME', 'REFERENCED_TABLE_SCHEMA', 'REFERENCED_TABLE_NAME', 'REFERENCED_COLUMN_NAME', 'DELETE_RULE', 'UPDATE_RULE'))) != (
                'payroll_entry_id', database, 'payroll_entries', 'payroll_entry_id', 'RESTRICT', 'RESTRICT'):
        raise FreshnessError('Payroll snapshot references are incompatible. An operator must verify migration 010.')


def inspect_structure(cursor, *, attendance=False, evidence=False):
    """Read-only preflight; reject incompatible partial structures, never repair."""
    names = ['payroll_attendance_guard']
    if attendance or evidence:
        names.append('payroll_attendance_generations')
    if evidence:
        names.append('payroll_attendance_snapshots')
    for table in names:
        inspect_table(cursor, table)
    if evidence:
        cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_entries'")
        row = cursor.fetchone()
        if not row or value(row, 'ENGINE') != 'InnoDB':
            raise FreshnessError('Payroll evidence storage must use InnoDB.')
        cursor.execute("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_entries'")
        columns = {value(r, 'COLUMN_NAME'): r for r in cursor.fetchall()}
        for name, kind in EVIDENCE_COLUMNS.items():
            row = columns.get(name)
            if (not row or _type(value(row, 'COLUMN_TYPE', 1)) != kind or value(row, 'IS_NULLABLE', 2) != 'YES'
                    or value(row, 'COLUMN_DEFAULT', 3) is not None or value(row, 'EXTRA', 4)):
                raise FreshnessError('Payroll calculation evidence is unavailable. An operator must verify migration 010.')
        inspect_snapshot_reference(cursor)


def lock_guard(cursor, *, attendance=False, evidence=False):
    inspect_structure(cursor, attendance=attendance, evidence=evidence)
    cursor.execute('SELECT guard_id FROM payroll_attendance_guard WHERE guard_id=1 FOR UPDATE')
    if cursor.fetchone() is None:
        raise FreshnessError('Payroll attendance coordination is unavailable. An operator must verify migration 010.')


def advance(cursor, keys):
    """Guard must be held. Old/new scope keys survive row moves as tombstones."""
    for employee, day in sorted(set(keys)):
        cursor.execute('SELECT generation FROM payroll_attendance_generations WHERE employee_id=%s AND attendance_date=%s FOR UPDATE', (employee, day))
        row = cursor.fetchone()
        if row is None:
            cursor.execute('INSERT INTO payroll_attendance_generations(employee_id,attendance_date,generation) VALUES(%s,%s,1)', (employee, day))
        else:
            generation = value(row, 'generation')
            if not 1 <= generation < MAX_GENERATION:
                raise FreshnessError('Attendance change generation is exhausted. Contact an operator; no counter may be reset.')
            cursor.execute('UPDATE payroll_attendance_generations SET generation=generation+1 WHERE employee_id=%s AND attendance_date=%s AND generation=%s AND generation<%s', (employee, day, generation, MAX_GENERATION))
            if cursor.rowcount != 1:
                raise FreshnessError('Attendance change generation could not be confirmed. Reload and reconcile.')


def work_dates(start, end):
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        if current == end:
            break
        current += timedelta(days=1)


def generations(cursor, employee, start, end):
    cursor.execute('SELECT attendance_date,generation FROM payroll_attendance_generations WHERE employee_id=%s AND attendance_date BETWEEN %s AND %s ORDER BY attendance_date FOR UPDATE', (employee, start, end))
    return {value(row, 'attendance_date'): value(row, 'generation', 1) for row in cursor.fetchall()}


def save(cursor, entry, employee, start, end):
    current = generations(cursor, employee, start, end)
    cursor.execute('DELETE FROM payroll_attendance_snapshots WHERE payroll_entry_id=%s', (entry,))
    rows = [(entry, day, employee, current.get(day, 0)) for day in work_dates(start, end)]
    if rows:
        cursor.executemany('INSERT INTO payroll_attendance_snapshots(payroll_entry_id,attendance_date,employee_id,generation) VALUES(%s,%s,%s,%s)', rows)
    cursor.execute('UPDATE payroll_entries SET attendance_evidence_version=%s,attendance_scope_start=%s,attendance_scope_end=%s WHERE payroll_entry_id=%s', (VERSION, start, end, entry))


def validate(cursor, period, start, end, *, payment=False):
    """Guard held through transition commit; never attest legacy data."""
    prefix = 'Payment blocked. ' if payment else ''
    guidance = ('APPROVED Payroll was not reopened. An approved recovery procedure is required.'
                if payment else 'Return to Draft if needed and explicitly recalculate Payroll before approval.')
    cursor.execute('SELECT payroll_entry_id,employee_id,attendance_evidence_version,attendance_scope_start,attendance_scope_end FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id FOR UPDATE', (period,))
    entries = cursor.fetchall()
    expected = set(work_dates(start, end))
    if not entries or not expected:
        raise FreshnessError(prefix + 'Payroll attendance evidence is missing. ' + guidance)
    for row in entries:
        entry, employee, version, saved_start, saved_end = [
            value(row, name, i) for i, name in enumerate(('payroll_entry_id', 'employee_id',
                'attendance_evidence_version', 'attendance_scope_start', 'attendance_scope_end'))]
        if version != VERSION or saved_start != start or saved_end != end:
            raise FreshnessError(prefix + 'Payroll calculation is unverified or its cutoff changed. ' + guidance)
        cursor.execute('SELECT attendance_date,employee_id,generation FROM payroll_attendance_snapshots WHERE payroll_entry_id=%s ORDER BY attendance_date FOR UPDATE', (entry,))
        rows = cursor.fetchall()
        saved = {value(r, 'attendance_date'): (value(r, 'employee_id', 1), value(r, 'generation', 2)) for r in rows}
        current = generations(cursor, employee, start, end)
        if len(rows) != len(expected) or set(saved) != expected or any(saved[day] != (employee, current.get(day, 0)) for day in expected):
            raise FreshnessError(prefix + 'Attendance changed after Payroll calculation or evidence is incomplete. ' + guidance)
