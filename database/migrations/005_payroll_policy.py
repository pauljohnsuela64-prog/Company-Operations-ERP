"""Explicit additive Payroll policy foundation. No configuration or connection on import."""
import argparse
from getpass import getpass
import hashlib
import json
import re

import mysql.connector

TABLE_OPTIONS = 'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci'
TRIGGER_SQL_MODE = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties),
                additionalProperties=False, maxProperties=len(properties))


def choices(*values):
    return {'enum': list(values)}


# These are bounded vocabularies, not executable formulas or company approvals.
# UNRESOLVED is permitted in drafts only. BLOCK is an explicit supported restriction.
JSON_RULES = {
    'cutoff_rules': object_schema(dict(a_start=choices(1), a_end=choices(15),
                                      b_start=choices(16), b_end=choices('MONTH_END'))),
    'supported_pay_types': dict(type='array', items=choices('MONTHLY'), minItems=1,
                                maxItems=1, uniqueItems=True),
    'attendance_rules': object_schema(dict(
        missing_evidence=choices('BLOCK'),
        late_treatment=choices('UNRESOLVED', 'NO_DEDUCTION', 'BLOCK'),
        absence_treatment=choices('UNRESOLVED', 'PERIOD_WORKDAY_DIVISOR', 'BLOCK'),
        half_day_treatment=choices('UNRESOLVED', 'HALF_DAY_DEDUCTION', 'BLOCK'))),
    'leave_rules': object_schema(dict(
        paid_leave_treatment=choices('UNRESOLVED', 'NO_DEDUCTION', 'BLOCK'),
        unpaid_leave_treatment=choices('UNRESOLVED', 'PERIOD_WORKDAY_DIVISOR', 'BLOCK'),
        conflict=choices('BLOCK'))),
    'eligibility_rules': object_schema(dict(proration=choices('BLOCK'),
        full_cutoff_eligibility=choices('UNRESOLVED', 'VERIFIED_FULL_CUTOFF_ONLY'))),
    'deduction_rules': object_schema(dict(
        excess_deductions=choices('UNRESOLVED', 'ZERO_FLOOR', 'BLOCK'),
        statutory=choices('UNRESOLVED', 'EXTERNAL_APPROVED_PROCESS', 'BLOCK'),
        odd_cent_handling=choices('UNRESOLVED', 'ROUND_EACH_CUTOFF', 'BLOCK'))),
    'payment_rules': object_schema(dict(mode=choices('MANUAL'))),
}

VERSION_COLUMNS = [
    ('policy_version_id', 'INT NOT NULL AUTO_INCREMENT'),
    ('version_number', 'INT UNSIGNED NOT NULL'),
    ('policy_name', 'VARCHAR(100) NOT NULL'),
    ('status', "ENUM('DRAFT','APPROVED') NOT NULL DEFAULT 'DRAFT'"),
    ('revision', 'INT UNSIGNED NOT NULL DEFAULT 1'),
    ('effective_from', 'DATE NOT NULL'),
    ('calculator_key', 'VARCHAR(40) NOT NULL'),
    ('calendar_key', 'VARCHAR(40) NOT NULL'),
    ('frequency', 'VARCHAR(20) NOT NULL'),
    ('cutoff_rules', 'JSON NOT NULL'),
    ('working_week_mask', 'TINYINT UNSIGNED NOT NULL'),
    ('supported_pay_types', 'JSON NOT NULL'),
    ('currency_code', 'CHAR(3) NOT NULL'),
    ('full_cutoff_divisor', 'TINYINT UNSIGNED NOT NULL'),
    ('rounding_mode', 'VARCHAR(20) NOT NULL'),
    ('rounding_scale', 'TINYINT UNSIGNED NOT NULL'),
    *[(name, 'JSON NOT NULL') for name in ('attendance_rules', 'leave_rules',
       'eligibility_rules', 'deduction_rules', 'payment_rules')],
    ('configuration_hash', 'CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL'),
    ('created_by', 'INT NOT NULL'), ('updated_by', 'INT NOT NULL'),
    ('approved_by', 'INT NULL'),
    ('created_at', 'DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)'),
    ('updated_at', 'DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)'),
    ('approved_at', 'DATETIME(6) NULL'),
    ('approval_reference', 'VARCHAR(255) NULL'),
]
ACTIVATION_COLUMNS = [('effective_from', 'DATE NOT NULL'),
                      ('policy_version_id', 'INT NOT NULL'), ('activated_by', 'INT NOT NULL'),
                      ('activated_at', 'DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)')]
