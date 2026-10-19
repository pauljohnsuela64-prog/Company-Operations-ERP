"""Standalone HR upgrade; no Payroll dependency, .env or import-time connection."""
import argparse
from getpass import getpass
import re

import mysql.connector


SCHEMAS = {
    'departments': {
        'department_id': ('int', 'NO'), 'department_code': ('varchar(20)', 'NO'),
        'department_name': ('varchar(100)', 'NO'), 'description': ('varchar(255)', 'YES'),
        'is_active': ('tinyint(1)', 'NO'),
    },
    'employees': {
        'employee_id': ('int', 'NO'), 'employee_number': ('varchar(30)', 'NO'),
        'department_id': ('int', 'YES'), 'first_name': ('varchar(100)', 'NO'),
        'middle_name': ('varchar(100)', 'YES'), 'last_name': ('varchar(100)', 'NO'),
        'email': ('varchar(150)', 'YES'), 'phone': ('varchar(30)', 'YES'),
        'job_title': ('varchar(100)', 'YES'), 'hire_date': ('date', 'YES'),
        'employment_status': ('varchar(30)', 'NO'),
    },
}


def _type(value):
    return re.sub(r'\b(int|bigint)\(\d+\)', r'\1', value.lower())


def _inspect(cursor, table):
    cursor.execute('SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s', (table,))
    row = cursor.fetchone()
    if row is None or row['ENGINE'] != 'InnoDB':
        raise RuntimeError(f'{table} must exist and use InnoDB.')
    cursor.execute('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,DATA_TYPE FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s', (table,))
    columns = {r['COLUMN_NAME']: r for r in cursor.fetchall()}
    for name, (kind, nullable) in SCHEMAS[table].items():
        col = columns.get(name)
        if col is None or _type(col['COLUMN_TYPE']) != kind or col['IS_NULLABLE'] != nullable:
            raise RuntimeError(f'Incompatible {table}.{name}; inspect schema before upgrading.')
    for name in ('created_at', 'updated_at'):
        if columns.get(name, {}).get('DATA_TYPE') != 'timestamp':
            raise RuntimeError(f'Incompatible {table}.{name}.')
    default_name, default_value = ('employment_status', 'Active') if table == 'employees' else ('is_active', '1')
    if str(columns[default_name]['COLUMN_DEFAULT']) != default_value:
        raise RuntimeError(f'Incompatible {table}.{default_name} default.')
    pk = 'employee_id' if table == 'employees' else 'department_id'
    if 'auto_increment' not in columns[pk]['EXTRA']:
        raise RuntimeError(f'{table} requires its existing auto-increment identity.')
    cursor.execute('SELECT INDEX_NAME,NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS names,MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=%s GROUP BY INDEX_NAME,NON_UNIQUE', (table,))
    indexes = cursor.fetchall()
    required = [pk, 'employee_number', 'email'] if table == 'employees' else [pk, 'department_code', 'department_name']
    for name in required:
        if not any(r['NON_UNIQUE'] == 0 and r['names'] == name and not r['prefix_length']
                   and (name != pk or r['INDEX_NAME'] == 'PRIMARY') for r in indexes):
            raise RuntimeError(f'Missing expected unique/primary key on {table}.{name}.')
    col = columns.get('revision')
    if col is not None and (_type(col['COLUMN_TYPE']) != 'bigint' or col['IS_NULLABLE'] != 'NO'
                            or str(col['COLUMN_DEFAULT']) != '1' or col['EXTRA']):
        raise RuntimeError(f'Incompatible {table}.revision; no data was reset.')
    constraint = f'ck_{table}_revision_positive'
    cursor.execute('SELECT t.TABLE_NAME,t.CONSTRAINT_NAME,t.ENFORCED,c.CHECK_CLAUSE FROM information_schema.table_constraints t JOIN information_schema.check_constraints c ON c.CONSTRAINT_SCHEMA=t.CONSTRAINT_SCHEMA AND c.CONSTRAINT_NAME=t.CONSTRAINT_NAME WHERE t.CONSTRAINT_SCHEMA=DATABASE() AND (t.TABLE_NAME=%s OR t.CONSTRAINT_NAME=%s)', (table, constraint))
    found = False
    for check in cursor.fetchall():
        if check['CONSTRAINT_NAME'] == constraint:
            clause = re.sub(r'[\s`()]+', '', check['CHECK_CLAUSE']).lower()
            if check['TABLE_NAME'] != table or check['ENFORCED'] != 'YES' or clause != 'revision>=1':
                raise RuntimeError(f'Incompatible constraint {constraint}.')
            found = True
        elif re.search(r'\brevision\b', check['CHECK_CLAUSE'], re.I):
            raise RuntimeError(f'Unexpected revision constraint on {table}; review manually.')
    if col is not None:
        cursor.execute(f'SELECT COUNT(*) AS invalid FROM `{table}` WHERE revision < 1')
        if cursor.fetchone()['invalid']:
            raise RuntimeError(f'{table} contains invalid revisions; no automatic repair is permitted.')
    return col is not None, found


def upgrade(connection):
    if connection.in_transaction:
        raise RuntimeError('Run this DDL upgrade on a dedicated connection outside a transaction.')
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT VERSION() AS version, DATABASE() AS db')
        info = cursor.fetchone()
        match = re.match(r'(\d+)\.(\d+)\.(\d+)', info['version'])
        if not info['db'] or not match or 'mariadb' in info['version'].lower() or tuple(map(int, match.groups())) < (8, 0, 16):
            raise RuntimeError('Explicit database and compatible MySQL 8.0.16+ with enforced CHECKs required.')
        # Inspect BOTH tables and the FK before any DDL; incompatible partial
        # upgrades must fail without modifying the other table.
        state = {table: _inspect(cursor, table) for table in SCHEMAS}
        cursor.execute("SELECT k.COLUMN_NAME,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='employees' AND k.COLUMN_NAME='department_id' AND k.REFERENCED_TABLE_NAME IS NOT NULL")
        fks = cursor.fetchall()
        if len(fks) != 1 or fks[0]['REFERENCED_TABLE_SCHEMA'] != info['db'] or fks[0]['REFERENCED_TABLE_NAME'] != 'departments' or fks[0]['REFERENCED_COLUMN_NAME'] != 'department_id' or fks[0]['DELETE_RULE'] != 'SET NULL' or fks[0]['UPDATE_RULE'] not in ('RESTRICT', 'NO ACTION'):
            raise RuntimeError('Employee Department foreign key differs from the expected schema.')
        connection.commit()  # End inspection transaction before explicitly committing DDL.
        for table, (has_column, has_check) in state.items():
            clauses = []
            if not has_column:
                clauses.append('ADD COLUMN revision BIGINT NOT NULL DEFAULT 1')
            if not has_check:
                clauses.append(f'ADD CONSTRAINT ck_{table}_revision_positive CHECK (revision >= 1)')
            if clauses:
                cursor.execute(f'ALTER TABLE `{table}` ' + ', '.join(clauses))
        for table in SCHEMAS:
            if _inspect(cursor, table) != (True, True):
                raise RuntimeError(f'Incomplete revision upgrade on {table}.')
        connection.commit()
    except Exception:
        connection.rollback()  # Does not undo previously completed DDL statements.
        raise
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--user', required=True)
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    password = getpass('MySQL password: ')
    with mysql.connector.connect(host=args.host, port=args.port, user=args.user,
                                 password=password, database=args.database) as connection:
        upgrade(connection)
    print('Standalone HR revision migration 008 verified/applied.')


if __name__ == '__main__':
    main()
