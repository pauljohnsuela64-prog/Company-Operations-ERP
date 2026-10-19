"""TEST HARNESS ONLY. Never import from application routes or workers.

No authority monkeypatch exists here. The isolated smoke process supplies captured
synthetic authority claims to the unchanged real validator using unittest.mock.
This module has no configured connection factory, CLI, environment enable flag,
audit writer, scheduler or real-data entry point.
"""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import payroll_evidence_repository as evidence
from payroll_freshness import lock_payroll_inputs, raise_payroll_lock_error
import payroll_monthly_prototype as prototype


@dataclass(frozen=True)
class DisposableFixture:
    datadir: Path
    database_name: str
    actor_id: int
    employee_inputs: tuple[tuple[int, prototype.CalculationInput], ...]
    expected_entries: tuple


def entry_markers(entries):
    return tuple((r['payroll_entry_id'],r['status'],r['calculation_input_version'],
                  r['calculation_input_hash'],r['current_calculation_evidence_id']) for r in entries)


def _isolation(cursor,fixture):
    if type(fixture) is not DisposableFixture or fixture.database_name!='erp_synthetic_payroll_period':
        raise ValueError('An explicit disposable synthetic fixture is required.')
    expected=fixture.datadir.resolve()
    if (not expected.is_dir() or expected.name!='data'
            or not expected.parent.name.startswith('erp_audit_smoke_')
            or cursor._connection.server_host not in ('127.0.0.1','localhost')):
        raise ValueError('Expected the isolated smoke launcher temporary datadir.')
    cursor.execute('SELECT @@datadir datadir,DATABASE() db')
    actual=cursor.fetchone()
    if Path(actual['datadir']).resolve()!=expected or actual['db']!=fixture.database_name:
        raise ValueError('Disposable database isolation check failed. No payroll was touched.')


def _policy(policy):
    # Explicit bounded translation for synthetic fixtures only. This does not
    # approve the production policy vocabulary or promote the prototype engine.
    required={
        'attendance_rules':dict(missing_evidence='BLOCK',late_treatment='NO_DEDUCTION',
            absence_treatment='PERIOD_WORKDAY_DIVISOR',half_day_treatment='HALF_DAY_DEDUCTION'),
        'leave_rules':dict(paid_leave_treatment='NO_DEDUCTION',unpaid_leave_treatment='PERIOD_WORKDAY_DIVISOR',conflict='BLOCK'),
        'eligibility_rules':dict(proration='BLOCK',full_cutoff_eligibility='VERIFIED_FULL_CUTOFF_ONLY'),
        'deduction_rules':dict(excess_deductions='BLOCK',statutory='BLOCK',odd_cent_handling='BLOCK')}
    if any(policy[k]!=v for k,v in required.items()):
        raise ValueError('Synthetic policy does not match the explicit hypothetical calculator fixture.')


def _bind(inputs,entry,context,payload):
    member=next(m for m in context['certification']['members'] if m['employee_id']==entry['employee_id'])
    eligible=inputs.eligibility;period=context['period']
    if (inputs.monthly_salary!=entry['basic_rate'] or inputs.cutoff.code!=period['cutoff_code']
            or inputs.cutoff.start_date!=period['start_date'] or inputs.cutoff.end_date!=period['end_date']):
        raise ValueError('Synthetic salary/cutoff does not match the locked entry.')
    for name,snapshot in (
            ('hire_date','hire_date_snapshot'),('employment_coverage_start','employment_coverage_start'),
            ('employment_coverage_end','employment_coverage_end'),('employment_reference','employment_reference'),
            ('compensation_coverage_start','compensation_effective_date'),('compensation_coverage_end','compensation_coverage_end'),
            ('compensation_reference','compensation_reference'),('pay_type','pay_type'),('currency_code','currency_code')):
        if getattr(eligible,name)!=member[snapshot]:raise ValueError('Synthetic eligibility disagrees with certified evidence.')
    actual=payload['inputs']
    if sorted((r.date.isoformat(),r.status) for r in inputs.attendance)!=sorted(
            (r['attendance_date'],r['status']) for r in actual['attendance']):
        raise ValueError('Synthetic attendance does not match locked source records.')
    leave_days=sorted((r.date.isoformat(),'PAID_LEAVE' if r.is_paid else 'UNPAID_LEAVE') for r in inputs.approved_leave)
    if leave_days!=sorted((r['date'],r['classification']) for r in actual['daily'] if r['leave_request_id'] is not None):
        raise ValueError('Synthetic leave does not match locked approved leave.')
    if sorted((r.kind,r.amount) for r in inputs.adjustments)!=sorted(
            (r['adjustment_type'],Decimal(r['amount'])) for r in actual['adjustments']):
        raise ValueError('Synthetic adjustments do not match locked source records.')


def calculate_period(connect,period_id,fixture):
    """One disposable period, one transaction, no production success audit.

    A stale entry-marker fixture is rejected rather than creating duplicate
    evidence for a repeated/competing request. To deliberately recalculate, the
    smoke test supplies freshly reviewed markers. Uncertain commits require
    explicit inspection; this is not durable request idempotency.
    """
    connection=connect();cursor=connection.cursor(dictionary=True)
    try:
        # Metadata isolation read only; end that transaction before business locks.
        _isolation(cursor,fixture);connection.rollback()
        connection.start_transaction();lock_payroll_inputs(cursor)
        context=evidence.validate_eligibility(cursor,period_id)
        if context['period']['status']!='DRAFT':raise ValueError('Synthetic calculation requires Draft payroll.')
        if entry_markers(context['entries'])!=fixture.expected_entries:
            raise ValueError('Synthetic period changed; review new entry markers before recalculating.')
        _policy(context['policy'])
        if type(fixture.employee_inputs) is not tuple:raise ValueError('Explicit immutable synthetic inputs are required.')
        inputs=dict(fixture.employee_inputs)
        if len(inputs)!=len(fixture.employee_inputs) or sorted(inputs)!=sorted(e['employee_id'] for e in context['entries']):
            raise ValueError('Synthetic inputs must cover the exact certified included roster.')
        evidence.invalidate_period_in_transaction(cursor,period_id)
        saved=[]
        for entry in context['entries']:
            proposed=inputs[entry['employee_id']]
            result=prototype.calculate(proposed)
            outputs=result.as_evidence_outputs()
            payload=evidence.build_evidence(cursor,context,entry['payroll_entry_id'],outputs)
            _bind(proposed,entry,context,payload)
            saved.append(evidence.persist_proposed_in_transaction(cursor,period_id,entry['payroll_entry_id'],outputs,fixture.actor_id))
        connection.commit()
        return tuple(saved)
    except Exception as error:
        connection.rollback();raise_payroll_lock_error(error);raise
    finally:cursor.close();connection.close()