PERIOD_COLUMNS = [('policy_version_id', 'INT NULL'),
                  ('cutoff_code', "ENUM('A','B') CHARACTER SET ascii COLLATE ascii_bin NULL")]


def conjunction(*expressions):
    return ' AND '.join('(' + expression + ')' for expression in expressions)


VERSION_CHECKS = {
    'chk_ppv_numbers': conjunction('version_number > 0', 'revision > 0'),
    'chk_ppv_name': 'CHAR_LENGTH(TRIM(policy_name)) > 0',
    'chk_ppv_template': conjunction(
        "CAST(calculator_key AS CHAR CHARSET binary) = CAST('MONTHLY_SEMIMONTHLY_V1' AS CHAR CHARSET binary)",
        "CAST(calendar_key AS CHAR CHARSET binary) = CAST('SEMI_MONTHLY_1_15_16_EOM_V1' AS CHAR CHARSET binary)",
        "CAST(frequency AS CHAR CHARSET binary) = CAST('SEMI_MONTHLY' AS CHAR CHARSET binary)", 'working_week_mask = 31',
        "CAST(currency_code AS CHAR CHARSET binary) = CAST('PHP' AS CHAR CHARSET binary)", 'full_cutoff_divisor = 2',
        "CAST(rounding_mode AS CHAR CHARSET binary) = CAST('ROUND_HALF_UP' AS CHAR CHARSET binary)", 'rounding_scale = 2',
        'DAYOFMONTH(effective_from) IN (1,16)'),
    'chk_ppv_metadata': """(status = 'DRAFT' AND approved_by IS NULL
        AND approved_at IS NULL AND configuration_hash IS NULL)
        OR (status = 'APPROVED' AND approved_by IS NOT NULL AND approved_at IS NOT NULL
        AND configuration_hash IS NOT NULL
        AND REGEXP_LIKE(configuration_hash, '^[0-9a-f]{64}$', 'c'))""",
}
for field, schema in JSON_RULES.items():
    literal = json.dumps(schema, separators=(',', ':')).replace("'", "''")
    VERSION_CHECKS['chk_ppv_' + field] = f"JSON_SCHEMA_VALID('{literal}', {field})"
VERSION_CHECKS['chk_ppv_resolved'] = "status = 'DRAFT' OR (" + conjunction(*[
    f"JSON_SEARCH({field}, 'one', 'UNRESOLVED') IS NULL"
    for field in ('attendance_rules', 'leave_rules', 'eligibility_rules', 'deduction_rules')]) + ')'

PERIOD_CHECKS = {'chk_payroll_period_policy_pair':
    "(policy_version_id IS NULL AND cutoff_code IS NULL) OR "
    "(policy_version_id IS NOT NULL AND cutoff_code IS NOT NULL AND cutoff_code IN ('A','B'))"}

