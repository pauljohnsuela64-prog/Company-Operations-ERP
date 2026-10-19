"""Explicit, additive HR history foundation. No application workflow or backfill."""
import argparse
from getpass import getpass
import importlib.util
from pathlib import Path
import re

import mysql.connector


EVENT_TYPES = ('HIRE', 'STATUS_CHANGE', 'RESIGN', 'TERMINATE', 'REHIRE',
               'TRANSFER', 'POSITION_CHANGE', 'CORRECT', 'VOID', 'LEGACY_OBSERVATION')
TABLES = {}


def column(name, kind, nullable=False, default=None, extra=''):
    return (name, kind, nullable, default, extra)


def text_checks(name, limit, optional=False):
    expression = f'(char_length({name}) between 1 and {limit}) and (char_length(trim({name})) > 0)'
    return f'({name} is null) or ({expression})' if optional else expression


def table(name, columns, indexes, checks, fks):
    TABLES[name] = dict(columns=columns, indexes=indexes, checks=checks, fks=fks)


P = 'employee_employment_periods'
R = 'employee_lifecycle_requests'
E = 'employee_employment_events'
common = [column('employee_id', 'int'), column('employment_period_id', 'bigint', True)]
proposal = [column('event_type', 'text'), column('effective_date', 'date'),
            column('effective_order', 'int'), column('payload_version', 'smallint', default='1')]
source = [column('source_type', 'text'), column('source_reference', 'text'),
          column('source_version', 'text', True), column('reason', 'text')]


def base_checks(prefix, payload):
    return {
        prefix+'_type': 'cast(event_type as char charset binary) in ('+','.join("'"+v+"'" for v in EVENT_TYPES)+')',
        prefix+'_date': "effective_date >= '1000-01-01'",
        prefix+'_date_parts': '(month(effective_date) >= 1) and (dayofmonth(effective_date) >= 1)',
        prefix+'_order': 'effective_order >= 1',
        prefix+'_version': 'payload_version = 1',
        prefix+'_object': f"json_type({payload}) = 'OBJECT'",
        prefix+'_size': f'length(cast({payload} as char charset utf8mb4)) <= 16384',
        **{prefix+'_'+n: text_checks(n, limit, optional) for n, limit, optional in
           [('source_type',30,False), ('source_reference',255,False),
            ('source_version',50,True), ('reason',255,False)]},
    }


# Index entries: name -> (unique, column names). All are full BTREE indexes.
# FK entries: name -> (local columns, referenced table, referenced columns).
table(P, [column('employment_period_id','bigint',extra='auto_increment'),
          column('employee_id','int'), column('period_sequence','int'),
          column('verified_start_date','date'), column('end_exclusive_date','date',True),
          column('is_void','tinyint(1)',default='0'), column('publication_revision','bigint'),
          column('created_at_utc','datetime(6)',default='utc_timestamp(6)')],
      {'PRIMARY': (True,['employment_period_id']), 'uq_period_employee_id':(True,['employee_id','employment_period_id']),
       'uq_period_sequence':(True,['employee_id','period_sequence'])},
      {'ck_period_sequence':'period_sequence >= 1', 'ck_period_revision':'publication_revision >= 1',
       'ck_period_void':'is_void in (0,1)', 'ck_period_start':"verified_start_date >= '1000-01-01'",
       'ck_period_start_parts':'(month(verified_start_date) >= 1) and (dayofmonth(verified_start_date) >= 1)',
       'ck_period_end_parts':'(end_exclusive_date is null) or ((month(end_exclusive_date) >= 1) and (dayofmonth(end_exclusive_date) >= 1))',
       'ck_period_end':'(end_exclusive_date is null) or (end_exclusive_date > verified_start_date)'},
      {'fk_period_employee':(['employee_id'],'employees',['employee_id'])})
table(R, [column('request_id','bigint',extra='auto_increment'), *common, *proposal,
          column('expected_employee_revision','bigint'), column('proposal_data','json'), *source,
          column('submitted_by','int'), column('submitted_at_utc','datetime(6)',default='utc_timestamp(6)'),
          column('decision_state','text'), column('decided_by','int',True),
          column('decided_at_utc','datetime(6)',True), column('decision_reason','text',True)],
      {'PRIMARY':(True,['request_id']), 'uq_request_employee_id':(True,['employee_id','request_id']),
       'ix_request_period':(False,['employee_id','employment_period_id']),
       'ix_request_submitter':(False,['submitted_by']), 'ix_request_decider':(False,['decided_by'])},
      {**base_checks('ck_request','proposal_data'), 'ck_request_revision':'expected_employee_revision >= 1',
       'ck_request_decision':"cast(decision_state as char charset binary) in ('PENDING','APPROVED','REJECTED','CANCELLED')",
       'ck_request_decision_reason':text_checks('decision_reason',255,True)},
      {'fk_request_employee':(['employee_id'],'employees',['employee_id']),
       'fk_request_period':(['employee_id','employment_period_id'],P,['employee_id','employment_period_id']),
       'fk_request_submitter':(['submitted_by'],'users',['user_id']),
       'fk_request_decider':(['decided_by'],'users',['user_id'])})
