"""Bounded v2 wire contract. No salary engine and no implicit version upgrade."""
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from payroll_validation import payroll_money

ROUNDING_CONTRACT = 'POLICY_HALF_UP_2_V1'
MONEY_FIELDS = ('daily_rate','regular_pay','additional_earnings','gross_pay',
                'attendance_deduction','total_deductions','net_pay')
COUNT_FIELDS = ('scheduled_work_days','present_days','late_days','absent_days',
                'paid_leave_days','unpaid_leave_days','half_day_count','unrecorded_days')


def obj(**fields):
    return fields


MEMBER = obj(employee_id='id',disposition=('INCLUDE','EXCLUDE'),
    eligibility=('UNRESOLVED','FULL_CUTOFF','NOT_ELIGIBLE'),verification_status=('VERIFIED',),
    exclusion_reason='?text',exclusion_reference='?text',hire_date_snapshot='?date',
    employment_status_snapshot='?text',employment_coverage_start='?date',
    employment_coverage_end='?date',employment_reference='?text',compensation_id='?id',
    basic_rate='?positive_money',pay_type=('MONTHLY','DAILY','HOURLY',None),currency_code='?text',
    compensation_effective_date='?date',compensation_coverage_end='?date',
    compensation_reference='?text',material_source_digest='hash',
    schedule_evidence=obj(scheduled_dates=['date'],exceptions=[]))
CALENDAR = obj(timezone=('Asia/Manila',),working_week_mask=(31,),scheduled_dates=['date'],exceptions=[])
SCHEMA = obj(format_version=(2,),inputs=obj(
    period=obj(payroll_period_id='id',start_date='date',end_date='date',cutoff_code=('A','B')),
    policy=obj(policy_version_id='id',version_number='id',configuration_hash='hash',
               calculator_key=('MONTHLY_SEMIMONTHLY_V1',),calendar_key=('SEMI_MONTHLY_1_15_16_EOM_V1',)),
    certification=obj(certification_id='id',revision='id',certification_digest='hash',
        certified_by='id',certified_at='timestamp',roster_source_reference='text',
        calendar_source_reference='text',source_digest='hash',configuration_digest='hash'),
    roster=[MEMBER],calendar=CALENDAR,
    entry=obj(payroll_entry_id='id',employee_id='id',compensation_id='id',
              basic_rate='positive_money',pay_type=('MONTHLY',),currency_code=('PHP',)),
    attendance=[obj(attendance_id='id',attendance_date='date',status=('PRESENT','LATE','ABSENT','ON_LEAVE','HALF_DAY'))],
    leaves=[obj(leave_request_id='id',start_date='date',end_date='date',leave_type_id='id',
                is_paid=(0,1),total_days='positive_money')],
    daily=[obj(date='date',classification=('PRESENT','LATE','ABSENT','HALF_DAY','PAID_LEAVE','UNPAID_LEAVE'),
               attendance_id='id',leave_request_id='?id')],
    adjustments=[obj(adjustment_id='id',adjustment_type=('EARNING','DEDUCTION'),amount='positive_money')],
    rounding_contract=(ROUNDING_CONTRACT,)),
    outputs={**{k:'money' for k in MONEY_FIELDS},**{k:'count' for k in COUNT_FIELDS}})


def _normalize(value, spec):
    if isinstance(spec,dict):
        if not isinstance(value,dict) or set(value)!=set(spec):
            raise ValueError('Payroll evidence has missing or unsupported fields.')
        return {k:_normalize(value[k],s) for k,s in spec.items()}
    if isinstance(spec,list):
        if not isinstance(value,list) or len(value)>100000 or (not spec and value):
            raise ValueError('Unsupported payroll evidence collection.')
        return [_normalize(v,spec[0]) for v in value]
    if isinstance(spec,tuple):
        if not any(type(v) is type(value) and v==value for v in spec):
            raise ValueError('Unsupported payroll evidence value.')
        return value
    if spec.startswith('?'):
        return None if value is None else _normalize(value,spec[1:])
    if spec in ('money','positive_money'):
        amount=payroll_money(value,'Evidence amount',allow_zero=spec=='money')
        return '0.00' if amount==0 else format(amount,'.2f')
    if spec in ('id','count'):
        if type(value) is not int or not (0 if spec=='count' else 1)<=value<=18446744073709551615:
            raise ValueError('Invalid payroll evidence integer.')
        return value
    if spec=='date':
        if type(value) is date:value=value.isoformat()
        if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):
            raise ValueError('Invalid payroll evidence date.')
        try:parsed=date.fromisoformat(value)
        except ValueError:raise ValueError('Invalid payroll evidence date.') from None
        if parsed.year<1000:raise ValueError('Unsupported payroll evidence date.')
        return value
    if spec=='timestamp':
        # Certification DATETIME(6) is explicitly written as naive UTC by its repository.
        if isinstance(value,datetime):
            if value.tzinfo is None:value=value.replace(tzinfo=timezone.utc)
            value=value.astimezone(ZoneInfo('Asia/Manila')).isoformat(timespec='microseconds')
        if not isinstance(value,str):raise ValueError('Invalid payroll evidence timestamp.')
        try:parsed=datetime.fromisoformat(value)
        except ValueError:raise ValueError('Invalid payroll evidence timestamp.') from None
        if parsed.tzinfo is None or parsed.utcoffset()!=ZoneInfo('Asia/Manila').utcoffset(parsed):
            raise ValueError('Evidence timestamps require explicit Asia/Manila offset.')
        return parsed.astimezone(ZoneInfo('Asia/Manila')).isoformat(timespec='microseconds')
    if not isinstance(value,str) or not value or len(value)>255:
        raise ValueError('Invalid payroll evidence text.')
    if spec=='hash' and not re.fullmatch('[0-9a-f]{64}',value):
        raise ValueError('Invalid payroll evidence digest.')
    return value


def canonical_evidence(payload):
    value=_normalize(payload,SCHEMA)
    inputs=value['inputs']
    for key,order in (('roster',lambda r:r['employee_id']),
                      ('attendance',lambda r:(r['attendance_date'],r['attendance_id'])),
                      ('leaves',lambda r:r['leave_request_id']),
                      ('daily',lambda r:r['date']),('adjustments',lambda r:r['adjustment_id'])):
        rows=inputs[key]; keys=[order(r) for r in rows]
        if len(keys)!=len(set(keys)):raise ValueError('Duplicate payroll evidence records.')
        rows.sort(key=order)
    for calendar in [inputs['calendar']]+[m['schedule_evidence'] for m in inputs['roster']]:
        dates=calendar['scheduled_dates']
        if len(dates)!=len(set(dates)):raise ValueError('Duplicate scheduled dates.')
        dates.sort()
    encoded=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)
    if len(encoded.encode())>900000:raise ValueError('Payroll evidence exceeds the supported size.')
    return encoded


def evidence_digest(payload):
    return hashlib.sha256(canonical_evidence(payload).encode('utf-8')).hexdigest()


def fingerprint_for_version(cursor,period_id,entry_id,version):
    """Explicit infrastructure dispatch; existing workflow intentionally remains v1-only."""
    if type(version) is not int:raise ValueError('Unsupported payroll evidence version.')
    if version==1:
        from payroll_freshness import fingerprint
        return fingerprint(cursor,period_id,entry_id)
    if version==2:
        from payroll_evidence_repository import verify_current
        return verify_current(cursor,period_id,entry_id)['evidence_digest']
    raise ValueError('Unsupported payroll evidence version.')