# index name -> (unique, ordered columns)
VERSION_INDEXES = {
    'PRIMARY': (True, ('policy_version_id',)),
    'uq_ppv_number': (True, ('version_number',)),
    'uq_ppv_id_date': (True, ('policy_version_id', 'effective_from')),
    'idx_ppv_status_date': (False, ('status', 'effective_from')),
    **{'idx_ppv_' + name: (False, (name,)) for name in ('created_by','updated_by','approved_by')},
}
ACTIVATION_INDEXES = {
    'PRIMARY': (True, ('effective_from',)),
    'uq_ppa_version': (True, ('policy_version_id',)),
    'idx_ppa_version_date': (False, ('policy_version_id', 'effective_from')),
    'idx_ppa_actor': (False, ('activated_by',)),
}
PERIOD_INDEXES = {
    'idx_payroll_period_policy_dates': (False, ('policy_version_id','start_date','end_date','status')),
    'idx_payroll_period_dates_status': (False, ('start_date','end_date','status')),
}
# FK name -> (local columns, target table, target columns, delete rule, update rule)
VERSION_FKS = {'fk_ppv_' + field: ((field,), 'users', ('user_id',), 'RESTRICT', 'RESTRICT')
               for field in ('created_by','updated_by','approved_by')}
ACTIVATION_FKS = {
    'fk_ppa_version_date': (('policy_version_id','effective_from'), 'payroll_policy_versions',
                            ('policy_version_id','effective_from'), 'RESTRICT', 'RESTRICT'),
    'fk_ppa_actor': (('activated_by',), 'users', ('user_id',), 'RESTRICT', 'RESTRICT'),
}
PERIOD_FKS = {'fk_payroll_period_policy': (('policy_version_id',), 'payroll_policy_activations',
                                         ('policy_version_id',), 'RESTRICT', 'RESTRICT')}
TABLES = {
    'payroll_policy_versions': (VERSION_COLUMNS, VERSION_INDEXES, VERSION_FKS, VERSION_CHECKS),
    'payroll_policy_activations': (ACTIVATION_COLUMNS, ACTIVATION_INDEXES, ACTIVATION_FKS, {}),
    'payroll_periods': (PERIOD_COLUMNS, PERIOD_INDEXES, PERIOD_FKS, PERIOD_CHECKS),
}

# name -> (table, event, body); approval starts with a DRAFT, never an INSERT of APPROVED.
TRIGGERS = {
    'ppv_before_insert': ('payroll_policy_versions', 'INSERT', """BEGIN
        IF NEW.status <> 'DRAFT' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Create a draft policy before approval';
        END IF;
    END"""),
    'ppv_before_update': ('payroll_policy_versions', 'UPDATE', """BEGIN
        IF OLD.status = 'APPROVED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Approved payroll policy is immutable';
        END IF;
        IF NEW.policy_version_id <> OLD.policy_version_id OR NEW.version_number <> OLD.version_number
            OR NEW.created_by <> OLD.created_by OR NEW.created_at <> OLD.created_at THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payroll policy identity is immutable';
        END IF;
        IF NEW.revision <> OLD.revision + 1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Increment payroll policy revision exactly once';
        END IF;
    END"""),
    'ppv_before_delete': ('payroll_policy_versions', 'DELETE', """BEGIN
        IF OLD.status = 'APPROVED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Approved payroll policy cannot be deleted';
        END IF;
    END"""),
    'ppa_before_insert': ('payroll_policy_activations', 'INSERT', """BEGIN
        DECLARE policy_status VARCHAR(20) DEFAULT NULL;
        SELECT status INTO policy_status FROM payroll_policy_versions
            WHERE policy_version_id = NEW.policy_version_id FOR SHARE;
        IF policy_status IS NULL OR policy_status <> 'APPROVED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Only approved payroll policies can be activated';
        END IF;
    END"""),
    'ppa_before_update': ('payroll_policy_activations', 'UPDATE', """BEGIN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payroll activation history is immutable';
    END"""),
    'ppa_before_delete': ('payroll_policy_activations', 'DELETE', """BEGIN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Payroll activation history cannot be deleted';
    END"""),
}


