"""Explicit additive upgrade; no company configuration or import-time SQL."""
import argparse
from getpass import getpass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from payroll_freshness import (TABLES, EVIDENCE_COLUMNS, GUARD_DDL, GENERATIONS_DDL,
                               SNAPSHOTS_DDL, inspect_table, inspect_structure, inspect_snapshot_reference, _type, FreshnessError)
import mysql.connector


def migrate(connection, expected_database):
    """Requires drained participating writers; DDL cannot be rolled back."""
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute('SELECT VERSION() AS version,DATABASE() AS db')
        info = cursor.fetchone()
        import re
        version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', info['version'])
        if (not expected_database or info['db'] != expected_database or not version
                or 'mariadb' in info['version'].lower() or tuple(map(int, version.groups())) < (8, 0, 16)):
            raise FreshnessError('Explicit matching database and MySQL 8.0.16+ required.')
        cursor.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.tables WHERE table_schema=DATABASE()')
        engines = {r['TABLE_NAME']: r['ENGINE'] for r in cursor.fetchall()}
        for name in ('employees',):
            if engines.get(name) != 'InnoDB':
                raise FreshnessError('Required InnoDB source table unavailable: ' + name)
        if 'attendance_records' in engines and engines['attendance_records'] != 'InnoDB':
            raise FreshnessError('Installed Attendance storage must use InnoDB.')
        payroll = 'payroll_entries' in engines
        if payroll and engines['payroll_entries'] != 'InnoDB':
            raise FreshnessError('Payroll entries must use InnoDB.')
        for name in TABLES:
            if name in engines:
                inspect_table(cursor, name)
        if not payroll and 'payroll_attendance_snapshots' in engines:
            raise FreshnessError('Orphaned Payroll evidence structure; operator review required.')
        if 'payroll_attendance_snapshots' in engines:
            inspect_snapshot_reference(cursor)
        existing = {}
        if payroll:
            cursor.execute("SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='payroll_entries'")
            columns = {r['COLUMN_NAME']: r for r in cursor.fetchall()}
            for name, kind in EVIDENCE_COLUMNS.items():
                row = columns.get(name)
                if row and (_type(row['COLUMN_TYPE']) != kind or row['IS_NULLABLE'] != 'YES'
                            or row['COLUMN_DEFAULT'] is not None or row['EXTRA']):
                    raise FreshnessError('Incompatible existing evidence column: ' + name)
                existing[name] = row is not None
        # Preflight every existing integrity table/column before additive DDL.
        cursor.execute(GUARD_DDL)
        cursor.execute(GENERATIONS_DDL)
        cursor.execute('SELECT guard_id FROM payroll_attendance_guard')
        guards = cursor.fetchall()
        if guards and guards != [{'guard_id': 1}]:
            raise FreshnessError('Incompatible coordination rows; no reset allowed.')
        cursor.execute('INSERT IGNORE INTO payroll_attendance_guard(guard_id) VALUES(1)')
        connection.commit()
        if payroll:
            for name, kind in EVIDENCE_COLUMNS.items():
                if not existing[name]:
                    cursor.execute('ALTER TABLE payroll_entries ADD COLUMN ' + name + ' ' + kind + ' NULL')
            cursor.execute(SNAPSHOTS_DDL)
        inspect_structure(cursor, attendance=True, evidence=payroll)
        connection.rollback()
    # No update of Attendance, calculated amounts, revisions, statuses or evidence.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('host', 'user', 'database'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    with mysql.connector.connect(host=args.host, port=args.port, user=args.user,
                                 database=args.database, password=getpass('MySQL password: '),
                                 connection_timeout=3, read_timeout=5, write_timeout=5) as connection:
        migrate(connection, args.database)
    print('Freshness structures verified. Legacy Payroll remains unverified; no business data backfilled.')


if __name__ == '__main__':
    main()
