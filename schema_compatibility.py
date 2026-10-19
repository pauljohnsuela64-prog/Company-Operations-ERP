"""Read-only, versioned capabilities required by this application build.

No connection, migration, grant or configuration loading occurs on import.
"""
import re
from dataclasses import dataclass

MANIFEST_VERSION = 'erp-main-hr-revisions-v1'
CAPABILITIES = ('mysql-enforced-checks', 'hr-revisions-008',
                'receiving-idempotency-001', 'stock-idempotency-002',
                'it-helpdesk-permission-codes-003')
INNODB_TABLES = ('roles', 'permissions', 'role_permissions', 'users', 'employees', 'departments',
                 'inventory_categories', 'warehouses', 'inventory_items', 'inventory_stock',
                 'stock_movements', 'suppliers', 'purchase_requests', 'purchase_request_items',
                 'purchase_orders', 'purchase_order_items', 'goods_receipts', 'goods_receipt_items')
PERMISSIONS = ('it_assets.view', 'it_assets.manage', 'helpdesk.view', 'helpdesk.manage')


@dataclass(frozen=True)
class Inspection:
    issues: tuple

    @property
    def compatible(self):
        return not self.issues


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
    return col is not None, found


def inspect_schema(connection, expected_database):
    """Inspect a dedicated, idle connection; metadata only, no business writes.

    Connector/metadata errors propagate to the caller, distinct from incompatibility.
    RuntimeError below represents a known capability mismatch only.
    """
    issues = []
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute('SELECT VERSION() AS version, DATABASE() AS db')
        info = cursor.fetchone()
        version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', info['version'])
        if (not version or 'mariadb' in info['version'].lower()
                or tuple(map(int, version.groups())) < (8, 0, 16)):
            issues.append('Compatible MySQL 8.0.16+ with enforced CHECK support required.')
        if not expected_database or info['db'] != expected_database:
            issues.append('Selected database does not match the explicit expected database.')
        if issues:
            return Inspection(tuple(issues))
        placeholders = ','.join(['%s'] * len(INNODB_TABLES))
        cursor.execute('SELECT TABLE_NAME,ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN (' + placeholders + ')', INNODB_TABLES)
        engines = {row['TABLE_NAME']: row['ENGINE'] for row in cursor.fetchall()}
        for table in INNODB_TABLES:
            if engines.get(table) != 'InnoDB':
                issues.append(f'{table}: InnoDB table required.')
        for table in SCHEMAS:
            try:
                if _inspect(cursor, table) != (True, True):
                    issues.append(f'{table}: migration 008 revision column and enforced CHECK required.')
            except RuntimeError as error:
                issues.append(str(error))
        cursor.execute("SELECT k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME='employees' AND k.COLUMN_NAME='department_id' AND k.REFERENCED_TABLE_NAME IS NOT NULL")
        fks = cursor.fetchall()
        if (len(fks) != 1 or fks[0]['REFERENCED_TABLE_SCHEMA'] != expected_database
                or fks[0]['REFERENCED_TABLE_NAME'] != 'departments'
                or fks[0]['REFERENCED_COLUMN_NAME'] != 'department_id'
                or fks[0]['DELETE_RULE'] != 'SET NULL'
                or fks[0]['UPDATE_RULE'] not in ('RESTRICT', 'NO ACTION')):
            issues.append('Employee Department foreign key is incompatible.')
        for table in ('goods_receipts', 'stock_movements'):
            cursor.execute("SELECT COLUMN_TYPE,IS_NULLABLE,CHARACTER_SET_NAME,COLLATION_NAME,EXTRA FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s AND column_name='submission_id'", (table,))
            col = cursor.fetchone()
            if (not col or col['COLUMN_TYPE'].lower() != 'char(36)' or col['IS_NULLABLE'] != 'YES'
                    or col['CHARACTER_SET_NAME'] != 'ascii' or col['COLLATION_NAME'] != 'ascii_bin' or col['EXTRA']):
                issues.append(f'{table}: nullable ASCII/ascii_bin CHAR(36) submission_id required.')
            cursor.execute("SELECT INDEX_NAME,NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS names,MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=%s GROUP BY INDEX_NAME,NON_UNIQUE", (table,))
            if not any(r['NON_UNIQUE'] == 0 and r['names'] == 'submission_id' and not r['prefix_length'] for r in cursor.fetchall()):
                issues.append(f'{table}: full single-column submission_id UNIQUE index required.')
        found = set()
        if 'permissions' in engines:
            cursor.execute('SELECT permission_code FROM permissions WHERE permission_code IN (%s,%s,%s,%s)', PERMISSIONS)
            found = {row['permission_code'] for row in cursor.fetchall()}
        for code in PERMISSIONS:
            if code not in found:
                issues.append(f'Authorization permission code missing: {code}; operator review required, no grants applied.')
    return Inspection(tuple(issues))