def _sql_tokens(value):
    # CHECK_CLAUSE escapes quotes; this contract has no embedded apostrophe literals.
    value = value.replace("\\'", "'").replace('\\"', '"')
    value = re.sub(r"_(?:utf8mb4|ascii)(?=')", '', value, flags=re.I)
    tokens = re.findall(r"'(?:''|\\.|[^'])*'|`[^`]*`|[A-Za-z0-9_$]+|[^\s]", value)
    return [token if token.startswith("'") else token.strip('`').lower() for token in tokens]


def _strip_enclosing(tokens):
    while tokens and tokens[0] == '(' and tokens[-1] == ')':
        depth = 0
        for index, token in enumerate(tokens):
            if token == '(': depth += 1
            if token == ')': depth -= 1
            if depth == 0 and index != len(tokens)-1: break
        else:
            tokens = tokens[1:-1]
            continue
        break
    return tokens


def _normal_sql(value):
    """Normalize formatting without erasing literal case or expression grouping."""
    return tuple(_strip_enclosing(_sql_tokens(value)))


def _normal_check(value):
    # MySQL adds parentheses to each AND/OR operand in CHECK_CLAUSE. Compare
    # their boolean tree, retaining grouping and operator order. The manifest
    # does not use BETWEEN or other constructs with an embedded AND keyword.
    def tree(tokens):
        tokens = _strip_enclosing(tokens)
        for operator in ('or', 'and'):
            depth = 0; start = 0; parts = []
            for index, token in enumerate(tokens):
                if token == '(': depth += 1
                if token == ')': depth -= 1
                if depth == 0 and token == operator:
                    parts.append(tokens[start:index]); start = index+1
            if parts:
                parts.append(tokens[start:])
                return (operator, tuple(tree(part) for part in parts))
        return tuple(tokens)
    return tree(_sql_tokens(value))


def _rows(cursor, query, params=()):
    cursor.execute(query, params)
    return cursor.fetchall()


def _columns(cursor, table):
    return {row['COLUMN_NAME']: row for row in _rows(cursor, """SELECT COLUMN_NAME,COLUMN_TYPE,
        IS_NULLABLE,COLUMN_DEFAULT,EXTRA,CHARACTER_SET_NAME,COLLATION_NAME,GENERATION_EXPRESSION
        FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s""", (table,))}


def _verify_column(table, name, definition, actual, *, explicit_charset=False):
    type_match = re.match(r"(?:ENUM\([^)]*\)|[A-Z]+(?:\(\d+(?:,\d+)?\))?)(?: UNSIGNED)?", definition)
    expected_type = type_match[0]
    nullable = 'NO' if 'NOT NULL' in definition else 'YES'
    default_match = re.search(r" DEFAULT ('[^']*'|CURRENT_TIMESTAMP\(6\)|\d+)", definition)
    default = default_match[1].strip("'") if default_match else None
    if isinstance(default, str) and default.startswith('CURRENT_TIMESTAMP'):
        default = default.lower()
    actual_default = actual['COLUMN_DEFAULT']
    if isinstance(actual_default, str) and actual_default.lower().startswith('current_timestamp'):
        actual_default = actual_default.lower()
    extra = actual['EXTRA'].lower().replace('default_generated', '').strip()
    expected_extra = 'auto_increment' if 'AUTO_INCREMENT' in definition else ''
    if 'ON UPDATE' in definition: expected_extra = 'on update current_timestamp(6)'
    expected_charset = ('ascii','ascii_bin') if 'CHARACTER SET ascii' in definition else ('utf8mb4','utf8mb4_0900_ai_ci')
    text_type = expected_type.lower().startswith(('varchar','char','enum'))
    actual_type = re.sub(r'\b(tinyint|smallint|int|bigint)\(\d+\)', r'\1', actual['COLUMN_TYPE'], flags=re.I)
    if (_normal_sql(actual_type) != _normal_sql(expected_type) or actual['IS_NULLABLE'] != nullable
            or actual_default != default or extra != expected_extra or actual['GENERATION_EXPRESSION']
            or (explicit_charset and text_type and
                (actual['CHARACTER_SET_NAME'],actual['COLLATION_NAME']) != expected_charset)):
        raise RuntimeError(f'Incompatible column {table}.{name}; manual review required.')