table(E, [column('employment_event_id','bigint',extra='auto_increment'), *common,
          column('request_id','bigint'), *proposal, column('publication_revision','bigint'),
          column('changes','json'), *source, column('recorded_by','int'), column('approved_by','int',True),
          column('recorded_at_utc','datetime(6)',default='utc_timestamp(6)'),
          column('supersedes_event_id','bigint',True)],
      {'PRIMARY':(True,['employment_event_id']), 'uq_event_employee_id':(True,['employee_id','employment_event_id']),
       'uq_event_revision':(True,['employee_id','publication_revision']), 'uq_event_request':(True,['request_id']),
       'uq_event_successor':(True,['supersedes_event_id']),
       'ix_event_period':(False,['employee_id','employment_period_id']),
       'ix_event_request_employee':(False,['employee_id','request_id']),
       'ix_event_correction':(False,['employee_id','supersedes_event_id']),
       'ix_event_recorder':(False,['recorded_by']), 'ix_event_approver':(False,['approved_by'])},
      {**base_checks('ck_event','changes'), 'ck_event_revision':'publication_revision >= 1',
       'ck_event_correction':"(cast(event_type as char charset binary) in ('CORRECT','VOID')) = (supersedes_event_id is not null)"},
      {'fk_event_employee':(['employee_id'],'employees',['employee_id']),
       'fk_event_period':(['employee_id','employment_period_id'],P,['employee_id','employment_period_id']),
       'fk_event_request':(['employee_id','request_id'],R,['employee_id','request_id']),
       'fk_event_correction':(['employee_id','supersedes_event_id'],E,['employee_id','employment_event_id']),
       'fk_event_recorder':(['recorded_by'],'users',['user_id']),
       'fk_event_approver':(['approved_by'],'users',['user_id'])})


def create_table(name):
    spec = TABLES[name]
    parts = []
    for n, kind, nullable, default, extra in spec['columns']:
        d = '' if default is None else ' DEFAULT '+ ('('+default+')' if 'timestamp' in default else default)
        parts.append(f'`{n}` {kind} '+('NULL' if nullable else 'NOT NULL')+d+' '+extra)
    for n,(unique,cols) in spec['indexes'].items():
        parts.append(('PRIMARY KEY' if n=='PRIMARY' else ('UNIQUE KEY' if unique else 'KEY')+' `'+n+'`')+' ('+','.join('`'+c+'`' for c in cols)+')')
    for n,expression in spec['checks'].items():
        parts.append(f'CONSTRAINT `{n}` CHECK ({expression})')
    for n,(cols,target,refs) in spec['fks'].items():
        parts.append(f'CONSTRAINT `{n}` FOREIGN KEY ('+','.join(cols)+f') REFERENCES `{target}` ('+','.join(refs)+') ON DELETE RESTRICT ON UPDATE RESTRICT')
    return f'CREATE TABLE `{name}` ('+',\n'.join(parts)+') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'


immutable = [c[0] for c in TABLES[R]['columns'] if c[0] not in
             ('decision_state','decided_by','decided_at_utc','decision_reason')]
