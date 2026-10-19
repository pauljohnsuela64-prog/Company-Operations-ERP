"""Transactional v2 foundation, deliberately unused by production payroll workflows.

Cursor interfaces require the coordination guard FIRST in the caller's transaction.
No HTTP endpoint, salary calculator, permission bypass, or finalization is provided.
"""
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal

from database import get_connection
import payroll_certification_repository as certifications
from payroll_freshness import lock_payroll_inputs, raise_payroll_lock_error
from payroll_generation_repository import month_cutoffs, _resolve
from payroll_policy_repository import _decode
from payroll_policy_validation import positive_integer
from payroll_validation import validate_evidence_money
from payroll_evidence import (MEMBER, MONEY_FIELDS, COUNT_FIELDS, ROUNDING_CONTRACT,
                              canonical_evidence, evidence_digest)


def _project(row,fields):
    return {key:row[key] for key in fields}


def validate_eligibility(cursor,period_id,*,require_entries=True):
    """Authoritative current-read gate, not an authorization or salary calculation.

    Call inside an active transaction before taking other locks. For generation,
    require_entries=False validates certification/sources before entries exist.
    All other future stages must require the exact included entry population.
    """
    period_id=positive_integer(period_id,'Payroll period',2147483647)
    lock_payroll_inputs(cursor)
    cursor.execute('SELECT * FROM payroll_periods WHERE payroll_period_id=%s FOR UPDATE',(period_id,))
    period=cursor.fetchone()
    if not period or not period['policy_version_id'] or period['cutoff_code'] not in ('A','B'):
        raise ValueError('Version-2 evidence requires a policy-pinned cutoff.')
    if period['status']=='CANCELLED':raise ValueError('Cancelled payroll is not eligible for calculation evidence.')
    cutoff=next(c for c in month_cutoffs(period['start_date'].year,period['start_date'].month)
                if c['cutoff_code']==period['cutoff_code'])
    if any(period[k]!=cutoff[k] for k in ('start_date','end_date')):
        raise ValueError('Period does not match exact supported cutoff dates.')
    resolved=_resolve(cursor,[cutoff])[0]
    if resolved['policy_version_id']!=period['policy_version_id']:
        raise ValueError('Pinned policy is not the original activated cutoff policy.')
    cursor.execute('SELECT * FROM payroll_policy_versions WHERE policy_version_id=%s FOR UPDATE',(period['policy_version_id'],))
    policy=_decode(cursor.fetchone())
    cursor.execute("SELECT certification_id FROM payroll_cutoff_certifications WHERE payroll_period_id=%s AND state='SEALED' ORDER BY revision DESC LIMIT 1 FOR UPDATE",(period_id,))
    latest=cursor.fetchone()
    if not latest:raise ValueError('A sealed certification is required.')
    cert=certifications._load(cursor,latest['certification_id'],True)
    if any(e['event_type'] in ('REVOKE','INVALIDATE','SUPERSEDE') for e in cert['events']):
        raise ValueError('Latest sealed certification is withdrawn. No older revision may be used.')
    if any(cert[k]!=period[k] for k in ('payroll_period_id','policy_version_id','cutoff_code','start_date','end_date')):
        raise ValueError('Certification does not match the pinned cutoff.')
    if cert['configuration_digest']!=certifications.digest(cert['calendar_configuration']):
        raise ValueError('Certification calendar digest does not match.')
    # Verify original certifier authority, NOT authority of a future payer/caller.
    expected=certifications.validate_publication(cursor,cert,period,cert['certified_by'])
    if not cert['certification_digest'] or not hmac.compare_digest(expected,cert['certification_digest']):
        raise ValueError('Certification seal does not match. Authorized review is required.')
    cursor.execute('SELECT * FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id FOR UPDATE',(period_id,))
    entries=cursor.fetchall()
    included={m['employee_id']:m for m in cert['members'] if m['disposition']=='INCLUDE'}
    if require_entries and (not included or sorted(e['employee_id'] for e in entries)!=sorted(included)):
        raise ValueError('Payroll entries do not match the complete included certified roster.')
    for entry in entries:
        member=included.get(entry['employee_id'])
        if member is None or any(entry[k]!=member[k] for k in ('compensation_id','basic_rate','pay_type','currency_code')):
            raise ValueError('Payroll compensation snapshot or roster disagrees with certification.')
    return dict(period=period,policy=policy,certification=cert,entries=entries)