def _indexes(cursor, table):
    result = {}
    for row in _rows(cursor, """SELECT INDEX_NAME,NON_UNIQUE,COLUMN_NAME,SUB_PART,INDEX_TYPE,
        IS_VISIBLE,COLLATION FROM information_schema.statistics
        WHERE table_schema=DATABASE() AND table_name=%s ORDER BY INDEX_NAME,SEQ_IN_INDEX""", (table,)):
        item = result.setdefault(row['INDEX_NAME'], [not row['NON_UNIQUE'], []])
        item[1].append(row['COLUMN_NAME'])
        if row['SUB_PART'] is not None or row['INDEX_TYPE'] != 'BTREE' or row['IS_VISIBLE'] != 'YES' or row['COLLATION'] != 'A':
            raise RuntimeError(f'Incompatible index {table}.{row["INDEX_NAME"]}.')
    return {name:(item[0],tuple(item[1])) for name,item in result.items()}


def _foreign_keys(cursor, table):
    result = {}
    for row in _rows(cursor, """SELECT k.CONSTRAINT_NAME,k.COLUMN_NAME,k.REFERENCED_TABLE_SCHEMA,
        k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE
        FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r
        ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME
        AND r.TABLE_NAME=k.TABLE_NAME WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s
        ORDER BY k.CONSTRAINT_NAME,k.ORDINAL_POSITION""", (table,)):
        item = result.setdefault(row['CONSTRAINT_NAME'], [[],row['REFERENCED_TABLE_NAME'],[],row['DELETE_RULE'],row['UPDATE_RULE']])
        if row['REFERENCED_TABLE_SCHEMA'] != cursor._policy_database:
            raise RuntimeError('Cross-database foreign key requires manual review.')
        item[0].append(row['COLUMN_NAME']); item[2].append(row['REFERENCED_COLUMN_NAME'])
    return {name:(tuple(v[0]),v[1],tuple(v[2]),v[3],v[4]) for name,v in result.items()}


def _checks(cursor, table):
    result = {}
    for row in _rows(cursor, """SELECT t.CONSTRAINT_NAME,c.CHECK_CLAUSE,t.ENFORCED
        FROM information_schema.table_constraints t JOIN information_schema.check_constraints c
        ON c.CONSTRAINT_SCHEMA=t.CONSTRAINT_SCHEMA AND c.CONSTRAINT_NAME=t.CONSTRAINT_NAME
        WHERE t.TABLE_SCHEMA=DATABASE() AND t.TABLE_NAME=%s AND t.CONSTRAINT_TYPE='CHECK'""", (table,)):
        if row['ENFORCED'] != 'YES': raise RuntimeError(f'Unenforced check {table}.{row["CONSTRAINT_NAME"]}.')
        result[row['CONSTRAINT_NAME']] = _normal_check(row['CHECK_CLAUSE'])
    return result


def _verify_objects(actual, expected, label, *, complete=False, exclusive=False):
    for name,value in expected.items():
        if name in actual and actual[name] != value:
            raise RuntimeError(f'Incompatible {label} {name}; manual review required.')
        if complete and name not in actual: raise RuntimeError(f'Missing {label} {name}.')
    if exclusive and set(actual)-set(expected):
        raise RuntimeError(f'Unexpected {label}: {sorted(set(actual)-set(expected))}; manual review required.')


def _table_exists(cursor, table):
    rows = _rows(cursor, """SELECT ENGINE,TABLE_COLLATION FROM information_schema.tables
        WHERE table_schema=DATABASE() AND table_name=%s""", (table,))
    if not rows: return False
    if rows[0]['ENGINE'] != 'InnoDB': raise RuntimeError(f'{table} must use InnoDB.')
    if table.startswith('payroll_policy_') and rows[0]['TABLE_COLLATION'] != 'utf8mb4_0900_ai_ci':
        raise RuntimeError(f'Incompatible collation for {table}.')
    return True