TRIGGERS = {
    'hr_request_insert':(R,'INSERT',"""BEGIN
IF BINARY NEW.decision_state <> BINARY 'PENDING' OR NEW.decided_by IS NOT NULL OR NEW.decided_at_utc IS NOT NULL OR NEW.decision_reason IS NOT NULL THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Requests must start pending'; END IF;
SET NEW.submitted_at_utc=UTC_TIMESTAMP(6);
END"""),
    'hr_request_decide':(R,'UPDATE',"BEGIN\nIF "+' OR '.join(f'NOT (CAST(NEW.`{n}` AS BINARY) <=> CAST(OLD.`{n}` AS BINARY))' for n in immutable)+""" THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Request proposals are immutable'; END IF;
IF BINARY OLD.decision_state <> BINARY 'PENDING' OR BINARY NEW.decision_state NOT IN (BINARY 'APPROVED',BINARY 'REJECTED',BINARY 'CANCELLED') OR NEW.decided_by IS NULL OR NEW.decision_reason IS NULL OR CHAR_LENGTH(TRIM(NEW.decision_reason))=0 THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='A pending request permits one terminal decision'; END IF;
SET NEW.decided_at_utc=UTC_TIMESTAMP(6);
END"""),
    'hr_request_no_delete':(R,'DELETE',"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Requests cannot be deleted'"),
    'hr_event_insert':(E,'INSERT',"""BEGIN
IF NEW.supersedes_event_id IS NOT NULL AND NOT EXISTS (
 SELECT 1 FROM employee_employment_events WHERE employment_event_id=NEW.supersedes_event_id AND employee_id=NEW.employee_id AND publication_revision < NEW.publication_revision) THEN
 SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Correction requires an earlier same-employee event'; END IF;
SET NEW.recorded_at_utc=UTC_TIMESTAMP(6);
END"""),
    'hr_event_no_update':(E,'UPDATE',"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Published events are immutable'"),
    'hr_event_no_delete':(E,'DELETE',"SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Published events cannot be deleted'"),
}


def canonical(sql):
    """Preserve quoted values and grouping; normalize server formatting only."""
    sql = sql.replace("\\'", "'")
    sql = re.sub(r'_(?:utf8mb4|utf8mb3|utf8|binary)(?=\s*\')','',sql,flags=re.I)
    tokens = re.findall(r"'(?:''|[^'])*'|`[^`]+`|[a-zA-Z_][\w]*|\d+|<=>|>=|<=|<>|!=|[^\s]", sql)
    result = ''.join(t if t.startswith("'") else t.strip('`').lower() for t in tokens)
    # MySQL adds parentheses around whole expressions, not semantic operators.
    while result.startswith('(') and result.endswith(')'):
        depth=0
        # Parentheses inside string literals are irrelevant for our fixed expressions.
        for i,c in enumerate(result):
            depth += (c=='(')-(c==')')
            if depth==0: break
        if i != len(result)-1: break
        result=result[1:-1]
    return result.replace('characterset','charset')


def rows(cur, query, params=()):
    cur.execute(query,params)
    return cur.fetchall()


def column_type(value):
    return re.sub(r'\b(int|bigint|smallint)\(\d+\)',r'\1',value.lower())


def inspect_table(cur,name):
    database=rows(cur,'SELECT DATABASE() AS db')[0]['db']
    found=rows(cur,'SELECT ENGINE,TABLE_COLLATION FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s',(name,))
    if not found:return False
    if found != [{'ENGINE':'InnoDB','TABLE_COLLATION':'utf8mb4_bin'}]:raise RuntimeError('Incompatible engine/collation: '+name)
    cols=rows(cur,'SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA,CHARACTER_SET_NAME,COLLATION_NAME FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name=%s ORDER BY ORDINAL_POSITION',(name,))
    if any(c['COLUMN_TYPE']=='text' and (c['CHARACTER_SET_NAME'],c['COLLATION_NAME'])!=('utf8mb4','utf8mb4_bin') for c in cols):
        raise RuntimeError('Incompatible text column collation: '+name)
    actual=[(c['COLUMN_NAME'],column_type(c['COLUMN_TYPE']),c['IS_NULLABLE']=='YES',
             canonical(c['COLUMN_DEFAULT']) if c['COLUMN_DEFAULT'] is not None else None,
             c['EXTRA'].replace('DEFAULT_GENERATED','').strip()) for c in cols]
    expected=[(n,k,null,canonical(d) if d is not None else None,x) for n,k,null,d,x in TABLES[name]['columns']]
    if actual!=expected:raise RuntimeError('Incompatible columns: '+name)
    indexes=rows(cur,'SELECT INDEX_NAME,NON_UNIQUE,COLUMN_NAME,SUB_PART,INDEX_TYPE,IS_VISIBLE FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name=%s ORDER BY INDEX_NAME,SEQ_IN_INDEX',(name,))
    ix={}
    for r in indexes:
        if r['SUB_PART'] or r['INDEX_TYPE']!='BTREE' or r['IS_VISIBLE']!='YES':raise RuntimeError('Incompatible index: '+name)
        ix.setdefault(r['INDEX_NAME'],(not r['NON_UNIQUE'],[]))[1].append(r['COLUMN_NAME'])
    if ix!=TABLES[name]['indexes']:raise RuntimeError('Incompatible indexes: '+name)
    checks=rows(cur,'SELECT t.CONSTRAINT_NAME,t.ENFORCED,c.CHECK_CLAUSE FROM information_schema.table_constraints t JOIN information_schema.check_constraints c USING(CONSTRAINT_SCHEMA,CONSTRAINT_NAME) WHERE t.TABLE_SCHEMA=DATABASE() AND t.TABLE_NAME=%s',(name,))
    if any(c['ENFORCED']!='YES' for c in checks) or {c['CONSTRAINT_NAME']:canonical(c['CHECK_CLAUSE']) for c in checks}!={n:canonical(e) for n,e in TABLES[name]['checks'].items()}:
        raise RuntimeError('Incompatible CHECK constraints: '+name)
    fks=rows(cur,'SELECT k.CONSTRAINT_NAME,k.COLUMN_NAME,k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r USING(CONSTRAINT_SCHEMA,CONSTRAINT_NAME) WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s ORDER BY k.CONSTRAINT_NAME,k.ORDINAL_POSITION',(name,))
    actual={}
    for f in fks:
        if f['REFERENCED_TABLE_SCHEMA']!=database or f['DELETE_RULE']!='RESTRICT' or f['UPDATE_RULE']!='RESTRICT':raise RuntimeError('Incompatible FK rules: '+name)
        entry=actual.setdefault(f['CONSTRAINT_NAME'],([],f['REFERENCED_TABLE_NAME'],[]))
        entry[0].append(f['COLUMN_NAME']);entry[2].append(f['REFERENCED_COLUMN_NAME'])
    if actual!=TABLES[name]['fks']:raise RuntimeError('Incompatible foreign keys: '+name)
    return True