def _daily(period,policy,attendance,leaves):
    dates=certifications.scheduled_dates(period)
    by_date={r['attendance_date'].isoformat():r for r in attendance}
    if len(by_date)!=len(attendance):raise ValueError('Attendance contains duplicate dates.')
    for leave in leaves:
        if leave['start_date']>leave['end_date'] or leave['total_days']<=0 or leave['total_days']%1:
            raise ValueError('Leave duration is invalid or partial-day evidence is unsupported.')
    daily=[]
    for day in dates:
        row=by_date.get(day)
        matches=[r for r in leaves if r['start_date'].isoformat()<=day<=r['end_date'].isoformat()]
        if not row:raise ValueError('Attendance evidence is incomplete for the cutoff.')
        if len(matches)>1 or (matches and row['status']!='ON_LEAVE') or (row['status']=='ON_LEAVE' and not matches):
            raise ValueError('Attendance and approved leave conflict or are ambiguous.')
        classification=row['status'];leave=matches[0] if matches else None
        if leave:classification='PAID_LEAVE' if leave['is_paid'] else 'UNPAID_LEAVE'
        rules={
            'LATE':policy['attendance_rules']['late_treatment'],
            'ABSENT':policy['attendance_rules']['absence_treatment'],
            'HALF_DAY':policy['attendance_rules']['half_day_treatment'],
            'PAID_LEAVE':policy['leave_rules']['paid_leave_treatment'],
            'UNPAID_LEAVE':policy['leave_rules']['unpaid_leave_treatment']}
        if classification not in ('PRESENT',*rules):raise ValueError('Unsupported attendance classification.')
        if rules.get(classification)=='BLOCK':raise ValueError('Policy blocks a recorded daily classification.')
        daily.append(dict(date=day,classification=classification,attendance_id=row['attendance_id'],
                          leave_request_id=leave['leave_request_id'] if leave else None))
    return daily


def build_evidence(cursor,context,entry_id,outputs):
    """Bind explicitly proposed outputs to current sources; never computes salary.

    Context must come from validate_eligibility in this same guarded transaction.
    This private-service boundary is not safe to expose as an arbitrary form API.
    """
    entry=next((e for e in context['entries'] if e['payroll_entry_id']==entry_id),None)
    if not entry:raise ValueError('Entry does not belong to the certified period.')
    period=context['period'];policy=context['policy'];cert=context['certification']
    cursor.execute('''SELECT attendance_id,attendance_date,status FROM attendance_records
        WHERE employee_id=%s AND attendance_date BETWEEN %s AND %s
        ORDER BY attendance_date,attendance_id FOR UPDATE''',
        (entry['employee_id'],period['start_date'],period['end_date']))
    attendance=cursor.fetchall()
    cursor.execute('''SELECT lr.leave_request_id,lr.start_date,lr.end_date,lr.leave_type_id,lt.is_paid,lr.total_days
        FROM leave_requests lr JOIN leave_types lt ON lt.leave_type_id=lr.leave_type_id
        WHERE lr.employee_id=%s AND lr.status='APPROVED' AND lr.start_date<=%s AND lr.end_date>=%s
        ORDER BY lr.leave_request_id FOR UPDATE''',(entry['employee_id'],period['end_date'],period['start_date']))
    leaves=cursor.fetchall()
    cursor.execute('''SELECT adjustment_id,adjustment_type,amount FROM payroll_adjustments
        WHERE payroll_entry_id=%s ORDER BY adjustment_id FOR UPDATE''',(entry_id,))
    adjustments=cursor.fetchall()
    daily=_daily(period,policy,attendance,leaves)
    if not isinstance(outputs,dict) or set(outputs)!=set(MONEY_FIELDS+COUNT_FIELDS):
        raise ValueError('Proposed calculation outputs are incomplete or unsupported.')
    # Normalize before arithmetic so floats and nonfinite values never enter it.
    payload=dict(format_version=2,inputs=dict(
        period=_project(period,('payroll_period_id','start_date','end_date','cutoff_code')),
        policy=_project(policy,('policy_version_id','version_number','configuration_hash','calculator_key','calendar_key')),
        certification=_project(cert,('certification_id','revision','certification_digest','certified_by','certified_at',
                                    'roster_source_reference','calendar_source_reference','source_digest','configuration_digest')),
        roster=[_project(m,MEMBER) for m in cert['members']],calendar=cert['calendar_configuration'],
        entry=_project(entry,('payroll_entry_id','employee_id','compensation_id','basic_rate','pay_type','currency_code')),
        attendance=attendance,leaves=leaves,daily=daily,adjustments=adjustments,
        rounding_contract=ROUNDING_CONTRACT),outputs=outputs)
    normalized=json.loads(canonical_evidence(payload))
    money={k:Decimal(normalized['outputs'][k]) for k in MONEY_FIELDS}
    validate_evidence_money(dict(entry,**money),adjustments)
    counts=dict(scheduled_work_days=len(daily),unrecorded_days=0)
    for field,kind in zip(COUNT_FIELDS[1:-1],('PRESENT','LATE','ABSENT','PAID_LEAVE','UNPAID_LEAVE','HALF_DAY')):
        counts[field]=sum(d['classification']==kind for d in daily)
    if any(outputs[k]!=v for k,v in counts.items()):raise ValueError('Calculation day counts disagree with source evidence.')
    earnings=sum((r['amount'] for r in adjustments if r['adjustment_type']=='EARNING'),Decimal('0'))
    deductions=sum((r['amount'] for r in adjustments if r['adjustment_type']=='DEDUCTION'),Decimal('0'))
    if (money['additional_earnings']!=earnings or money['gross_pay']!=money['regular_pay']+earnings
            or money['total_deductions']!=money['attendance_deduction']+deductions):
        raise ValueError('Calculation output totals disagree with adjustment evidence.')
    # No salary/net-pay formula is introduced here. Future approved engine owns it.
    return normalized