def _verify_table(cursor, table, *, complete=False):
    if not _table_exists(cursor, table):
        if complete: raise RuntimeError(f'Missing table {table}.')
        return
    columns,indexes,fks,checks = TABLES[table]
    actual = _columns(cursor, table)
    exclusive = table != 'payroll_periods'
    for name,definition in columns:
        if name in actual:
            _verify_column(table,name,definition,actual[name],explicit_charset=exclusive or name=='cutoff_code')
        elif complete or exclusive:
            raise RuntimeError(f'Missing column {table}.{name}; manual review required.')
    if exclusive and set(actual) != {name for name,_ in columns}:
        raise RuntimeError(f'Unexpected columns in {table}.')
    actual_indexes = _indexes(cursor,table)
    actual_fks = _foreign_keys(cursor,table)
    actual_checks = _checks(cursor,table)
    if not exclusive:
        owned = {name for name,_ in columns}
        for name,(_,fields) in actual_indexes.items():
            if owned.intersection(fields) and name not in indexes:
                raise RuntimeError(f'Unexpected index on policy columns: {name}.')
        for name,(fields,*_) in actual_fks.items():
            if owned.intersection(fields) and name not in fks:
                raise RuntimeError(f'Unexpected foreign key on policy columns: {name}.')
        for name,expression in actual_checks.items():
            if name not in checks and any(field in str(expression) for field in owned):
                raise RuntimeError(f'Unexpected check on policy columns: {name}.')
    _verify_objects(actual_indexes,indexes,f'{table} index',complete=complete,exclusive=exclusive)
    _verify_objects(actual_fks,fks,f'{table} foreign key',complete=complete,exclusive=exclusive)
    _verify_objects(actual_checks,{n:_normal_check(v) for n,v in checks.items()},
                    f'{table} check',complete=complete,exclusive=exclusive)


def _verify_triggers(cursor, *, complete=False):
    rows = _rows(cursor, """SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,
        ACTION_ORIENTATION,ACTION_STATEMENT,SQL_MODE FROM information_schema.triggers
        WHERE TRIGGER_SCHEMA=DATABASE()""")
    found = set()
    for row in rows:
        name = row['TRIGGER_NAME']
        if name not in TRIGGERS:
            if row['EVENT_OBJECT_TABLE'] in ('payroll_policy_versions','payroll_policy_activations'):
                raise RuntimeError(f'Unexpected policy trigger {name}.')
            continue
        found.add(name); table,event,body = TRIGGERS[name]
        modes = row['SQL_MODE']
        modes = set(modes.split(',')) if isinstance(modes,str) else set(modes)
        if ((row['EVENT_OBJECT_TABLE'],row['EVENT_MANIPULATION'],row['ACTION_TIMING'],row['ACTION_ORIENTATION'])
                != (table,event,'BEFORE','ROW') or _normal_sql(row['ACTION_STATEMENT']) != _normal_sql(body)
                or modes != set(TRIGGER_SQL_MODE.split(','))):
            raise RuntimeError(f'Incompatible trigger {name}; manual review required.')
    if complete and found != set(TRIGGERS): raise RuntimeError('Missing policy immutability triggers.')
    return found