def inspect_flag(cur):
    cols=rows(cur,"SELECT COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='employees' AND column_name='lifecycle_managed'")
    if cols and cols != [{'COLUMN_TYPE':'tinyint(1)','IS_NULLABLE':'NO','COLUMN_DEFAULT':'0','EXTRA':''}]:raise RuntimeError('Incompatible lifecycle_managed column')
    all_checks=rows(cur,"SELECT t.TABLE_NAME,t.CONSTRAINT_NAME,t.ENFORCED,c.CHECK_CLAUSE FROM information_schema.table_constraints t JOIN information_schema.check_constraints c USING(CONSTRAINT_SCHEMA,CONSTRAINT_NAME) WHERE t.CONSTRAINT_SCHEMA=DATABASE() AND (t.TABLE_NAME='employees' OR t.CONSTRAINT_NAME='ck_employees_lifecycle_managed')")
    if any(c['CONSTRAINT_NAME']!='ck_employees_lifecycle_managed' and re.search(r'\blifecycle_managed\b',c['CHECK_CLAUSE'],re.I) for c in all_checks):
        raise RuntimeError('Unexpected lifecycle flag constraint')
    checks=[{k:v for k,v in c.items() if k!='CONSTRAINT_NAME'} for c in all_checks if c['CONSTRAINT_NAME']=='ck_employees_lifecycle_managed']
    if checks and checks != [{'TABLE_NAME':'employees','ENFORCED':'YES','CHECK_CLAUSE':checks[0]['CHECK_CLAUSE']}]:raise RuntimeError('Incompatible lifecycle flag CHECK')
    if checks and canonical(checks[0]['CHECK_CLAUSE'])!=canonical('lifecycle_managed in (0,1)'):raise RuntimeError('Incompatible lifecycle flag CHECK')
    if cols and rows(cur,'SELECT employee_id FROM employees WHERE lifecycle_managed NOT IN (0,1) LIMIT 1'):raise RuntimeError('Invalid lifecycle flag values')
    return bool(cols),bool(checks)


def inspect_triggers(cur):
    existing=rows(cur,"SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,EVENT_MANIPULATION,ACTION_TIMING,ACTION_STATEMENT FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND (event_object_table IN (%s,%s,%s) OR trigger_name LIKE 'hr_event_%%' OR trigger_name LIKE 'hr_request_%%')",(P,R,E))
    for t in existing:
        expected=TRIGGERS.get(t['TRIGGER_NAME'])
        if not expected or (t['EVENT_OBJECT_TABLE'],t['EVENT_MANIPULATION'],t['ACTION_TIMING'],canonical(t['ACTION_STATEMENT'])) != (expected[0],expected[1],'BEFORE',canonical(expected[2])):
            raise RuntimeError('Incompatible trigger '+t['TRIGGER_NAME'])
    return {t['TRIGGER_NAME'] for t in existing}