def persist_proposed(period_id,entry_id,outputs,actor_id):
    """Foundation only: no production caller; tests supply synthetic outputs/sources.

    Future calculator must invoke equivalent work within its existing authorized
    transaction, not accept these outputs directly from an HTTP request.
    """
    actor_id=positive_integer(actor_id,'Acting user',2147483647)
    entry_id=positive_integer(entry_id,'Payroll entry',2147483647)
    connection=get_connection();cursor=connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        context=validate_eligibility(cursor,period_id)
        if context['period']['status']!='DRAFT':raise ValueError('Evidence can only be written for Draft payroll.')
        entry=next((e for e in context['entries'] if e['payroll_entry_id']==entry_id),None)
        if not entry or entry['status'] not in ('DRAFT','CALCULATED'):raise ValueError('Entry is not editable Draft payroll.')
        payload=build_evidence(cursor,context,entry_id,outputs)
        encoded=canonical_evidence(payload);digest=evidence_digest(payload)
        cursor.execute('SELECT calculation_sequence FROM payroll_calculation_evidence WHERE payroll_entry_id=%s ORDER BY calculation_sequence DESC LIMIT 1 FOR UPDATE',(entry_id,))
        previous=cursor.fetchone();sequence=previous['calculation_sequence']+1 if previous else 1
        stamp=datetime.now(timezone.utc).replace(tzinfo=None)
        cursor.execute('''INSERT INTO payroll_calculation_evidence
            (evidence_version,payroll_period_id,payroll_entry_id,employee_id,certification_id,
             calculation_sequence,canonical_evidence,rounding_contract,evidence_digest,calculated_by,calculated_at)
            VALUES(2,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (period_id,entry_id,entry['employee_id'],context['certification']['certification_id'],sequence,
             encoded,ROUNDING_CONTRACT,digest,actor_id,stamp))
        evidence_id=cursor.lastrowid
        fields=MONEY_FIELDS+COUNT_FIELDS
        cursor.execute('UPDATE payroll_entries SET '+','.join(k+'=%s' for k in fields)+''',
            calculation_input_version=2,calculation_input_hash=%s,current_calculation_evidence_id=%s,
            status='CALCULATED',calculated_by=%s,calculated_at=%s WHERE payroll_entry_id=%s''',
            tuple(payload['outputs'][k] for k in fields)+(digest,evidence_id,actor_id,stamp,entry_id))
        if cursor.rowcount!=1:raise ValueError('Evidence association failed. No calculation was saved.')
        connection.commit();return evidence_id
    except Exception as error:
        connection.rollback();raise_payroll_lock_error(error);raise
    finally:cursor.close();connection.close()


def verify_current(cursor,period_id,entry_id):
    context=validate_eligibility(cursor,period_id)
    entry=next((e for e in context['entries'] if e['payroll_entry_id']==entry_id),None)
    if not entry or entry['calculation_input_version']!=2 or not entry['current_calculation_evidence_id']:
        raise ValueError('Current version-2 calculation evidence is missing.')
    cursor.execute('SELECT * FROM payroll_calculation_evidence WHERE calculation_evidence_id=%s FOR UPDATE',
                   (entry['current_calculation_evidence_id'],))
    evidence=cursor.fetchone()
    if not evidence or any(evidence[k]!=entry[k] for k in ('payroll_period_id','payroll_entry_id','employee_id')):
        raise ValueError('Calculation evidence ownership does not match.')
    if evidence['evidence_version']!=2 or evidence['rounding_contract']!=ROUNDING_CONTRACT:
        raise ValueError('Unsupported calculation evidence contract.')
    stored=evidence['canonical_evidence']
    if isinstance(stored,(str,bytes)):stored=json.loads(stored)
    digest=evidence_digest(stored)
    if (not hmac.compare_digest(digest,evidence['evidence_digest'])
            or not hmac.compare_digest(digest,entry['calculation_input_hash'])):
        raise ValueError('Stored calculation evidence digest does not match.')
    current=build_evidence(cursor,context,entry_id,_project(entry,MONEY_FIELDS+COUNT_FIELDS))
    if (evidence['certification_id']!=context['certification']['certification_id']
            or not hmac.compare_digest(digest,evidence_digest(current))):
        raise ValueError('Calculation evidence sources or saved outputs changed. Recalculation requires authorized review.')
    return evidence
