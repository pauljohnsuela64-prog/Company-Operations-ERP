"""Explicit correction-reference extension; no data backfill or payroll cutover."""
import argparse
from getpass import getpass
import hashlib
from importlib.util import module_from_spec,spec_from_file_location
from pathlib import Path
import mysql.connector


def foundation():
    spec=spec_from_file_location('correction_foundation_006',Path(__file__).with_name('006_payroll_certification.py'))
    module=module_from_spec(spec);spec.loader.exec_module(module);return module


def upgrade(connection):
    if connection.in_transaction:raise RuntimeError('Use a fresh migration connection.')
    module=foundation();base=module.base
    cursor=connection.cursor(dictionary=True);locks=[];mode=None
    columns=[('correction_reason','VARCHAR(255) NULL'),('correction_reference','VARCHAR(255) NULL')]
    check="(correction_reason IS NULL AND correction_reference IS NULL) OR (correction_reason IS NOT NULL AND correction_reference IS NOT NULL AND CHAR_LENGTH(TRIM(correction_reason)) > 0 AND CHAR_LENGTH(TRIM(correction_reference)) > 0)"
    original=module.TRIGGERS['pcc_seal_events_006']
    replacement=(*original[:3],original[3].replace("'Certification replaced by a complete revision',NEW.roster_source_reference","NEW.correction_reason,NEW.correction_reference"))
    extra={
        'pcc_correction_insert_007':(module.CERT,'INSERT','BEFORE',"""BEGIN
            IF NEW.predecessor_certification_id IS NOT NULL AND (NEW.correction_reason IS NULL OR NEW.correction_reference IS NULL) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Replacement requires correction reason and reference'; END IF;
        END"""),
        'pcc_correction_seal_007':(module.CERT,'UPDATE','BEFORE',"""BEGIN
            IF NEW.state='SEALED' AND NEW.predecessor_certification_id IS NOT NULL AND (NEW.correction_reason IS NULL OR NEW.correction_reference IS NULL) THEN
                SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Replacement requires correction reason and reference'; END IF;
        END"""),
    }
    try:
        module._prerequisites(cursor)
        for prefix in ('erp_cert_006_','erp_correction_007_'):
            name=prefix+hashlib.sha256(cursor._policy_database.encode()).hexdigest()[:32]
            cursor.execute('SELECT GET_LOCK(%s,0) acquired',(name,))
            if cursor.fetchone()['acquired']!=1:raise RuntimeError('Another evidence migration is running.')
            locks.append(name)
        existing_columns=base._columns(cursor,module.CERT)
        cols,indexes,fks,checks=module.TABLES[module.CERT]
        checks=dict(checks,chk_pcc_correction_007=check)
        existing_checks=base._checks(cursor,module.CERT)
        prerequisite_checks={n:v for n,v in checks.items() if n!='chk_pcc_correction_007' or n in existing_checks}
        module.TABLES[module.CERT]=(cols+[item for item in columns if item[0] in existing_columns],indexes,fks,prerequisite_checks)
        rows=base._rows(cursor,"SELECT ACTION_STATEMENT FROM information_schema.triggers WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='pcc_seal_events_006'")
        if rows:
            actual=base._normal_sql(rows[0]['ACTION_STATEMENT'])
            if actual not in (base._normal_sql(original[3]),base._normal_sql(replacement[3])):
                raise RuntimeError('Incompatible certification seal trigger; manual review required.')
            module.TRIGGERS['pcc_seal_events_006']=original if actual==base._normal_sql(original[3]) else replacement
        module.TRIGGERS.update(extra)
        for table,manifest in module.TABLES.items():module._verify(cursor,table,manifest,True,True)
        for table,manifest in module.ADDITIONS.items():module._verify(cursor,table,manifest,True)
        found=module._triggers(cursor)
        if set(module.TRIGGERS)-set(extra)-{'pcc_seal_events_006'}-found:
            raise RuntimeError('Migration 006 protections are incomplete. Verify 006 before upgrading.')
        cursor.execute('SELECT @@SESSION.sql_mode mode');mode=cursor.fetchone()['mode']
        cursor.execute('SET SESSION sql_mode=%s',(module.MODE,))
        for name,definition in columns:
            if name not in existing_columns:cursor.execute(f'ALTER TABLE `{module.CERT}` ADD COLUMN `{name}` {definition}')
        if 'chk_pcc_correction_007' not in base._checks(cursor,module.CERT):
            cursor.execute(f'ALTER TABLE `{module.CERT}` ADD CONSTRAINT chk_pcc_correction_007 CHECK ({check})')
        if rows and base._normal_sql(rows[0]['ACTION_STATEMENT'])!=base._normal_sql(replacement[3]):
            cursor.execute('DROP TRIGGER pcc_seal_events_006');found.discard('pcc_seal_events_006')
        module.TRIGGERS['pcc_seal_events_006']=replacement
        for name,(table,event,timing,body) in module.TRIGGERS.items():
            if name not in found:cursor.execute(f'CREATE TRIGGER `{name}` {timing} {event} ON `{table}` FOR EACH ROW {body}')
        module.TABLES[module.CERT]=(cols+columns,indexes,fks,checks)
        for table,manifest in module.TABLES.items():module._verify(cursor,table,manifest,True,True)
        module._triggers(cursor,True);connection.commit()
    finally:
        connection.rollback()
        if mode is not None:cursor.execute('SET SESSION sql_mode=%s',(mode,))
        for name in reversed(locks):cursor.execute('SELECT RELEASE_LOCK(%s)',(name,));cursor.fetchall()
        cursor.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('host','user','database'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--port',type=int,required=True);args=parser.parse_args()
    with mysql.connector.connect(host=args.host,port=args.port,user=args.user,password=getpass('MySQL password: '),database=args.database) as connection:upgrade(connection)
    print('Correction references verified. No history, grants or payment rules were changed.')


if __name__=='__main__':main()
