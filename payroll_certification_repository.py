"""Cutoff certification preparation; production publication awaits approved sources."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import re

from database import get_connection
from payroll_freshness import lock_payroll_inputs, raise_payroll_lock_error
from payroll_generation_repository import month_cutoffs, _resolve
from payroll_policy_validation import positive_integer, text
from payroll_validation import payroll_money

PUBLICATION_BLOCKER = ('Publication is unavailable: approved authoritative roster, employment/rate and '
                       'calendar sources, and company certifier authority have not been established.')


def authoritative_evidence(period, actor_id):
    """No production adapter exists. Tests explicitly supply synthetic evidence here.

    Never populate this from a form, environment flag, Active status, or a checkbox.
    """
    return None


def _json(value):
    if isinstance(value, (date, datetime)):return value.isoformat()
    if isinstance(value, Decimal):return format(value, '.2f')
    raise TypeError('Unsupported certification evidence type')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=_json,
                                    ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def reference(value, label):
    result=text(value,label,255)
    if len(result)<3 or result.casefold() in ('pending','unknown','none','n/a','test','todo'):
        raise ValueError(f'{label} requires a meaningful supporting reference.')
    return result


def optional_date(value,label):
    if value in (None,''):return None
    if isinstance(value,datetime):raise ValueError(f'{label} must be a date.')
    if isinstance(value,date):result=value
    else:
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',str(value)):raise ValueError()
            result=date.fromisoformat(value)
        except (ValueError,TypeError):raise ValueError(f'{label} must be a valid YYYY-MM-DD date.') from None
    if result.year<1000:raise ValueError(f'{label} is outside the supported date range.')
    return result


def scheduled_dates(period):
    return [(period['start_date']+timedelta(days=n)).isoformat()
            for n in range((period['end_date']-period['start_date']).days+1)
            if (period['start_date']+timedelta(days=n)).weekday()<5]


def _decode(row):
    if row:
        for key in ('roster_scope','calendar_configuration','schedule_evidence'):
            if isinstance(row.get(key),(str,bytes)):row[key]=json.loads(row[key])
    return row


def _load(cursor,cid,lock=False):
    cursor.execute('SELECT * FROM payroll_cutoff_certifications WHERE certification_id=%s'+(' FOR UPDATE' if lock else ''),(cid,))
    row=_decode(cursor.fetchone())
    if not row:raise ValueError('Certification not found.')
    cursor.execute('SELECT * FROM payroll_certification_members WHERE certification_id=%s ORDER BY employee_id'+(' FOR UPDATE' if lock else ''),(cid,))
    row['members']=[_decode(member) for member in cursor.fetchall()]
    cursor.execute('SELECT * FROM payroll_certification_events WHERE certification_id=%s ORDER BY certification_event_id'+(' FOR UPDATE' if lock else ''),(cid,))
    row['events']=cursor.fetchall()
    return row


def revision_token(row):
    return digest({k:v for k,v in row.items() if k not in ('source_stale','source_consistent','terminal_events')})


def _expected(row,token):
    if not isinstance(token,str) or not hmac.compare_digest(revision_token(row),token):
        raise ValueError('Certification changed or its source review is stale. Reload and review before retrying.')


def _transaction(operation):
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:
        connection.start_transaction();lock_payroll_inputs(cursor)
        result=operation(cursor);connection.commit();return result
    except Exception as error:
        connection.rollback();raise_payroll_lock_error(error)
        if getattr(error,'errno',None)==1062:raise ValueError('The revision or transition already exists. Reload and review.') from error
        raise
    finally:cursor.close();connection.close()


def _period(cursor,pid,require_draft=True):
    pid=positive_integer(pid,'Payroll period',2147483647)
    cursor.execute('SELECT * FROM payroll_periods WHERE payroll_period_id=%s FOR UPDATE',(pid,))
    period=cursor.fetchone()
    if not period:raise ValueError('Payroll period not found.')
    # Withdrawal of certification must remain possible when its supporting policy
    # or legacy cutoff is invalid. Revocation does not authorize financial actions.
    if not require_draft:return period
    if require_draft and period['status']!='DRAFT':raise ValueError('Certification preparation/publication requires a DRAFT period.')
    if period['policy_version_id'] is None or period['cutoff_code'] not in ('A','B'):
        raise ValueError('Certification requires a policy-pinned cutoff. Legacy references were not changed.')
    cutoffs=month_cutoffs(period['start_date'].year,period['start_date'].month)
    cutoff=next(c for c in cutoffs if c['cutoff_code']==period['cutoff_code'])
    if any(cutoff[key]!=period[key] for key in ('start_date','end_date')):
        raise ValueError('Period dates do not match the supported cutoff calendar.')
    resolved=_resolve(cursor,[cutoff])[0]
    if resolved['policy_version_id']!=period['policy_version_id']:
        raise ValueError('Pinned policy does not cover this entire cutoff.')
    return period


def _sources(cursor,ids,lock=True):
    # Current reads after the shared guard. Names/contact details are not evidence inputs.
    cursor.execute('SELECT employee_id FROM employees ORDER BY employee_id'+(' FOR SHARE' if lock else ''))
    population=[row['employee_id'] for row in cursor.fetchall()]
    rows=[]
    for eid in sorted(ids):
        cursor.execute('SELECT employee_id,hire_date,employment_status FROM employees WHERE employee_id=%s'+(' FOR SHARE' if lock else ''),(eid,))
        employee=cursor.fetchone()
        if not employee:raise ValueError(f'Employee {eid} does not exist. No record was substituted.')
        cursor.execute('SELECT compensation_id,employee_id,pay_type,basic_rate,currency_code,effective_date FROM employee_compensation WHERE employee_id=%s'+(' FOR SHARE' if lock else ''),(eid,))
        employee['compensation']=cursor.fetchone();rows.append(employee)
    return dict(population=population,employees=rows)


def validate_exceptions(period,exceptions):
    if exceptions is None:return []
    if not isinstance(exceptions,list) or len(exceptions)>1000:raise ValueError('Invalid calendar exception list.')
    result=[]
    for item in exceptions:
        if set(item)!= {'date','kind','source_reference'}:raise ValueError('Invalid calendar exception fields.')
        when=optional_date(item['date'],'Exception date')
        if when is None or not period['start_date']<=when<=period['end_date']:raise ValueError('Exception date must fall inside this cutoff.')
        if item['kind'] not in ('HOLIDAY','SPECIAL_PAY','SCHEDULE_EXCEPTION'):raise ValueError('Select a valid exception kind.')
        result.append(dict(date=when.isoformat(),kind=item['kind'],source_reference=reference(item['source_reference'],'Exception reference')))
    return result


def _header(cursor,period,ids,roster_ref,calendar_ref,exceptions=None):
    if not isinstance(ids,(list,tuple)):raise ValueError('Declare the employee roster explicitly.')
    ids=sorted(positive_integer(eid,'Employee',2147483647) for eid in ids)
    if len(ids)!=len(set(ids)) or not ids or len(ids)>100000:raise ValueError('Declare a nonempty roster of at most 100,000 employees without duplicates.')
    return dict(roster_scope=dict(kind='EXPLICIT_EMPLOYEE_ROSTER',employee_ids=ids),
                roster_source_reference=reference(roster_ref,'Roster source'),
                calendar_source_reference=reference(calendar_ref,'Calendar source'),
                calendar_configuration=dict(timezone='Asia/Manila',working_week_mask=31,
                                            scheduled_dates=scheduled_dates(period),exceptions=validate_exceptions(period,exceptions)),
                source_digest=digest(_sources(cursor,ids)))


def prepare(period_id,ids,roster_reference,calendar_reference,actor_id,predecessor_id=None,
            correction_reason=None,correction_reference=None,predecessor_token=None,calendar_exceptions=None):
    actor_id=positive_integer(actor_id,'Acting user',2147483647)
    def write(cursor):
        period=_period(cursor,period_id)
        cursor.execute('SELECT * FROM payroll_cutoff_certifications WHERE payroll_period_id=%s ORDER BY revision DESC LIMIT 1 FOR UPDATE',(period_id,))
        previous=cursor.fetchone()
        if previous:
            if predecessor_id is None or positive_integer(predecessor_id,'Predecessor')!=previous['certification_id'] or previous['state']!='SEALED':
                raise ValueError('A revision exists. Review the latest revision before preparing a correction.')
            _expected(_load(cursor,previous['certification_id'],True),predecessor_token)
            correction=dict(correction_reason=reference(correction_reason,'Correction reason'),
                            correction_reference=reference(correction_reference,'Correction reference'))
        else:correction={}
        if predecessor_id is not None and previous is None:raise ValueError('The expected predecessor does not exist.')
        header=_header(cursor,period,ids,roster_reference,calendar_reference,calendar_exceptions)
        header.update(payroll_period_id=period_id,policy_version_id=period['policy_version_id'],revision=previous['revision']+1 if previous else 1,
                      cutoff_code=period['cutoff_code'],start_date=period['start_date'],end_date=period['end_date'],
                      configuration_digest=digest(header['calendar_configuration']),created_by=actor_id,
                      created_at=datetime.now(timezone.utc).replace(tzinfo=None))
        header.update(correction)
        if previous:header['predecessor_certification_id']=previous['certification_id']
        columns=list(header)
        cursor.execute('INSERT INTO payroll_cutoff_certifications('+','.join(columns)+') VALUES('+','.join(['%s']*len(columns))+')',
                       tuple(json.dumps(header[k]) if isinstance(header[k],dict) else header[k] for k in columns))
        return _load(cursor,cursor.lastrowid)
    return _transaction(write)


MEMBER_FIELDS=('disposition','eligibility','verification_status','exclusion_reason','exclusion_reference',
               'employment_coverage_start','employment_coverage_end','employment_reference',
               'compensation_coverage_end','compensation_reference')


def save_member(cid,eid,token,values,source_token,schedule_exceptions=None):
    cid=positive_integer(cid,'Certification');eid=positive_integer(eid,'Employee',2147483647)
    if set(values)-set(MEMBER_FIELDS):raise ValueError('Unsupported member fields.')
    def write(cursor):
        cursor.execute('SELECT payroll_period_id FROM payroll_cutoff_certifications WHERE certification_id=%s',(cid,))
        identity=cursor.fetchone()
        if not identity:raise ValueError('Certification not found.')
        period=_period(cursor,identity['payroll_period_id']);row=_load(cursor,cid,True);_expected(row,token)
        if row['state']!='ASSEMBLY':raise ValueError('Published certification is immutable.')
        if eid not in row['roster_scope']['employee_ids']:raise ValueError('Employee is outside the declared roster.')
        member={key:values.get(key) or None for key in MEMBER_FIELDS}
        for field,options in [('disposition',('INCLUDE','EXCLUDE')),('eligibility',('UNRESOLVED','FULL_CUTOFF','NOT_ELIGIBLE')),('verification_status',('UNVERIFIED','VERIFIED'))]:
            if member[field] not in options:raise ValueError(f'Select a valid {field.replace("_"," ")}.')
        for field in ('exclusion_reason','exclusion_reference','employment_reference','compensation_reference'):
            if member[field] is not None:member[field]=text(member[field],field.replace('_',' ').capitalize(),255)
        if member['disposition']=='EXCLUDE':
            member['exclusion_reason']=reference(member['exclusion_reason'],'Exclusion reason')
            member['exclusion_reference']=reference(member['exclusion_reference'],'Exclusion reference')
        for field in ('employment_coverage_start','employment_coverage_end','compensation_coverage_end'):
            member[field]=optional_date(member[field],field.replace('_',' ').capitalize())
        start,end=member['employment_coverage_start'],member['employment_coverage_end']
        if start and end and end<start:raise ValueError('Employment coverage ends before it starts.')
        source=_sources(cursor,[eid])['employees'][0];comp=source['compensation']
        if not isinstance(source_token,str) or not hmac.compare_digest(digest(source),source_token):
            raise ValueError('ERP employee/compensation sources changed after the form opened. Reload and review the current snapshot.')
        member.update(certification_id=cid,employee_id=eid,hire_date_snapshot=source['hire_date'],
                      employment_status_snapshot=source['employment_status'],compensation_id=comp['compensation_id'] if comp else None,
                      basic_rate=payroll_money(comp['basic_rate'],'Compensation rate') if comp else None,
                      pay_type=comp['pay_type'] if comp else None,currency_code=comp['currency_code'] if comp else None,
                      compensation_effective_date=comp['effective_date'] if comp else None,
                      schedule_evidence=json.dumps(dict(scheduled_dates=scheduled_dates(period),exceptions=validate_exceptions(period,schedule_exceptions))),
                      material_source_digest=digest(source))
        cursor.execute('DELETE FROM payroll_certification_members WHERE certification_id=%s AND employee_id=%s',(cid,eid))
        cursor.execute('INSERT INTO payroll_certification_members('+','.join(member)+') VALUES('+','.join(['%s']*len(member))+')',tuple(member.values()))
        # Capture current material sources; individual member digests still detect earlier stale saves.
        cursor.execute('UPDATE payroll_cutoff_certifications SET source_digest=%s WHERE certification_id=%s',
                       (digest(_sources(cursor,row['roster_scope']['employee_ids'])),cid))
        return _load(cursor,cid)
    return _transaction(write)


def validate_publication(cursor,row,period,actor_id):
    sources=_sources(cursor,row['roster_scope']['employee_ids'])
    if row['source_digest']!=digest(sources):raise ValueError('ERP employee/compensation sources changed. Re-review the assembly.')
    ids=row['roster_scope']['employee_ids'];members=row['members']
    if sorted(m['employee_id'] for m in members)!=sorted(ids):raise ValueError('Every declared employee requires an explicit disposition.')
    for member in members:
        source=next(s for s in sources['employees'] if s['employee_id']==member['employee_id'])
        if member['material_source_digest']!=digest(source):raise ValueError('Member ERP sources changed. Re-review the employee.')
        if member['verification_status']!='VERIFIED':raise ValueError('Member verification is unresolved.')
        if member['disposition']=='EXCLUDE':
            reference(member['exclusion_reason'],'Exclusion reason');reference(member['exclusion_reference'],'Exclusion reference');continue
        if member['eligibility']!='FULL_CUTOFF' or not member['hire_date_snapshot'] or member['hire_date_snapshot']>period['start_date']:
            raise ValueError('Unknown or mid-cutoff hire eligibility is unsupported.')
        for start,end in [('employment_coverage_start','employment_coverage_end'),('compensation_effective_date','compensation_coverage_end')]:
            if not member[start] or not member[end] or member[start]>period['start_date'] or member[end]<period['end_date']:
                raise ValueError('Employment and compensation evidence must cover the full cutoff.')
        if member['pay_type']!='MONTHLY' or member['currency_code']!='PHP':raise ValueError('Included compensation must be MONTHLY/PHP.')
        payroll_money(member['basic_rate'],'Compensation snapshot')
        reference(member['employment_reference'],'Employment reference');reference(member['compensation_reference'],'Compensation reference')
        if member['schedule_evidence']!=dict(scheduled_dates=scheduled_dates(period),exceptions=[]):raise ValueError('Employee schedule is unsupported or incomplete.')
    calendar=dict(timezone='Asia/Manila',working_week_mask=31,scheduled_dates=scheduled_dates(period),exceptions=[])
    if row['calendar_configuration']!=calendar:raise ValueError('Calendar is unsupported or incomplete.')
    evidence=authoritative_evidence(period,actor_id)
    if evidence is None:raise ValueError(PUBLICATION_BLOCKER)
    # Trusted adapters must supply full expected claims, not simply a permission checkbox.
    expected=dict(roster_ids=sorted(ids),roster_source_reference=row['roster_source_reference'],
                  calendar_source_reference=row['calendar_source_reference'],calendar=calendar,
                  members=[{k:v for k,v in m.items() if k!='certification_id'} for m in members])
    if actor_id not in evidence.get('certifier_ids',()) or evidence.get('claims')!=expected:
        raise ValueError('Authoritative source population, evidence, calendar or certifier authority does not match this revision.')
    return digest(dict(period={key:period[key] for key in ('payroll_period_id','policy_version_id','cutoff_code','start_date','end_date')},
                       header={k:v for k,v in row.items() if k not in ('members','events','certification_digest','state','certified_by','certified_at')},
                       members=members))


def publish(cid,token,actor_id):
    cid=positive_integer(cid,'Certification');actor_id=positive_integer(actor_id,'Acting user',2147483647)
    def write(cursor):
        cursor.execute('SELECT payroll_period_id FROM payroll_cutoff_certifications WHERE certification_id=%s',(cid,))
        identity=cursor.fetchone()
        if not identity:raise ValueError('Certification not found.')
        period=_period(cursor,identity['payroll_period_id']);row=_load(cursor,cid,True);_expected(row,token)
        if row['state']!='ASSEMBLY':raise ValueError('Certification is already published.')
        cursor.execute('SELECT certification_id FROM payroll_cutoff_certifications WHERE payroll_period_id=%s ORDER BY revision DESC LIMIT 1 FOR UPDATE',(period['payroll_period_id'],))
        if cursor.fetchone()['certification_id']!=cid:raise ValueError('Only the latest revision may be published.')
        sealed=validate_publication(cursor,row,period,actor_id)
        cursor.execute("UPDATE payroll_cutoff_certifications SET state='SEALED',certified_by=%s,certified_at=%s,certification_digest=%s WHERE certification_id=%s AND state='ASSEMBLY'",
                       (actor_id,datetime.now(timezone.utc).replace(tzinfo=None),sealed,cid))
        if cursor.rowcount!=1:raise ValueError('Publication changed concurrently.')
        return _load(cursor,cid)
    return _transaction(write)


def revoke(cid,token,actor_id,reason,supporting_reference):
    cid=positive_integer(cid,'Certification');actor_id=positive_integer(actor_id,'Acting user',2147483647)
    reason=reference(reason,'Revocation reason');supporting_reference=reference(supporting_reference,'Revocation reference')
    def write(cursor):
        cursor.execute('SELECT payroll_period_id FROM payroll_cutoff_certifications WHERE certification_id=%s',(cid,))
        identity=cursor.fetchone()
        if not identity:raise ValueError('Certification not found.')
        _period(cursor,identity['payroll_period_id'],False);row=_load(cursor,cid,True);_expected(row,token)
        if row['state']!='SEALED' or any(e['event_type'] in ('REVOKE','INVALIDATE','SUPERSEDE') for e in row['events']):
            raise ValueError('Certification is not currently revocable. No older revision was reactivated.')
        cursor.execute("INSERT INTO payroll_certification_events(certification_id,event_type,actor_id,occurred_at,reason,supporting_reference) VALUES(%s,'REVOKE',%s,%s,%s,%s)",
                       (cid,actor_id,datetime.now(timezone.utc).replace(tzinfo=None),reason,supporting_reference))
        return _load(cursor,cid)
    return _transaction(write)


def get_certification(cid):
    cid=positive_integer(cid,'Certification')
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:return _load(cursor,cid)
    finally:cursor.close();connection.close()


def get_employee_source(eid):
    eid=positive_integer(eid,'Employee',2147483647)
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:return _sources(cursor,[eid],False)['employees'][0]
    finally:cursor.close();connection.close()


def review(cid):
    cid=positive_integer(cid,'Certification')
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:
        row=_load(cursor,cid)
        sources=_sources(cursor,row['roster_scope']['employee_ids'],False)
        row['source_stale']=row['source_digest']!=digest(sources) or any(
            m['material_source_digest']!=digest(next(s for s in sources['employees'] if s['employee_id']==m['employee_id'])) for m in row['members'])
        return row
    finally:cursor.close();connection.close()


def update_scope(cid,token,ids,roster_reference,calendar_reference,correction_reason=None,correction_reference=None,calendar_exceptions=None):
    cid=positive_integer(cid,'Certification')
    def write(cursor):
        cursor.execute('SELECT payroll_period_id FROM payroll_cutoff_certifications WHERE certification_id=%s',(cid,))
        identity=cursor.fetchone()
        if not identity:raise ValueError('Certification not found.')
        period=_period(cursor,identity['payroll_period_id']);row=_load(cursor,cid,True);_expected(row,token)
        if row['state']!='ASSEMBLY':raise ValueError('Published certification is immutable.')
        header=_header(cursor,period,ids,roster_reference,calendar_reference,calendar_exceptions)
        if row['predecessor_certification_id'] is not None:
            cursor.execute('UPDATE payroll_cutoff_certifications SET correction_reason=%s,correction_reference=%s WHERE certification_id=%s',
                (reference(correction_reason,'Correction reason'),reference(correction_reference,'Correction reference'),cid))
        for member in row['members']:
            if member['employee_id'] not in header['roster_scope']['employee_ids']:
                cursor.execute('DELETE FROM payroll_certification_members WHERE certification_id=%s AND employee_id=%s',(cid,member['employee_id']))
        cursor.execute('UPDATE payroll_cutoff_certifications SET roster_scope=%s,roster_source_reference=%s,calendar_source_reference=%s,calendar_configuration=%s,source_digest=%s,configuration_digest=%s WHERE certification_id=%s',
            (json.dumps(header['roster_scope']),header['roster_source_reference'],header['calendar_source_reference'],json.dumps(header['calendar_configuration']),header['source_digest'],digest(header['calendar_configuration']),cid))
        return _load(cursor,cid)
    return _transaction(write)


def list_certifications(period_id):
    period_id=positive_integer(period_id,'Payroll period',2147483647)
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:
        cursor.execute('SELECT * FROM payroll_cutoff_certifications WHERE payroll_period_id=%s ORDER BY revision DESC',(period_id,))
        return [_decode(row) for row in cursor.fetchall()]
    finally:cursor.close();connection.close()


def current_certification(period_id):
    """Review only: latest SEALED, including revoked/stale. Never fall back."""
    latest=next((r for r in list_certifications(period_id) if r['state']=='SEALED'),None)
    if latest is None:return None
    row=review(latest['certification_id'])
    row['terminal_events']=[e['event_type'] for e in row['events'] if e['event_type'] in ('REVOKE','INVALIDATE','SUPERSEDE')]
    row['source_consistent']=not row['source_stale'] and not row['terminal_events']
    return row
