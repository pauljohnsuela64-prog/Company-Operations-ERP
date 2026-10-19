"""Explicit additive certification schema upgrade. No application or salary cutover."""
import argparse
from getpass import getpass
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import mysql.connector

# Reuse the frozen 005 metadata comparison rules without executing its upgrade.
_spec = spec_from_file_location('certification_prerequisite_005', Path(__file__).with_name('005_payroll_policy.py'))
base = module_from_spec(_spec)
_spec.loader.exec_module(base)

OPTIONS = base.TABLE_OPTIONS
MODE = base.TRIGGER_SQL_MODE
CERT = 'payroll_cutoff_certifications'
MEMBER = 'payroll_certification_members'
EVENT = 'payroll_certification_events'
EVIDENCE = 'payroll_calculation_evidence'
DIGEST = 'VARCHAR(65) CHARACTER SET ascii COLLATE ascii_bin'
CODE = "ENUM('A','B') CHARACTER SET ascii COLLATE ascii_bin NOT NULL"


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


REFERENCE = dict(type='string', minLength=1, maxLength=255)
DATES = dict(type='array', maxItems=16, uniqueItems=True,
             items=dict(type='string', minLength=10, maxLength=10, pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'))
IDS = dict(type='array', maxItems=100000, uniqueItems=True,
           items=dict(type='integer', minimum=1, maximum=2147483647))
EXCEPTIONS = dict(type='array', maxItems=1000, items=object_schema(dict(
    date=dict(type='string', minLength=10, maxLength=10, pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
    kind=dict(enum=['HOLIDAY','SPECIAL_PAY','SCHEDULE_EXCEPTION']), source_reference=REFERENCE)))
ROSTER_SCHEMA = object_schema(dict(kind=dict(enum=['EXPLICIT_EMPLOYEE_ROSTER']), employee_ids=IDS))
CALENDAR_SCHEMA = object_schema(dict(timezone=dict(enum=['Asia/Manila']), working_week_mask=dict(enum=[31]),
                                   scheduled_dates=DATES, exceptions=EXCEPTIONS))
SCHEDULE_SCHEMA = object_schema(dict(scheduled_dates=DATES, exceptions=EXCEPTIONS))
PAYLOAD_SCHEMA = object_schema(dict(format_version=dict(enum=[2]),
    inputs=dict(type='object'), outputs=dict(type='object')))


def json_check(column, schema):
    literal = json.dumps(schema, separators=(',', ':')).replace("'", "''")
    return f"JSON_SCHEMA_VALID('{literal}', {column})"


def digest_check(column, nullable=False):
    value = f"({column} IS NOT NULL AND CHAR_LENGTH({column}) = 64 AND REGEXP_LIKE({column}, '^[0-9a-f]{{64}}$', 'c'))"
    return f'({column} IS NULL OR {value})' if nullable else value


def ref_check(column):
    return f"({column} IS NOT NULL AND CHAR_LENGTH(TRIM({column})) > 0)"


def fk(columns, table, target):
    return (tuple(columns), table, tuple(target), 'RESTRICT', 'RESTRICT')


TABLES = {
    CERT: ([
        ('certification_id','BIGINT UNSIGNED NOT NULL AUTO_INCREMENT'),
        ('payroll_period_id','INT NOT NULL'), ('policy_version_id','INT NOT NULL'),
        ('revision','INT UNSIGNED NOT NULL'), ('predecessor_certification_id','BIGINT UNSIGNED NULL'),
        ('cutoff_code',CODE), ('start_date','DATE NOT NULL'), ('end_date','DATE NOT NULL'),
        ('roster_scope','JSON NOT NULL'), ('roster_source_reference','VARCHAR(255) NOT NULL'),
        ('calendar_source_reference','VARCHAR(255) NOT NULL'), ('calendar_configuration','JSON NOT NULL'),
        ('source_digest',DIGEST+' NOT NULL'), ('configuration_digest',DIGEST+' NOT NULL'),
        ('certification_digest',DIGEST+' NULL'), ('evidence_format_version','SMALLINT UNSIGNED NOT NULL DEFAULT 1'),
        ('state',"ENUM('ASSEMBLY','SEALED') NOT NULL DEFAULT 'ASSEMBLY'"),
        ('created_by','INT NOT NULL'), ('created_at','DATETIME(6) NOT NULL'),
        ('certified_by','INT NULL'), ('certified_at','DATETIME(6) NULL'),
    ], {
        'PRIMARY':(True,('certification_id',)), 'uq_pcc_revision':(True,('payroll_period_id','revision')),
        'uq_pcc_predecessor':(True,('predecessor_certification_id',)),
        'uq_pcc_period':(True,('certification_id','payroll_period_id')),
        'idx_pcc_policy':(False,('policy_version_id',)),
        'idx_pcc_creator':(False,('created_by',)), 'idx_pcc_certifier':(False,('certified_by',)),
    }, {
        'fk_pcc_period':fk(['payroll_period_id'],'payroll_periods',['payroll_period_id']),
        'fk_pcc_policy':fk(['policy_version_id'],'payroll_policy_activations',['policy_version_id']),
        'fk_pcc_predecessor':fk(['predecessor_certification_id'],CERT,['certification_id']),
        'fk_pcc_creator':fk(['created_by'],'users',['user_id']),
        'fk_pcc_certifier':fk(['certified_by'],'users',['user_id']),
    }, {
        'chk_pcc_numbers':'revision > 0 AND evidence_format_version = 1',
        'chk_pcc_dates':"start_date >= '1000-01-01' AND end_date >= start_date",
        'chk_pcc_refs':ref_check('roster_source_reference')+' AND '+ref_check('calendar_source_reference'),
        'chk_pcc_roster':json_check('roster_scope',ROSTER_SCHEMA),
        'chk_pcc_calendar':json_check('calendar_configuration',CALENDAR_SCHEMA),
        'chk_pcc_digests':digest_check('source_digest')+' AND '+digest_check('configuration_digest')+' AND '+digest_check('certification_digest',True),
        'chk_pcc_seal':"(state='ASSEMBLY' AND certified_by IS NULL AND certified_at IS NULL AND certification_digest IS NULL) OR (state='SEALED' AND certified_by IS NOT NULL AND certified_at IS NOT NULL AND certification_digest IS NOT NULL)",
    }),
    MEMBER: ([
        ('certification_id','BIGINT UNSIGNED NOT NULL'), ('employee_id','INT NOT NULL'),
        ('disposition',"ENUM('INCLUDE','EXCLUDE') NOT NULL"),
        ('eligibility',"ENUM('UNRESOLVED','FULL_CUTOFF','NOT_ELIGIBLE') NOT NULL DEFAULT 'UNRESOLVED'"),
        ('verification_status',"ENUM('UNVERIFIED','VERIFIED') NOT NULL DEFAULT 'UNVERIFIED'"),
        ('exclusion_reason','VARCHAR(255) NULL'), ('exclusion_reference','VARCHAR(255) NULL'),
        ('hire_date_snapshot','DATE NULL'), ('employment_status_snapshot','VARCHAR(30) NULL'),
        ('employment_coverage_start','DATE NULL'), ('employment_coverage_end','DATE NULL'),
        ('employment_reference','VARCHAR(255) NULL'), ('compensation_id','INT NULL'),
        ('basic_rate','DECIMAL(12,2) NULL'), ('pay_type',"ENUM('MONTHLY','DAILY','HOURLY') NULL"),
        ('currency_code','CHAR(3) NULL'), ('compensation_effective_date','DATE NULL'),
        ('compensation_coverage_end','DATE NULL'), ('compensation_reference','VARCHAR(255) NULL'),
        ('schedule_evidence','JSON NOT NULL'), ('material_source_digest',DIGEST+' NOT NULL'),
    ], {
        'PRIMARY':(True,('certification_id','employee_id')),
        'idx_pcm_employee':(False,('employee_id',)), 'idx_pcm_compensation':(False,('compensation_id','employee_id')),
    }, {
        'fk_pcm_certification':fk(['certification_id'],CERT,['certification_id']),
        'fk_pcm_employee':fk(['employee_id'],'employees',['employee_id']),
        'fk_pcm_compensation':fk(['compensation_id','employee_id'],'employee_compensation',['compensation_id','employee_id']),
    }, {
        'chk_pcm_digest':digest_check('material_source_digest'),
        'chk_pcm_schedule':json_check('schedule_evidence',SCHEDULE_SCHEMA),
        'chk_pcm_rate':'basic_rate IS NULL OR basic_rate > 0',
        'chk_pcm_exclusion':"disposition <> 'EXCLUDE' OR ("+ref_check('exclusion_reason')+' AND '+ref_check('exclusion_reference')+')',
        'chk_pcm_dates':"(hire_date_snapshot IS NULL OR hire_date_snapshot >= '1000-01-01') AND (employment_coverage_start IS NULL OR employment_coverage_start >= '1000-01-01') AND (employment_coverage_end IS NULL OR employment_coverage_end >= '1000-01-01') AND (employment_coverage_start IS NULL OR employment_coverage_end IS NULL OR employment_coverage_end >= employment_coverage_start) AND (compensation_effective_date IS NULL OR compensation_effective_date >= '1000-01-01') AND (compensation_coverage_end IS NULL OR compensation_coverage_end >= '1000-01-01') AND (compensation_effective_date IS NULL OR compensation_coverage_end IS NULL OR compensation_coverage_end >= compensation_effective_date)",
    }),
    EVENT: ([
        ('certification_event_id','BIGINT UNSIGNED NOT NULL AUTO_INCREMENT'),
        ('certification_id','BIGINT UNSIGNED NOT NULL'),
        ('event_type',"ENUM('CERTIFY','REVOKE','INVALIDATE','SUPERSEDE') NOT NULL"),
        ('replacement_certification_id','BIGINT UNSIGNED NULL'),
        ('actor_id','INT NOT NULL'), ('occurred_at','DATETIME(6) NOT NULL'),
        ('reason','VARCHAR(255) NOT NULL'), ('supporting_reference','VARCHAR(255) NOT NULL'),
    ], {
        'PRIMARY':(True,('certification_event_id',)), 'uq_pce_action':(True,('certification_id','event_type')),
        'idx_pce_replacement':(False,('replacement_certification_id',)), 'idx_pce_actor':(False,('actor_id',)),
    }, {
        'fk_pce_certification':fk(['certification_id'],CERT,['certification_id']),
        'fk_pce_replacement':fk(['replacement_certification_id'],CERT,['certification_id']),
        'fk_pce_actor':fk(['actor_id'],'users',['user_id']),
    }, {
        'chk_pce_refs':ref_check('reason')+' AND '+ref_check('supporting_reference'),
        'chk_pce_replacement':"(event_type='SUPERSEDE' AND replacement_certification_id IS NOT NULL AND replacement_certification_id <> certification_id) OR (event_type <> 'SUPERSEDE' AND replacement_certification_id IS NULL)",
    }),
    EVIDENCE: ([
        ('calculation_evidence_id','BIGINT UNSIGNED NOT NULL AUTO_INCREMENT'),
        ('evidence_version','SMALLINT UNSIGNED NOT NULL'), ('payroll_period_id','INT NOT NULL'),
        ('payroll_entry_id','INT NOT NULL'), ('employee_id','INT NOT NULL'),
        ('certification_id','BIGINT UNSIGNED NOT NULL'), ('calculation_sequence','INT UNSIGNED NOT NULL'),
        ('canonical_evidence','JSON NOT NULL'), ('rounding_contract','VARCHAR(40) NOT NULL'),
        ('evidence_digest',DIGEST+' NOT NULL'), ('calculated_by','INT NOT NULL'), ('calculated_at','DATETIME(6) NOT NULL'),
    ], {
        'PRIMARY':(True,('calculation_evidence_id',)),
        'uq_pce_sequence':(True,('payroll_entry_id','calculation_sequence')),
        'uq_pce_owner':(True,('calculation_evidence_id','payroll_entry_id')),
        'idx_pcev_entry':(False,('payroll_entry_id','payroll_period_id','employee_id')),
        'idx_pcev_cert_period':(False,('certification_id','payroll_period_id')),
        'idx_pcev_member':(False,('certification_id','employee_id')),
        'idx_pcev_actor':(False,('calculated_by',)),
    }, {
        'fk_pcev_entry':fk(['payroll_entry_id','payroll_period_id','employee_id'],'payroll_entries',['payroll_entry_id','payroll_period_id','employee_id']),
        'fk_pcev_period':fk(['certification_id','payroll_period_id'],CERT,['certification_id','payroll_period_id']),
        'fk_pcev_member':fk(['certification_id','employee_id'],MEMBER,['certification_id','employee_id']),
        'fk_pcev_actor':fk(['calculated_by'],'users',['user_id']),
    }, {
        'chk_pcev_version':'evidence_version = 2 AND calculation_sequence > 0',
        'chk_pcev_digest':digest_check('evidence_digest'),
        'chk_pcev_payload':json_check('canonical_evidence',PAYLOAD_SCHEMA),
        'chk_pcev_rounding':ref_check('rounding_contract'),
    }),
}

ADDITIONS = {
    'employee_compensation': ([], {'uq_compensation_employee_006':(True,('compensation_id','employee_id'))}, {}, {}),
    'payroll_entries': ([('current_calculation_evidence_id','BIGINT UNSIGNED NULL')],
        {'uq_entry_identity_006':(True,('payroll_entry_id','payroll_period_id','employee_id')),
         'idx_entry_evidence_006':(False,('current_calculation_evidence_id','payroll_entry_id'))},
        {'fk_entry_evidence_006':fk(['current_calculation_evidence_id','payroll_entry_id'],EVIDENCE,['calculation_evidence_id','payroll_entry_id'])},
        {'chk_entry_evidence_006':"(current_calculation_evidence_id IS NULL AND (calculation_input_version IS NULL OR calculation_input_version <> 2)) OR (current_calculation_evidence_id IS NOT NULL AND calculation_input_version IS NOT NULL AND calculation_input_version = 2 AND calculation_input_hash IS NOT NULL)"}),
}

# Nullable assembly fields remain representable; all actual references are positive.
for _table, (_columns, _indexes, _fks, _checks) in TABLES.items():
    _ids = [name for name, definition in _columns if name.endswith('_id') and 'AUTO_INCREMENT' not in definition]
    _checks['chk_' + {CERT:'pcc', MEMBER:'pcm', EVENT:'pce', EVIDENCE:'pcev'}[_table] + '_ids'] = ' AND '.join(
        f'({name} IS NULL OR {name} > 0)' for name in _ids)
TABLES[CERT][3]['chk_pcc_times'] = "created_at >= '1000-01-01' AND (certified_at IS NULL OR certified_at >= created_at)"
TABLES[EVENT][3]['chk_pce_time'] = "occurred_at >= '1000-01-01'"
TABLES[EVIDENCE][3]['chk_pcev_time'] = "calculated_at >= '1000-01-01'"
TABLES[EVIDENCE][3]['chk_pcev_size'] = 'JSON_STORAGE_SIZE(canonical_evidence) <= 1048576'

TRIGGERS = {}


def trigger(name, table, event, body, timing='BEFORE'):
    TRIGGERS[name] = (table, event, timing, 'BEGIN\n'+body+'\nEND')


trigger('pcc_insert_006',CERT,'INSERT', """
    DECLARE p_policy INT DEFAULT NULL; DECLARE p_code CHAR(1); DECLARE p_start DATE; DECLARE p_end DATE;
    DECLARE last_revision INT UNSIGNED DEFAULT NULL; DECLARE last_id BIGINT UNSIGNED; DECLARE last_state VARCHAR(20);
    SELECT policy_version_id,cutoff_code,start_date,end_date INTO p_policy,p_code,p_start,p_end
        FROM payroll_periods WHERE payroll_period_id=NEW.payroll_period_id FOR UPDATE;
    IF p_policy IS NULL OR NOT(p_policy <=> NEW.policy_version_id) OR NOT(p_code <=> NEW.cutoff_code)
        OR NOT(p_start <=> NEW.start_date) OR NOT(p_end <=> NEW.end_date) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification must match a pinned period'; END IF;
    IF NEW.state <> 'ASSEMBLY' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Assemble before sealing'; END IF;
    SELECT MAX(revision) INTO last_revision FROM payroll_cutoff_certifications WHERE payroll_period_id=NEW.payroll_period_id;
    IF last_revision IS NULL THEN
        IF NEW.revision <> 1 OR NEW.predecessor_certification_id IS NOT NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Initial certification revision must be one'; END IF;
    ELSE
        SELECT certification_id,state INTO last_id,last_state FROM payroll_cutoff_certifications
            WHERE payroll_period_id=NEW.payroll_period_id AND revision=last_revision;
        IF NEW.revision <> last_revision+1 OR NOT(NEW.predecessor_certification_id <=> last_id) OR last_state <> 'SEALED' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification must extend the latest sealed revision'; END IF;
    END IF;
""")

trigger('pcc_update_006',CERT,'UPDATE', """
    DECLARE members_count INT; DECLARE invalid_count INT;
    IF OLD.state='SEALED' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Sealed certification is immutable'; END IF;
    IF NOT(NEW.certification_id <=> OLD.certification_id) OR NOT(NEW.payroll_period_id <=> OLD.payroll_period_id)
        OR NOT(NEW.policy_version_id <=> OLD.policy_version_id) OR NOT(NEW.revision <=> OLD.revision)
        OR NOT(NEW.predecessor_certification_id <=> OLD.predecessor_certification_id)
        OR NOT(NEW.cutoff_code <=> OLD.cutoff_code) OR NOT(NEW.start_date <=> OLD.start_date)
        OR NOT(NEW.end_date <=> OLD.end_date) OR NOT(NEW.created_by <=> OLD.created_by) OR NOT(NEW.created_at <=> OLD.created_at) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification identity is immutable'; END IF;
    IF NEW.state='SEALED' THEN
        SELECT COUNT(*), COALESCE(SUM(
            NOT JSON_CONTAINS(NEW.roster_scope,CAST(employee_id AS JSON),'$.employee_ids')
            OR verification_status <> 'VERIFIED'
            OR (disposition='INCLUDE' AND (
                eligibility <> 'FULL_CUTOFF' OR hire_date_snapshot IS NULL OR hire_date_snapshot > NEW.start_date
                OR employment_coverage_start IS NULL OR employment_coverage_start > NEW.start_date
                OR employment_coverage_end IS NULL OR employment_coverage_end < NEW.end_date
                OR employment_reference IS NULL OR CHAR_LENGTH(TRIM(employment_reference))=0
                OR compensation_id IS NULL OR basic_rate IS NULL OR NOT(pay_type <=> 'MONTHLY') OR NOT(BINARY currency_code <=> BINARY 'PHP')
                OR compensation_effective_date IS NULL OR compensation_effective_date > NEW.start_date
                OR compensation_coverage_end IS NULL OR compensation_coverage_end < NEW.end_date
                OR compensation_reference IS NULL OR CHAR_LENGTH(TRIM(compensation_reference))=0
                OR JSON_LENGTH(schedule_evidence,'$.exceptions') <> 0
                OR NOT(JSON_EXTRACT(schedule_evidence,'$.scheduled_dates') <=> JSON_EXTRACT(NEW.calendar_configuration,'$.scheduled_dates'))
            ))),0) INTO members_count,invalid_count FROM payroll_certification_members
            WHERE certification_id=OLD.certification_id FOR UPDATE;
        IF members_count <> JSON_LENGTH(NEW.roster_scope,'$.employee_ids') OR invalid_count <> 0
            OR JSON_LENGTH(NEW.calendar_configuration,'$.exceptions') <> 0 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Incomplete or unsupported certification cannot be sealed'; END IF;
    END IF;
""")

trigger('pcc_delete_006',CERT,'DELETE', """IF OLD.state='SEALED' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Sealed certification cannot be deleted'; END IF;""")

for event in ('INSERT','UPDATE','DELETE'):
    row = 'OLD' if event=='DELETE' else 'NEW'
    identity = """IF NOT(NEW.certification_id <=> OLD.certification_id) OR NOT(NEW.employee_id <=> OLD.employee_id) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Membership identity is immutable'; END IF;""" if event=='UPDATE' else ''
    trigger('pcm_'+event.lower()+'_006',MEMBER,event, f"""
        DECLARE parent_state VARCHAR(20) DEFAULT NULL;
        SELECT state INTO parent_state FROM payroll_cutoff_certifications WHERE certification_id={row}.certification_id FOR UPDATE;
        IF parent_state IS NULL OR parent_state <> 'ASSEMBLY' THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Members require an assembly certification'; END IF;
        {identity}
    """)

trigger('pce_insert_006',EVENT,'INSERT', """
    DECLARE parent_state VARCHAR(20) DEFAULT NULL; DECLARE replacement BIGINT UNSIGNED DEFAULT NULL;
    DECLARE certifier INT; DECLARE certified DATETIME(6);
    SELECT state,certified_by,certified_at INTO parent_state,certifier,certified FROM payroll_cutoff_certifications
        WHERE certification_id=NEW.certification_id;
    IF parent_state IS NULL OR parent_state <> 'SEALED' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Events require a sealed certification'; END IF;
    IF NEW.event_type='CERTIFY' AND (NOT(NEW.actor_id <=> certifier) OR NOT(NEW.occurred_at <=> certified)) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification event must match the seal'; END IF;
    IF NEW.event_type='SUPERSEDE' THEN
        SELECT certification_id INTO replacement FROM payroll_cutoff_certifications
            WHERE certification_id=NEW.replacement_certification_id AND predecessor_certification_id=NEW.certification_id AND state='SEALED';
        IF replacement IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Supersession must reference the sealed successor'; END IF;
    END IF;
""")

# The seal and required history are a single SQL statement/transaction. No helper audit is involved.
trigger('pcc_seal_events_006',CERT,'UPDATE', """
    IF OLD.state='ASSEMBLY' AND NEW.state='SEALED' THEN
        INSERT INTO payroll_certification_events(certification_id,event_type,actor_id,occurred_at,reason,supporting_reference)
            VALUES(NEW.certification_id,'CERTIFY',NEW.certified_by,NEW.certified_at,'Certification sealed',NEW.roster_source_reference);
        IF NEW.predecessor_certification_id IS NOT NULL THEN
            INSERT INTO payroll_certification_events(certification_id,event_type,replacement_certification_id,actor_id,occurred_at,reason,supporting_reference)
                VALUES(NEW.predecessor_certification_id,'SUPERSEDE',NEW.certification_id,NEW.certified_by,NEW.certified_at,'Certification replaced by a complete revision',NEW.roster_source_reference);
        END IF;
    END IF;
""",'AFTER')

for table,prefix in ((EVENT,'pce'),(EVIDENCE,'pcev')):
    for event in ('UPDATE','DELETE'):
        trigger(prefix+'_'+event.lower()+'_006',table,event,
                "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification history is append only';")

trigger('pcev_insert_006',EVIDENCE,'INSERT', """
    DECLARE parent_state VARCHAR(20) DEFAULT NULL; DECLARE included VARCHAR(10) DEFAULT NULL;
    SELECT c.state,m.disposition INTO parent_state,included FROM payroll_cutoff_certifications c
        JOIN payroll_certification_members m USING(certification_id)
        WHERE c.certification_id=NEW.certification_id AND m.employee_id=NEW.employee_id FOR SHARE;
    IF parent_state IS NULL OR parent_state <> 'SEALED' OR included <> 'INCLUDE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Calculation evidence requires sealed included membership'; END IF;
    IF EXISTS(SELECT 1 FROM payroll_certification_events WHERE certification_id=NEW.certification_id
            AND event_type IN ('REVOKE','INVALIDATE','SUPERSEDE')) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certification is revoked, invalidated or superseded'; END IF;
""")

trigger('period_identity_006','payroll_periods','UPDATE', """
    IF NOT(NEW.payroll_period_id <=> OLD.payroll_period_id) OR NOT(NEW.policy_version_id <=> OLD.policy_version_id)
        OR NOT(NEW.cutoff_code <=> OLD.cutoff_code) OR NOT(NEW.start_date <=> OLD.start_date) OR NOT(NEW.end_date <=> OLD.end_date) THEN
        IF EXISTS(SELECT 1 FROM payroll_cutoff_certifications WHERE payroll_period_id=OLD.payroll_period_id) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Certified period identity cannot be rebound'; END IF;
    END IF;
""")

for event in ('INSERT','UPDATE'):
    trigger('entry_evidence_'+event.lower()+'_006','payroll_entries',event, """
        DECLARE stored_hash CHAR(64) DEFAULT NULL;
        IF NEW.current_calculation_evidence_id IS NOT NULL THEN
            SELECT evidence_digest INTO stored_hash FROM payroll_calculation_evidence
                WHERE calculation_evidence_id=NEW.current_calculation_evidence_id AND payroll_entry_id=NEW.payroll_entry_id
                    AND payroll_period_id=NEW.payroll_period_id AND employee_id=NEW.employee_id FOR SHARE;
            IF stored_hash IS NULL OR NOT(BINARY stored_hash <=> BINARY NEW.calculation_input_hash) OR NOT(NEW.calculation_input_version <=> 2) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Current calculation evidence identity or hash mismatch'; END IF;
        END IF;
    """)


def _normal_check(value):
    return _normal_check_from_tree(base._normal_check(value))


def _normal_check_from_tree(tree):
    # MySQL flattens associative AND/OR groups when it stores these CHECKs.
    def flatten(node):
        if len(node)==2 and node[0] in ('and','or'):
            operator=node[0];parts=[]
            for part in node[1]:
                part=flatten(part)
                if len(part)==2 and part[0]==operator:parts.extend(part[1])
                else:parts.append(part)
            return operator,tuple(parts)
        return node
    return flatten(tree)


def _verify(cursor, table, manifest, complete=False, exclusive=False):
    if not base._table_exists(cursor,table):
        if complete: raise RuntimeError(f'Missing table {table}.')
        return
    columns,indexes,fks,checks = manifest
    actual = base._columns(cursor,table)
    for name,definition in columns:
        if name in actual: base._verify_column(table,name,definition,actual[name],explicit_charset=True)
        elif complete or exclusive: raise RuntimeError(f'Missing column {table}.{name}.')
    if exclusive:
        if set(actual)!={n for n,_ in columns}: raise RuntimeError(f'Unexpected columns in {table}.')
        cursor.execute('SELECT TABLE_COLLATION FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s',(table,))
        if cursor.fetchone()['TABLE_COLLATION']!='utf8mb4_0900_ai_ci': raise RuntimeError(f'Incompatible collation {table}.')
    for actual_objects,expected,label in (
        (base._indexes(cursor,table),indexes,'index'), (base._foreign_keys(cursor,table),fks,'foreign key'),
        ({n:_normal_check_from_tree(v) for n,v in base._checks(cursor,table).items()},
         {n:_normal_check(v) for n,v in checks.items()},'check')):
        base._verify_objects(actual_objects,expected,table+' '+label,complete=complete,exclusive=exclusive)
        if not exclusive:
            owned={n for n,_ in columns}
            for name,value in actual_objects.items():
                if name.endswith('_006') and name not in expected:
                    raise RuntimeError(f'Unexpected owned object {table}.{name}.')
                fields = value[1] if label=='index' else value[0] if label=='foreign key' else str(value)
                if name not in expected and any(n in fields for n in owned):
                    raise RuntimeError(f'Unexpected {label} on evidence columns: {name}.')


def _triggers(cursor, complete=False):
    found=set()
    for row in base._rows(cursor,'''SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,
        ACTION_ORIENTATION,ACTION_STATEMENT,SQL_MODE FROM information_schema.triggers WHERE TRIGGER_SCHEMA=DATABASE()'''):
        name=row['TRIGGER_NAME']
        if name not in TRIGGERS:
            if row['EVENT_OBJECT_TABLE'] in (*TABLES,'payroll_periods','payroll_entries') or name.endswith('_006'):
                raise RuntimeError(f'Unexpected certification trigger {name}.')
            continue
        found.add(name)
        table,event,timing,body=TRIGGERS[name]
        modes=row['SQL_MODE'];modes=set(modes.split(',')) if isinstance(modes,str) else set(modes)
        if ((row['EVENT_OBJECT_TABLE'],row['EVENT_MANIPULATION'],row['ACTION_TIMING'],row['ACTION_ORIENTATION']) != (table,event,timing,'ROW')
            or base._normal_sql(row['ACTION_STATEMENT'])!=base._normal_sql(body) or modes!=set(MODE.split(','))):
            raise RuntimeError(f'Incompatible trigger {name}.')
    if complete and found!=set(TRIGGERS):raise RuntimeError('Missing certification protection triggers.')
    return found


def _prerequisites(cursor):
    cursor.execute('SELECT @@SESSION.foreign_key_checks AS fk_checks,@@SESSION.unique_checks AS unique_checks')
    switches=cursor.fetchone()
    if switches['fk_checks']!=1 or switches['unique_checks']!=1:
        raise RuntimeError('Migration requires enabled foreign_key_checks and unique_checks.')
    base._prerequisites(cursor)
    for table in base.TABLES:base._verify_table(cursor,table,complete=True)
    base._verify_triggers(cursor,complete=True)
    required={
        'employees':[('employee_id','INT NOT NULL AUTO_INCREMENT')],
        'employee_compensation':[('compensation_id','INT NOT NULL AUTO_INCREMENT'),('employee_id','INT NOT NULL')],
        'payroll_entries':[('payroll_period_id','INT NOT NULL'),('employee_id','INT NOT NULL'),('compensation_id','INT NOT NULL')],
    }
    for table,columns in required.items():
        actual=base._columns(cursor,table)
        for name,definition in columns:
            if name not in actual:raise RuntimeError(f'Missing prerequisite {table}.{name}.')
            base._verify_column(table,name,definition,actual[name])
    for table,key in (('employees','employee_id'),('employee_compensation','compensation_id'),('payroll_entries','payroll_entry_id')):
        base._verify_objects(base._indexes(cursor,table),{'PRIMARY':(True,(key,))},table+' primary key',complete=True)
    pointer_exists='current_calculation_evidence_id' in base._columns(cursor,'payroll_entries')
    condition='calculation_input_version=2'
    if pointer_exists:
        condition="(calculation_input_version=2 AND current_calculation_evidence_id IS NULL) OR (current_calculation_evidence_id IS NOT NULL AND (calculation_input_version IS NULL OR calculation_input_version<>2 OR calculation_input_hash IS NULL))"
    cursor.execute('SELECT COUNT(*) AS invalid_rows FROM payroll_entries WHERE '+condition)
    if cursor.fetchone()['invalid_rows']:
        raise RuntimeError('Existing calculation evidence is incompatible. Manual review required; historical evidence is never backfilled.')


def _execute_ddl(cursor, statement):
    cursor.execute(statement)


def _add(cursor,table,manifest, skip_fks=False):
    columns,indexes,fks,checks=manifest
    for name,definition in columns:
        if name not in base._columns(cursor,table):_execute_ddl(cursor,f'ALTER TABLE `{table}` ADD COLUMN `{name}` {definition}')
    for name,definition in indexes.items():
        if name not in base._indexes(cursor,table):_execute_ddl(cursor,f'ALTER TABLE `{table}` ADD '+base._index_ddl(name,definition))
    if not skip_fks:
        for name,definition in fks.items():
            if name not in base._foreign_keys(cursor,table):_execute_ddl(cursor,f'ALTER TABLE `{table}` ADD '+base._fk_ddl(name,definition))
        for name,body in checks.items():
            if name not in base._checks(cursor,table):_execute_ddl(cursor,f'ALTER TABLE `{table}` ADD CONSTRAINT `{name}` CHECK ({body})')


def upgrade(connection):
    if connection.in_transaction:raise RuntimeError('Use a fresh migration connection with no pending business transaction.')
    cursor=connection.cursor(dictionary=True)
    lock_name=None;saved_mode=None
    try:
        _prerequisites(cursor)
        name='erp_cert_006_'+hashlib.sha256(cursor._policy_database.encode()).hexdigest()[:32]
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired',(name,))
        if cursor.fetchone()['acquired']!=1:raise RuntimeError('Another migration 006 is running.')
        lock_name=name
        for table,manifest in TABLES.items():_verify(cursor,table,manifest,exclusive=True)
        for table,manifest in ADDITIONS.items():_verify(cursor,table,manifest)
        existing=_triggers(cursor)
        cursor.execute('SELECT @@SESSION.sql_mode AS mode');saved_mode=cursor.fetchone()['mode']
        cursor.execute('SET SESSION sql_mode=%s',(MODE,))
        # Install parent indexes/nullable pointer first; close the FK cycle only after evidence exists.
        for table,manifest in ADDITIONS.items():_add(cursor,table,manifest,skip_fks=True)
        for table,(columns,indexes,fks,checks) in TABLES.items():
            if not base._table_exists(cursor,table):
                parts=['`'+n+'` '+d for n,d in columns]
                parts += [base._index_ddl(n,d) for n,d in indexes.items()]
                parts += [base._fk_ddl(n,d) for n,d in fks.items()]
                parts += [f'CONSTRAINT `{n}` CHECK ({body})' for n,body in checks.items()]
                _execute_ddl(cursor,f'CREATE TABLE `{table}` ('+',\n'.join(parts)+') '+OPTIONS)
            else:_add(cursor,table,TABLES[table])
        for table,manifest in ADDITIONS.items():_add(cursor,table,manifest)
        for name,(table,event,timing,body) in TRIGGERS.items():
            if name not in existing:_execute_ddl(cursor,f'CREATE TRIGGER `{name}` {timing} {event} ON `{table}` FOR EACH ROW {body}')
        for table,manifest in TABLES.items():_verify(cursor,table,manifest,True,True)
        for table,manifest in ADDITIONS.items():_verify(cursor,table,manifest,True)
        _triggers(cursor,True)
        connection.commit()
    finally:
        connection.rollback()
        if saved_mode is not None:cursor.execute('SET SESSION sql_mode=%s',(saved_mode,))
        if lock_name is not None:
            cursor.execute('SELECT RELEASE_LOCK(%s)',(lock_name,));cursor.fetchall()
        cursor.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('host','user','database'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',type=int,required=True)
    args=parser.parse_args()
    with mysql.connector.connect(host=args.host,port=args.port,user=args.user,password=getpass('MySQL password: '),database=args.database) as connection:
        upgrade(connection)
    print('Certification schema applied/verified. No evidence, grants or payroll cutover were populated.')


if __name__=='__main__':main()