def _prerequisites(cursor):
    cursor.execute('SELECT VERSION() AS version, DATABASE() AS database_name')
    row = cursor.fetchone()
    if not row['database_name']: raise RuntimeError('Select an explicit target database.')
    version = re.match(r'(\d+)\.(\d+)\.(\d+)', row['version'])
    if not version or 'mariadb' in row['version'].lower() or tuple(map(int,version.groups())) < (8,0,17):
        raise RuntimeError('MySQL 8.0.17 or later is required (enforced CHECK and JSON_SCHEMA_VALID).')
    cursor._policy_database = row['database_name']
    for table in ('users','roles','permissions','role_permissions','audit_logs','employee_compensation',
                  'payroll_periods','payroll_entries','payroll_adjustments','employees',
                  'attendance_records','leave_requests','leave_types','payroll_input_guard'):
        if not _table_exists(cursor,table): raise RuntimeError(f'Prerequisite {table} is missing; apply/verify 004 first.')
    required = {
        'users': [('user_id','INT NOT NULL AUTO_INCREMENT')],
        'permissions': [('permission_id','INT NOT NULL AUTO_INCREMENT'),('permission_code','VARCHAR(100) NOT NULL')],
        'payroll_input_guard': [('guard_id','TINYINT NOT NULL')],
        'payroll_periods': [('payroll_period_id','INT NOT NULL AUTO_INCREMENT'),
            ('period_number','VARCHAR(50) NOT NULL'),('period_name','VARCHAR(100) NOT NULL'),
            ('start_date','DATE NOT NULL'),('end_date','DATE NOT NULL'),('pay_date','DATE NOT NULL'),
            ('status',"ENUM('DRAFT','PROCESSING','APPROVED','PAID','CANCELLED') NOT NULL DEFAULT 'DRAFT'")],
        'payroll_entries': [('payroll_entry_id','INT NOT NULL AUTO_INCREMENT'),
            ('calculation_input_version','SMALLINT UNSIGNED NULL'),
            ('calculation_input_hash','CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL')],
        'employee_compensation': [('basic_rate','DECIMAL(12,2) NOT NULL')],
        'payroll_adjustments': [('amount','DECIMAL(12,2) NOT NULL')],
        'audit_logs': [('audit_log_id','BIGINT NOT NULL AUTO_INCREMENT'),('user_id','INT NULL'),
            ('module','VARCHAR(50) NOT NULL'),('action','VARCHAR(50) NOT NULL'),('entity_id','VARCHAR(100) NULL')],
    }
    for table,columns in required.items():
        actual = _columns(cursor,table)
        for name,definition in columns:
            if name not in actual: raise RuntimeError(f'Prerequisite {table}.{name} missing; verify migration 004.')
            _verify_column(table,name,definition,actual[name],
                           explicit_charset=name=='calculation_input_hash')
    guard_columns = _columns(cursor,'payroll_input_guard')
    if set(guard_columns) != {'guard_id'} or _indexes(cursor,'payroll_input_guard') != {'PRIMARY':(True,('guard_id',))}:
        raise RuntimeError('Incompatible migration 004 coordination structure.')
    cursor.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id=1')
    if not cursor.fetchone(): raise RuntimeError('Migration 004 coordination row is missing.')
    _verify_objects(_indexes(cursor,'users'),{'PRIMARY':(True,('user_id',))},'users primary key',complete=True)
    _verify_objects(_indexes(cursor,'payroll_periods'),{
        'PRIMARY':(True,('payroll_period_id',)), 'period_number':(True,('period_number',)),
        'period_name':(True,('period_name',))},'period constraint',complete=True)
    _verify_objects(_checks(cursor,'payroll_periods'),{
        'chk_payroll_period_dates':_normal_check('end_date >= start_date'),
        'chk_payroll_period_pay_date':_normal_check('pay_date >= end_date')},'period check',complete=True)
    _verify_objects(_foreign_keys(cursor,'payroll_periods'),{
        'fk_payroll_period_'+field: ((field,), 'users', ('user_id',), 'NO ACTION', 'NO ACTION')
        for field in ('created_by','updated_by','submitted_by','approved_by','paid_by')},'period foreign key',complete=True)


def _index_ddl(name, definition):
    unique, columns = definition
    prefix = 'PRIMARY KEY' if name == 'PRIMARY' else ('UNIQUE INDEX' if unique else 'INDEX') + ' `' + name + '`'
    return prefix + ' (' + ','.join('`'+c+'`' for c in columns) + ')'


