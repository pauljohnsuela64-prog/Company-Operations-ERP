"""Migration 010 compatibility, legacy preservation and runtime admission."""
from contextlib import ExitStack
import importlib
import importlib.util
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness


def run(port, data_dir):
    options = dict(host='127.0.0.1', port=port, user='root', password='', connection_timeout=3)
    with mysql.connector.connect(**options) as db:
        cur = db.cursor(); cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve() == data_dir.resolve()
    spec = importlib.util.spec_from_file_location('migration010', harness.ROOT/'database/migrations/010_payroll_attendance_freshness.py')
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    import payroll_freshness as freshness

    def create(name, payroll=True, attendance=True):
        with mysql.connector.connect(**options) as db:
            cur = db.cursor(); cur.execute('CREATE DATABASE ' + name); cur.execute('USE ' + name)
            files = ['core'] + (['attendance'] if attendance else [])
            if payroll:
                files += ['payroll','payroll_period','payroll_entries','payroll_calculation','payroll_approval','payroll_adjustments','leave']
            for file in files:
                source = (harness.ROOT/'database'/f'{file}_schema.sql').read_text()
                source = source.split('-- Payroll attendance freshness:')[0]
                for statement in re.sub(r'--[^\n]*','',source).split(';'):
                    if statement.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',statement,re.I):
                        cur.execute(statement)
            cur.execute("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic migration operator')")
            cur.execute("INSERT INTO users(user_id,role_id,username,password_hash) VALUES(1,1,'synthetic-migration','test-only')")
            cur.execute("INSERT INTO employees(employee_id,employee_number,first_name,last_name) VALUES(1,'MIGRATION','Synthetic','Employee')")
            if attendance:
                cur.execute("INSERT INTO attendance_records(employee_id,attendance_date,status,created_by) VALUES(1,'2026-01-05','PRESENT',1)")
            if payroll:
                cur.execute("INSERT INTO employee_compensation(compensation_id,employee_id,pay_type,basic_rate,effective_date,created_by) VALUES(1,1,'MONTHLY',1000,'2026-01-01',1)")
                for index,status in enumerate(('DRAFT','PROCESSING','APPROVED','PAID'),1):
                    cur.execute("INSERT INTO payroll_periods(payroll_period_id,period_number,period_name,start_date,end_date,pay_date,status,created_by) VALUES(%s,%s,%s,'2026-01-05','2026-01-05','2026-01-06',%s,1)", (index,'MIG-'+str(index),'Legacy '+status,status))
                    cur.execute("INSERT INTO payroll_entries(payroll_period_id,employee_id,compensation_id,pay_type,basic_rate,net_pay,status,generated_by,calculated_at) VALUES(%s,1,1,'MONTHLY',1000,100,%s,1,'2026-01-06')", (index,status if status in ('APPROVED','PAID') else 'CALCULATED'))
            db.commit()
        return dict(options, database=name)

    def execute(config, query, params=(), fetch=False):
        with mysql.connector.connect(**config) as db:
            cur = db.cursor(); cur.execute(query,params)
            result = cur.fetchall() if fetch else None
            db.commit(); return result

    for partial in (False, True):
        name = 'erp_migration010_' + ('partial' if partial else 'legacy')
        config = create(name)
        if partial:
            execute(config, freshness.GENERATIONS_DDL)
            execute(config, "INSERT INTO payroll_attendance_generations VALUES(1,'2026-01-05',7)")
            execute(config, 'ALTER TABLE payroll_entries ADD COLUMN attendance_scope_start DATE NULL')
        before = {}
        with mysql.connector.connect(**config) as db:
            cur = db.cursor()
            for table in ('employees','attendance_records','payroll_periods','payroll_entries'):
                cur.execute('SELECT * FROM ' + table)
                before[table] = (cur.column_names, cur.fetchall())
            migration.migrate(db,name)
            migration.migrate(db,name)
            for table,(columns,rows) in before.items():
                cur.execute('SELECT ' + ','.join(columns) + ' FROM ' + table)
                assert cur.fetchall() == rows, table
            cur.execute('SELECT COUNT(*) FROM payroll_entries WHERE attendance_evidence_version IS NOT NULL')
            assert cur.fetchone() == (0,)
            cur.execute('SELECT COUNT(*) FROM payroll_attendance_snapshots')
            assert cur.fetchone() == (0,)
            cur.execute('SELECT * FROM payroll_attendance_guard')
            assert cur.fetchall() == [(1,)]
            cur.execute('SELECT generation FROM payroll_attendance_generations')
            assert cur.fetchall() == ([(7,)] if partial else [])
        with ExitStack() as stack:
            stack.enter_context(patch('dotenv.load_dotenv', return_value=False))
            workflow = importlib.import_module('payroll_workflow_repository')
            stack.enter_context(patch.object(workflow,'get_connection',side_effect=lambda:mysql.connector.connect(**config)))
            try:
                workflow.mark_payroll_period_as_paid(3,1)
            except freshness.FreshnessError as error:
                assert 'unverified' in str(error) and 'recovery' in str(error)
            else:
                raise AssertionError('Legacy APPROVED Payroll was attested by migration')
            assert execute(config,'SELECT status FROM payroll_periods WHERE payroll_period_id=3',fetch=True) == [('APPROVED',)]
        print('PASS repeatable/partial migration preserves source, PAID history, all legacy amounts/statuses and unknown evidence:', name)

    config = create('erp_migration010_attendance_only', payroll=False)
    with mysql.connector.connect(**config) as db:
        migration.migrate(db,config['database'])
    assert execute(config,"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_entries'",fetch=True) == [(0,)]
    print('PASS Attendance-only upgrade does not install optional Payroll business tables')
    config = create('erp_migration010_core_only', payroll=False, attendance=False)
    with mysql.connector.connect(**config) as db:
        migration.migrate(db,config['database'])
    assert execute(config,"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('attendance_records','payroll_entries')",fetch=True) == [(0,)]
    print('PASS core-only upgrade adds coordination without installing optional business modules')

    for defect in ('engine','columns','check','metadata'):
        config = create('erp_migration010_bad_' + defect)
        if defect == 'metadata':
            execute(config,'ALTER TABLE payroll_entries ADD COLUMN attendance_evidence_version INT NOT NULL DEFAULT 1')
        else:
            statement = freshness.GENERATIONS_DDL
            if defect == 'engine': statement = statement.replace('ENGINE=InnoDB','ENGINE=MyISAM')
            if defect == 'columns': statement = statement.replace('generation BIGINT','generation INT')
            if defect == 'check': statement = statement.replace('generation >= 1','generation >= 0')
            execute(config, statement)
        try:
            with mysql.connector.connect(**config) as db:
                migration.migrate(db,config['database'])
        except freshness.FreshnessError:
            pass
        else:
            raise AssertionError('Incompatible preflight accepted: ' + defect)
        assert execute(config,"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_attendance_guard'",fetch=True) == [(0,)]
        print('PASS incompatible preflight refuses before additive DDL:', defect)

    config = create('erp_migration010_wrong_target')
    try:
        with mysql.connector.connect(**config) as db:
            migration.migrate(db, 'different_explicit_database')
    except freshness.FreshnessError:
        pass
    else:
        raise AssertionError('Wrong selected database accepted')
    print('SUCCESS: migration 010 checks used only verified disposable MySQL')


if __name__ == '__main__':
    harness.run = run
    harness.main()
