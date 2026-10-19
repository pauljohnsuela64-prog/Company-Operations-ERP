"""Internal Employee-scoped SELECT-only readers. No authorization/public routes.

Future callers must authorize each Employee before calling. No current-state
inference, publication, approval, revision increment, or central audit writes.
"""
from contextlib import contextmanager

from mysql.connector import Error
from database import get_connection
from hr_lifecycle_validation import (positive_integer, business_date, INT_MAX,
                                     LifecycleInputError)

MAX_PAGE_SIZE=100
MAX_OFFSET=100000
MAX_COVERAGE_PERIODS=1000


class LifecycleReadError(Exception):
    """Confidentiality-safe storage failure without SQL or employee details."""


def _scope(employee_id):
    return positive_integer(employee_id,'Employee ID',INT_MAX)


def _page(limit,offset):
    positive_integer(limit,'Page size',MAX_PAGE_SIZE)
    if type(offset) is not int or not 0 <= offset <= MAX_OFFSET:
        raise LifecycleInputError('Offset is outside the supported range.')
    return limit,offset


@contextmanager
def _snapshot_reader():
    connection=None
    cursor=None
    try:
        try:connection=get_connection()
        except ValueError:
            raise LifecycleReadError('Employment history is temporarily unavailable.') from None
        # Fresh dedicated connection; coherent snapshots for multi-query diagnostics.
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,
                                     consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        yield cursor
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:
            if connection is not None:
                try:connection.rollback()  # End read-only snapshot; never commit writes.
                finally:connection.close()


@contextmanager
def _reader():
    try:
        with _snapshot_reader() as cur:yield cur
    except Error:
        raise LifecycleReadError('Employment history is temporarily unavailable.') from None


def get_lifecycle_status(employee_id):
    employee_id=_scope(employee_id)
    with _reader() as cur:
        cur.execute('SELECT employee_id,lifecycle_managed,revision FROM employees WHERE employee_id=%s',(employee_id,))
        return cur.fetchone()  # Missing and out-of-scope details consistently return None.


def list_employment_periods(employee_id,*,limit=50,offset=0):
    employee_id=_scope(employee_id);limit,offset=_page(limit,offset)
    with _reader() as cur:
        cur.execute('SELECT * FROM employee_employment_periods WHERE employee_id=%s ORDER BY verified_start_date,period_sequence,employment_period_id LIMIT %s OFFSET %s',
                    (employee_id,limit,offset))
        return cur.fetchall()  # Void/open/closed rows retained, never silently filtered.


_EVENT_SELECT='''SELECT e.*, successor.employment_event_id AS superseded_by_event_id
FROM employee_employment_events e LEFT JOIN employee_employment_events successor
ON successor.employee_id=e.employee_id AND successor.supersedes_event_id=e.employment_event_id'''


def list_employment_events(employee_id,*,limit=50,offset=0):
    employee_id=_scope(employee_id);limit,offset=_page(limit,offset)
    with _reader() as cur:
        cur.execute(_EVENT_SELECT+' WHERE e.employee_id=%s ORDER BY e.effective_date,e.effective_order,e.publication_revision,e.employment_event_id LIMIT %s OFFSET %s',
                    (employee_id,limit,offset))
        return cur.fetchall()


def get_employment_event(employee_id,event_id):
    employee_id=_scope(employee_id);positive_integer(event_id,'Event ID')
    with _reader() as cur:
        cur.execute(_EVENT_SELECT+' WHERE e.employee_id=%s AND e.employment_event_id=%s',(employee_id,event_id))
        return cur.fetchone()


def list_lifecycle_requests(employee_id,*,limit=50,offset=0):
    employee_id=_scope(employee_id);limit,offset=_page(limit,offset)
    with _reader() as cur:
        cur.execute('SELECT * FROM employee_lifecycle_requests WHERE employee_id=%s ORDER BY effective_date,effective_order,request_id LIMIT %s OFFSET %s',
                    (employee_id,limit,offset))
        return cur.fetchall()


def get_lifecycle_request(employee_id,request_id):
    employee_id=_scope(employee_id);positive_integer(request_id,'Request ID')
    with _reader() as cur:
        cur.execute('SELECT * FROM employee_lifecycle_requests WHERE employee_id=%s AND request_id=%s',(employee_id,request_id))
        return cur.fetchone()


def get_correction_relationships(employee_id,event_id):
    """Immediate predecessor/successor only; no implicit correction application."""
    row=get_employment_event(employee_id,event_id)
    if row is None:return None
    return {k:row[k] for k in ('employee_id','employment_event_id','supersedes_event_id','superseded_by_event_id')}


def get_history_coverage(employee_id,start,end_exclusive):
    """Bounded DATE window; gaps mean unknown, never proof of nonemployment.

    Periods are recorded verified-period projections, not independent source
    verification. Events/legacy observations alone never establish coverage.
    """
    employee_id=_scope(employee_id)
    business_date(start,'Coverage start');business_date(end_exclusive,'Coverage end')
    if end_exclusive<=start:raise LifecycleInputError('Coverage end must follow start.')
    with _reader() as cur:
        cur.execute('SELECT employee_id,lifecycle_managed,revision FROM employees WHERE employee_id=%s',(employee_id,))
        status=cur.fetchone()
        if status is None:return None
        cur.execute('SELECT employment_period_id,verified_start_date,end_exclusive_date FROM employee_employment_periods WHERE employee_id=%s AND is_void=0 AND verified_start_date<%s AND (end_exclusive_date IS NULL OR end_exclusive_date>%s) ORDER BY verified_start_date,period_sequence,employment_period_id LIMIT %s',
                    (employee_id,end_exclusive,start,MAX_COVERAGE_PERIODS+1))
        periods=cur.fetchall()
        if len(periods)>MAX_COVERAGE_PERIODS:
            raise LifecycleInputError('Too many periods; request a narrower coverage window.')
        cur.execute("SELECT COUNT(*) AS observed_legacy_event_count FROM employee_employment_events WHERE employee_id=%s AND event_type='LEGACY_OBSERVATION' AND effective_date>=%s AND effective_date<%s",
                    (employee_id,start,end_exclusive))
        observations=cur.fetchone()['observed_legacy_event_count']
        covered=[]
        for period in periods:
            left=max(start,period['verified_start_date'])
            right=min(end_exclusive,period['end_exclusive_date'] or end_exclusive)
            if covered and left<=covered[-1]['end_exclusive']:
                covered[-1]['end_exclusive']=max(covered[-1]['end_exclusive'],right)
            else:covered.append({'start':left,'end_exclusive':right})
        unknown=[];position=start
        for interval in covered:
            if position<interval['start']:unknown.append({'start':position,'end_exclusive':interval['start']})
            position=interval['end_exclusive']
        if position<end_exclusive:unknown.append({'start':position,'end_exclusive':end_exclusive})
        return {**status,'window_start':start,'window_end_exclusive':end_exclusive,
                'recorded_period_coverage':covered,'unknown_intervals':unknown,
                'periods':periods,'observed_legacy_event_count':observations,
                'source_verification_performed':False}
