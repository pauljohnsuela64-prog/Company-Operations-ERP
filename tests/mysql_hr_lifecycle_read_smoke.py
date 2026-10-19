"""Employee-scoped lifecycle reads; disposable MySQL and synthetic fixtures only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import importlib.util
from pathlib import Path
import re
from unittest.mock import patch

import mysql.connector
import mysql_audit_smoke as harness
import hr_lifecycle_repository as repo
from hr_lifecycle_validation import LifecycleInputError


def run(port,data_dir):
    options=dict(host='127.0.0.1',port=port,user='root',password='')
    with mysql.connector.connect(**options) as db:
        cur=db.cursor();cur.execute('SELECT @@datadir')
        assert Path(cur.fetchone()[0]).resolve()==data_dir.resolve()
        cur.execute('CREATE DATABASE hr_lifecycle_reads')
    options['database']='hr_lifecycle_reads'

    def sql(query,params=(),fetch=False):
        with mysql.connector.connect(**options) as db:
            cur=db.cursor(dictionary=True);cur.execute(query,params)
            result=cur.fetchall() if fetch else cur.lastrowid
            db.commit();return result
    text=(harness.ROOT/'database/core_schema.sql').read_text()
    for stmt in re.sub(r'--[^\n]*','',text).split(';'):
        if stmt.strip() and not re.match(r'\s*(CREATE DATABASE|USE)\b',stmt,re.I):sql(stmt)
    spec=importlib.util.spec_from_file_location('read_hr009',harness.ROOT/'database/migrations/009_hr_employment_lifecycle.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with mysql.connector.connect(**options) as db:migration.upgrade(db)
    sql("INSERT INTO roles(role_id,role_name) VALUES(1,'Synthetic')")
    sql("INSERT INTO employees(employee_id,employee_number,first_name,last_name,hire_date,revision) VALUES(1,'SYN-1','Synthetic','One','1999-01-01',17),(2,'SYN-2','Synthetic','Two','1998-01-01',23),(3,'SYN-3','Synthetic','Three',NULL,1)")
    sql("INSERT INTO users(user_id,username,password_hash,role_id) VALUES(1,'synthetic','not-a-credential',1)")

    def period(employee,sequence,start,end=None,void=0):
        return sql('INSERT INTO employee_employment_periods(employee_id,period_sequence,verified_start_date,end_exclusive_date,is_void,publication_revision) VALUES(%s,%s,%s,%s,%s,1)',
                   (employee,sequence,start,end,void))
    def request(employee,event_type,effective,order=1,period_id=None):
        return sql("INSERT INTO employee_lifecycle_requests(employee_id,employment_period_id,event_type,effective_date,effective_order,expected_employee_revision,proposal_data,source_type,source_reference,reason,submitted_by,decision_state) VALUES(%s,%s,%s,%s,%s,17,'{}','DOCUMENT','synthetic-only','Synthetic',1,'PENDING')",
                   (employee,period_id,event_type,effective,order))
    def event(revision,event_type,effective,order=1,supersedes=None,employee=1,period_id=None):
        r=request(employee,event_type,effective,order,period_id)
        return sql("INSERT INTO employee_employment_events(employee_id,employment_period_id,request_id,event_type,effective_date,effective_order,publication_revision,changes,source_type,source_reference,reason,recorded_by,supersedes_event_id) VALUES(%s,%s,%s,%s,%s,%s,%s,'{}','DOCUMENT','synthetic-only','Synthetic',1,%s)",
                   (employee,period_id,r,event_type,effective,order,revision,supersedes))
    p1=period(1,1,'2020-01-01','2021-01-01')
    period(1,2,'2022-01-01')
    period(1,3,'2019-01-01','2020-02-01',1)  # void projection cannot fill unknown gap
    period(1,4,'2020-06-01','2020-10-01')  # overlap is not prohibited by policy
    e1=event(1,'HIRE','2024-06-01',period_id=p1)
    e2=event(2,'LEGACY_OBSERVATION','2018-01-01')
    e3=event(3,'TRANSFER','2024-06-01',2)
    e4=event(4,'CORRECT','2019-01-01',supersedes=e1)
    e5=event(5,'VOID','2019-01-01',supersedes=e4)
    e6=event(6,'POSITION_CHANGE','2024-06-01',1)
    e_other=event(1,'LEGACY_OBSERVATION','2020-01-01',employee=2)
    r_other=request(2,'STATUS_CHANGE','2024-01-01')
    sql("UPDATE employee_lifecycle_requests SET decision_state='REJECTED',decided_by=1,decision_reason='Synthetic' WHERE request_id=%s",(r_other,))
    sql("CREATE USER 'lifecycle_reader'@'127.0.0.1' IDENTIFIED BY 'synthetic-disposable-only'")
    sql("GRANT SELECT ON hr_lifecycle_reads.* TO 'lifecycle_reader'@'127.0.0.1'")
    reader_options={**options,'user':'lifecycle_reader','password':'synthetic-disposable-only'}
    def connect_reader():return mysql.connector.connect(**reader_options)
    def snapshot():
        tables=['employees','departments','users','permissions','role_permissions',*migration.TABLES]
        return {t:sql('SELECT * FROM '+t+' ORDER BY 1',fetch=True) for t in tables}
    before=snapshot()
    for mode in ('STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE',''):
        reader_options['init_command']="SET SESSION sql_mode='"+mode+"'"
        with patch.object(repo,'get_connection',side_effect=connect_reader):
            assert repo.get_lifecycle_status(1)==dict(employee_id=1,lifecycle_managed=0,revision=17)
            assert repo.get_lifecycle_status(999) is None
            periods=repo.list_employment_periods(1)
            assert len(periods)==4 and periods[0]['is_void']==1
            assert len([p for p in periods if p['end_exclusive_date'] is None])==1
            assert repo.list_employment_periods(999)==[]
            events=repo.list_employment_events(1)
            expected=[e2,e4,e5,e1,e6,e3]
            assert [e['employment_event_id'] for e in events]==expected
            assert [e['employment_event_id'] for offset in (0,2,4) for e in repo.list_employment_events(1,limit=2,offset=offset)]==expected
            assert repo.list_employment_events(1,offset=100)==[]
            assert repo.get_employment_event(1,e_other) is None
            assert repo.get_employment_event(2,e1) is None
            assert repo.get_employment_event(1,999) is None
            assert repo.get_correction_relationships(1,e1)['superseded_by_event_id']==e4
            assert repo.get_correction_relationships(1,e4)['supersedes_event_id']==e1
            assert repo.get_correction_relationships(1,e4)['superseded_by_event_id']==e5
            assert repo.get_correction_relationships(2,e1) is None
            requests=repo.list_lifecycle_requests(1)
            assert len(requests)==6 and all(r['decision_state']=='PENDING' for r in requests)
            assert len(repo.list_lifecycle_requests(1,limit=2))==2
            assert [r['request_id'] for r in requests]==[r['request_id'] for offset in (0,2,4) for r in repo.list_lifecycle_requests(1,limit=2,offset=offset)]
            assert repo.get_lifecycle_request(1,r_other) is None
            assert repo.get_lifecycle_request(2,r_other)['proposal_data']=='{}'
            assert repo.get_lifecycle_request(2,r_other)['decision_state']=='REJECTED'
            coverage=repo.get_history_coverage(1,date(2018,1,1),date(2025,1,1))
            assert coverage['unknown_intervals']==[
                {'start':date(2018,1,1),'end_exclusive':date(2020,1,1)},
                {'start':date(2021,1,1),'end_exclusive':date(2022,1,1)}]
            assert len(coverage['recorded_period_coverage'])==2
            assert coverage['observed_legacy_event_count']==1
            assert coverage['source_verification_performed'] is False
            for employee in (2,3):
                unknown=repo.get_history_coverage(employee,date(2018,1,1),date(2025,1,1))
                assert unknown['recorded_period_coverage']==[]
                assert unknown['unknown_intervals']==[{'start':date(2018,1,1),'end_exclusive':date(2025,1,1)}]
            assert repo.get_history_coverage(999,date(2020,1,1),date(2021,1,1)) is None
            with ThreadPoolExecutor(max_workers=6) as pool:
                reads=list(pool.map(lambda _:repo.list_employment_events(1),range(24)))
            assert all(rows==events for rows in reads)
        assert snapshot()==before
        print('PASS SELECT-only account, Employee scoping, effective/same-day/backdated order, pagination, corrections, unknown coverage, concurrent reads and no mutations in',mode or 'NON-STRICT')

    # A concurrent fixture insert after the first read must not tear a coverage snapshot.
    class SnapshotCursor:
        def __init__(self,inner):self.inner=inner;self.first=True
        def __getattr__(self,name):return getattr(self.inner,name)
        def fetchone(self):
            row=self.inner.fetchone()
            if self.first:
                self.first=False;period(3,1,'2020-01-01','2021-01-01')
            return row
    class SnapshotConnection:
        def __init__(self,inner):self.inner=inner
        def __getattr__(self,name):return getattr(self.inner,name)
        def cursor(self,*args,**kwargs):return SnapshotCursor(self.inner.cursor(*args,**kwargs))
    with patch.object(repo,'get_connection',side_effect=lambda:SnapshotConnection(connect_reader())):
        coverage=repo.get_history_coverage(3,date(2020,1,1),date(2021,1,1))
        assert coverage['recorded_period_coverage']==[]
    with patch.object(repo,'get_connection',side_effect=connect_reader):
        assert len(repo.get_history_coverage(3,date(2020,1,1),date(2021,1,1))['recorded_period_coverage'])==1
        with patch.object(repo,'MAX_COVERAGE_PERIODS',1):
            try:repo.get_history_coverage(1,date(2018,1,1),date(2025,1,1))
            except LifecycleInputError:pass
            else:raise AssertionError('Truncated coverage must fail explicitly')
    assert sql('SELECT revision,lifecycle_managed FROM employees ORDER BY employee_id',fetch=True)==[
        {'revision':17,'lifecycle_managed':0},{'revision':23,'lifecycle_managed':0},{'revision':1,'lifecycle_managed':0}]
    print('PASS repeatable snapshot under concurrent fixture insert, bounded coverage refusal and unchanged HR revisions')


if __name__=='__main__':
    harness.run=run
    harness.main()