def upgrade(connection):
    if connection.in_transaction:raise RuntimeError('Dedicated connection outside a transaction required')
    cur=connection.cursor(dictionary=True)
    try:
        info=rows(cur,'SELECT VERSION() AS version,DATABASE() AS db')[0]
        v=re.match(r'(\d+)\.(\d+)\.(\d+)',info['version'])
        if not info['db'] or not v or 'mariadb' in info['version'].lower() or tuple(map(int,v.groups()))<(8,0,16):raise RuntimeError('Explicit database and MySQL 8.0.16+ required')
        spec=importlib.util.spec_from_file_location('hr008',Path(__file__).with_name('008_hr_employee_department_revisions.py'))
        prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
        for name in ('employees','departments'):
            if prior._inspect(cur,name)!=(True,True):raise RuntimeError('Apply compatible migration 008 first')
        user=rows(cur,"SELECT c.COLUMN_TYPE,c.IS_NULLABLE,c.COLUMN_KEY,c.EXTRA,t.ENGINE FROM information_schema.columns c JOIN information_schema.tables t USING(TABLE_SCHEMA,TABLE_NAME) WHERE c.TABLE_SCHEMA=DATABASE() AND c.TABLE_NAME='users' AND c.COLUMN_NAME='user_id'")
        if user:user[0]['COLUMN_TYPE']=column_type(user[0]['COLUMN_TYPE'])
        if user != [{'COLUMN_TYPE':'int','IS_NULLABLE':'NO','COLUMN_KEY':'PRI','EXTRA':'auto_increment','ENGINE':'InnoDB'}]:raise RuntimeError('Incompatible users identity')
        # Verify existing cross-module identity links, without altering them.
        for tbl,col,target,ref,rule in [('employees','department_id','departments','department_id','SET NULL'),('users','employee_id','employees','employee_id','SET NULL')]:
            fk=rows(cur,'SELECT k.REFERENCED_TABLE_SCHEMA,k.REFERENCED_TABLE_NAME,k.REFERENCED_COLUMN_NAME,r.DELETE_RULE,r.UPDATE_RULE FROM information_schema.key_column_usage k JOIN information_schema.referential_constraints r USING(CONSTRAINT_SCHEMA,CONSTRAINT_NAME) WHERE k.TABLE_SCHEMA=DATABASE() AND k.TABLE_NAME=%s AND k.COLUMN_NAME=%s',(tbl,col))
            if len(fk)!=1 or tuple(fk[0].values())[:4]!=(info['db'],target,ref,rule) or fk[0]['UPDATE_RULE'] not in ('RESTRICT','NO ACTION'):raise RuntimeError('Incompatible existing identity FK '+tbl)
        owners={constraint:name for name,specification in TABLES.items()
                for kind in ('checks','fks') for constraint in specification[kind]}
        for constraint in rows(cur,'SELECT TABLE_NAME,CONSTRAINT_NAME FROM information_schema.table_constraints WHERE CONSTRAINT_SCHEMA=DATABASE()'):
            expected_owner=owners.get(constraint['CONSTRAINT_NAME'])
            if expected_owner and expected_owner!=constraint['TABLE_NAME']:
                raise RuntimeError('Lifecycle constraint name already used by another table: '+constraint['CONSTRAINT_NAME'])
        state={n:inspect_table(cur,n) for n in TABLES}
        flag,check=inspect_flag(cur);triggers=inspect_triggers(cur)
        connection.commit()
        clauses=[]
        if not flag:clauses.append('ADD COLUMN lifecycle_managed TINYINT(1) NOT NULL DEFAULT 0')
        if not check:clauses.append('ADD CONSTRAINT ck_employees_lifecycle_managed CHECK (lifecycle_managed IN (0,1))')
        if clauses:cur.execute('ALTER TABLE employees '+', '.join(clauses))
        for name,present in state.items():
            if not present:cur.execute(create_table(name))
        for name,(tbl,event,body) in TRIGGERS.items():
            if name not in triggers:cur.execute(f'CREATE TRIGGER `{name}` BEFORE {event} ON `{tbl}` FOR EACH ROW '+body)
        for name in TABLES:inspect_table(cur,name)
        if inspect_flag(cur)!=(True,True) or inspect_triggers(cur)!=set(TRIGGERS):raise RuntimeError('Incomplete migration 009')
        connection.commit()
    except Exception:
        connection.rollback()  # MySQL DDL already committed is deliberately retained.
        raise
    finally:cur.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for option in ('host','user','database'):parser.add_argument('--'+option,required=True)
    parser.add_argument('--port',required=True,type=int)
    args=parser.parse_args()
    with mysql.connector.connect(**vars(args),password=getpass('MySQL password: ')) as db:upgrade(db)
    print('HR migration 009 verified/applied; no lifecycle publication performed.')


if __name__=='__main__':main()