def _fk_ddl(name, definition):
    columns,target,remote,delete,update = definition
    return (f'CONSTRAINT `{name}` FOREIGN KEY (' + ','.join('`'+c+'`' for c in columns)
            + f') REFERENCES `{target}` (' + ','.join('`'+c+'`' for c in remote)
            + f') ON DELETE {delete} ON UPDATE {update}')


def _execute_ddl(cursor, statement):
    cursor.execute(statement)


def upgrade(connection):
    if connection.in_transaction:
        raise RuntimeError('Use a fresh migration connection with no pending business transaction.')
    cursor = connection.cursor(dictionary=True)
    lock_name = None
    saved_mode = None
    try:
        _prerequisites(cursor)
        lock_name = 'erp_policy_005_' + hashlib.sha256(cursor._policy_database.encode()).hexdigest()[:32]
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired',(lock_name,))
        if cursor.fetchone()['acquired'] != 1:
            lock_name = None
            raise RuntimeError('Another migration 005 is running. Retry after it finishes.')
        # Preflight all existing objects before any DDL. Never replace incompatible definitions.
        for table in TABLES: _verify_table(cursor,table)
        existing_triggers = _verify_triggers(cursor)
        cursor.execute('SELECT @@SESSION.sql_mode AS mode')
        saved_mode = cursor.fetchone()['mode']
        cursor.execute('SET SESSION sql_mode=%s',(TRIGGER_SQL_MODE,))
        for table,(columns,indexes,fks,checks) in TABLES.items():
            if not _table_exists(cursor,table):
                parts = ['`'+name+'` '+definition for name,definition in columns]
                parts += [_index_ddl(name,d) for name,d in indexes.items()]
                parts += [_fk_ddl(name,d) for name,d in fks.items()]
                parts += [f'CONSTRAINT `{name}` CHECK ({body})' for name,body in checks.items()]
                _execute_ddl(cursor,f'CREATE TABLE `{table}` (' + ',\n'.join(parts) + ') ' + TABLE_OPTIONS)
            else:
                actual = _columns(cursor,table)
                for name,definition in columns:
                    if name not in actual: _execute_ddl(cursor,f'ALTER TABLE `{table}` ADD COLUMN `{name}` {definition}')
                for name,d in indexes.items():
                    if name not in _indexes(cursor,table): _execute_ddl(cursor,f'ALTER TABLE `{table}` ADD '+_index_ddl(name,d))
                for name,d in fks.items():
                    if name not in _foreign_keys(cursor,table): _execute_ddl(cursor,f'ALTER TABLE `{table}` ADD '+_fk_ddl(name,d))
                for name,body in checks.items():
                    if name not in _checks(cursor,table): _execute_ddl(cursor,f'ALTER TABLE `{table}` ADD CONSTRAINT `{name}` CHECK ({body})')
        for name,(table,event,body) in TRIGGERS.items():
            if name not in existing_triggers:
                _execute_ddl(cursor,f'CREATE TRIGGER `{name}` BEFORE {event} ON `{table}` FOR EACH ROW {body}')
        for table in TABLES: _verify_table(cursor,table,complete=True)
        _verify_triggers(cursor,complete=True)
        connection.commit()
    finally:
        # DDL may already have committed. No destructive rollback/repair is attempted.
        connection.rollback()
        if saved_mode is not None: cursor.execute('SET SESSION sql_mode=%s',(saved_mode,))
        if lock_name is not None:
            cursor.execute('SELECT RELEASE_LOCK(%s)',(lock_name,)); cursor.fetchall()
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('host','user','database'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',type=int,required=True)
    args = parser.parse_args()
    with mysql.connector.connect(host=args.host,port=args.port,user=args.user,
                                 password=getpass('MySQL password: '),database=args.database) as connection:
        upgrade(connection)
    print('Payroll policy foundation applied/verified. No policies, grants or historical references were populated.')


if __name__ == '__main__':
    main()
