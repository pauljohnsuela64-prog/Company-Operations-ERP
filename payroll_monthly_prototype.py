"""Development-only hypothetical mathematics. Never use for real payroll.

Pure inputs/outputs: no database, application, repository, policy lookup, clock,
evidence persistence, or import-time runner. Synthetic assertions are NOT HR
certification or approval of a company/statutory payroll policy.
"""
from calendar import monthrange
from dataclasses import dataclass, fields
from datetime import date, timedelta
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_UP, localcontext

from payroll_validation import payroll_money


class PrototypeValidationError(ValueError):
    """Invalid or incomplete synthetic input; no salary result is returned."""


class UnsupportedPolicyError(PrototypeValidationError):
    """Scenario needs a policy decision outside this hypothetical contract."""


@dataclass(frozen=True, slots=True)
class HypotheticalPolicy:
    """Every field is explicit; other policy shapes/values are unsupported."""
    scenario: str
    development_only: bool
    frequency: str
    calculator_key: str
    calendar_key: str
    pay_type: str
    currency_code: str
    working_week_mask: int
    cutoff_a_start: int
    cutoff_a_end: int
    cutoff_b_start: int
    cutoff_b_end: str
    full_cutoff_divisor: int
    rounding_mode: str
    rounding_scale: int
    late_treatment: str
    absence_treatment: str
    half_day_treatment: str
    paid_leave_treatment: str
    unpaid_leave_treatment: str
    missing_evidence: str
    proration: str
    calendar_exceptions: str
    odd_cent_handling: str
    excess_deductions: str


# Validation vocabulary only. Callers still must supply a policy explicitly.
_POLICY_VALUES = dict(
    scenario='HYPOTHETICAL_MONTHLY_V1', development_only=True, frequency='SEMI_MONTHLY',
    calculator_key='HYPOTHETICAL_MONTHLY_PROTOTYPE_V1', calendar_key='SEMI_MONTHLY_1_15_16_EOM_V1',
    pay_type='MONTHLY', currency_code='PHP', working_week_mask=31,
    cutoff_a_start=1, cutoff_a_end=15, cutoff_b_start=16, cutoff_b_end='MONTH_END',
    full_cutoff_divisor=2, rounding_mode='ROUND_HALF_UP', rounding_scale=2,
    late_treatment='NO_DEDUCTION', absence_treatment='PERIOD_WORKDAY_DIVISOR',
    half_day_treatment='HALF_DAY_DEDUCTION', paid_leave_treatment='NO_DEDUCTION',
    unpaid_leave_treatment='PERIOD_WORKDAY_DIVISOR', missing_evidence='BLOCK',
    proration='BLOCK', calendar_exceptions='BLOCK', odd_cent_handling='BLOCK', excess_deductions='BLOCK')


@dataclass(frozen=True, slots=True)
class Cutoff:
    code: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class SyntheticEligibility:
    fixture_reference: str
    development_only: bool
    eligibility: str
    cutoff: Cutoff
    hire_date: date | None
    employment_coverage_start: date | None
    employment_coverage_end: date | None
    compensation_coverage_start: date | None
    compensation_coverage_end: date | None
    employment_reference: str
    compensation_reference: str
    pay_type: str
    currency_code: str
    scheduled_dates: tuple[date, ...]
    calendar_exceptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttendanceDay:
    date: date
    status: str


@dataclass(frozen=True, slots=True)
class ApprovedLeaveDay:
    date: date
    is_paid: bool
    approved: bool
    fixture_reference: str


@dataclass(frozen=True, slots=True)
class SyntheticAdjustment:
    kind: str
    amount: Decimal
    approved: bool
    fixture_reference: str


@dataclass(frozen=True, slots=True)
class CalculationInput:
    policy: HypotheticalPolicy
    cutoff: Cutoff
    eligibility: SyntheticEligibility
    monthly_salary: Decimal
    attendance: tuple[AttendanceDay, ...]
    approved_leave: tuple[ApprovedLeaveDay, ...]
    adjustments: tuple[SyntheticAdjustment, ...]


@dataclass(frozen=True, slots=True)
class DailyExplanation:
    date: date
    attendance_status: str
    classification: str
    deductible_units: Decimal
    leave_reference: str | None


@dataclass(frozen=True, slots=True)
class CalculationStep:
    item: str
    expression: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class CalculationResult:
    scenario: str
    cutoff: Cutoff
    monthly_salary: Decimal
    scheduled_dates: tuple[date, ...]
    daily: tuple[DailyExplanation, ...]
    adjustments: tuple[SyntheticAdjustment, ...]
    regular_pay: Decimal
    daily_calculation_rate: Decimal
    daily_rate_numerator: Decimal
    daily_rate_denominator: int
    daily_rate: Decimal
    scheduled_work_days: int
    present_days: int
    late_days: int
    absent_days: int
    half_day_count: int
    paid_leave_days: int
    unpaid_leave_days: int
    unrecorded_days: int
    deductible_day_equivalents: Decimal
    attendance_deduction: Decimal
    additional_earnings: Decimal
    other_deductions: Decimal
    gross_pay: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    explanation: tuple[CalculationStep, ...]

    def as_evidence_outputs(self):
        """Fresh in-memory shape only: no evidence hash, identity, seal or write.

        These 15 names match the v2 output vocabulary for future interface review.
        Synthetic results are not eligible for production persistence.
        """
        return {name: getattr(self, name) for name in (
            'daily_rate', 'regular_pay', 'additional_earnings', 'gross_pay',
            'attendance_deduction', 'total_deductions', 'net_pay',
            'scheduled_work_days', 'present_days', 'late_days', 'absent_days',
            'paid_leave_days', 'unpaid_leave_days', 'half_day_count', 'unrecorded_days')}


def _require_type(value, expected, label):
    # Dataclass annotations alone do not enforce types. Reject mutable substitutes
    # and subclasses with overridden arithmetic/attributes at this bounded API.
    if type(value) is not expected:
        raise PrototypeValidationError(f'{label} must be {expected.__name__}.')


def _reference(value, label):
    if (type(value) is not str or not value.startswith('SYNTHETIC:')
            or not value[len('SYNTHETIC:'):].strip() or len(value) > 255):
        raise PrototypeValidationError(f'{label} requires an explicit SYNTHETIC: fixture reference (maximum 255 characters).')


def _date(value, label):
    _require_type(value, date, label)  # datetime and unknown coverage are rejected.
    if value.year < 1000:
        raise PrototypeValidationError(f'{label} must be within supported years 1000–9999.')


def _money(value, label, *, allow_zero=False):
    _require_type(value, Decimal, label)
    try:
        return payroll_money(value, label, allow_zero=allow_zero)
    except ValueError as error:
        raise PrototypeValidationError(str(error)) from None


def _validate_policy(policy):
    _require_type(policy, HypotheticalPolicy, 'Hypothetical policy')
    for field in fields(HypotheticalPolicy):
        expected = _POLICY_VALUES[field.name]
        value = getattr(policy, field.name)
        if type(value) is not type(expected) or value != expected:
            raise UnsupportedPolicyError(f'Unsupported hypothetical policy: {field.name}. No company policy is implied.')


def _scheduled_dates(cutoff):
    _require_type(cutoff, Cutoff, 'Cutoff')
    _date(cutoff.start_date, 'Cutoff start'); _date(cutoff.end_date, 'Cutoff end')
    if type(cutoff.code) is not str or cutoff.code not in ('A', 'B'):
        raise UnsupportedPolicyError('Only cutoff A or B is supported.')
    start = cutoff.start_date
    expected_start = date(start.year, start.month, 1 if cutoff.code == 'A' else 16)
    expected_end = date(start.year, start.month, 15 if cutoff.code == 'A' else monthrange(start.year, start.month)[1])
    if start != expected_start or cutoff.end_date != expected_end:
        raise UnsupportedPolicyError('Exact cutoff A (1–15) or B (16–month end) dates are required; arbitrary periods are unsupported.')
    # Offset iteration avoids overflowing 9999-12-31 by adding one day to end.
    return tuple(start + timedelta(days=n) for n in range((expected_end-start).days+1)
                 if (start + timedelta(days=n)).weekday() < 5)


def _validate_eligibility(eligibility, cutoff, scheduled):
    _require_type(eligibility, SyntheticEligibility, 'Synthetic eligibility')
    if eligibility.development_only is not True:
        raise PrototypeValidationError('Only development-only synthetic eligibility is accepted.')
    for name in ('fixture_reference', 'employment_reference', 'compensation_reference'):
        _reference(getattr(eligibility, name), name.replace('_', ' ').capitalize())
    if type(eligibility.eligibility) is not str or eligibility.eligibility != 'FULL_CUTOFF':
        raise UnsupportedPolicyError('Verified synthetic FULL_CUTOFF eligibility is required; unknown eligibility is unsupported.')
    _require_type(eligibility.cutoff, Cutoff, 'Eligibility cutoff')
    _scheduled_dates(eligibility.cutoff)
    if eligibility.cutoff != cutoff:
        raise PrototypeValidationError('Synthetic eligibility must describe the exact requested cutoff.')
    if (type(eligibility.pay_type) is not str or eligibility.pay_type != 'MONTHLY'
            or type(eligibility.currency_code) is not str or eligibility.currency_code != 'PHP'):
        raise UnsupportedPolicyError('Only synthetic MONTHLY/PHP compensation is supported; DAILY/HOURLY are unsupported.')
    _date(eligibility.hire_date, 'Synthetic hire date')
    if eligibility.hire_date > cutoff.start_date:
        raise UnsupportedPolicyError('Mid-cutoff hire/proration is unsupported; full-cutoff coverage is required.')
    for start_name, end_name, label in (
            ('employment_coverage_start', 'employment_coverage_end', 'Employment'),
            ('compensation_coverage_start', 'compensation_coverage_end', 'Compensation')):
        start = getattr(eligibility, start_name); end = getattr(eligibility, end_name)
        _date(start, f'{label} coverage start'); _date(end, f'{label} coverage end')
        if start > cutoff.start_date or end < cutoff.end_date:
            raise UnsupportedPolicyError(f'{label} evidence must cover the full cutoff; proration is unsupported.')
    _require_type(eligibility.calendar_exceptions, tuple, 'Calendar exceptions')
    if eligibility.calendar_exceptions:
        raise UnsupportedPolicyError('Holidays, special pay and schedule exceptions are unsupported.')
    _require_type(eligibility.scheduled_dates, tuple, 'Scheduled dates')
    for day in eligibility.scheduled_dates: _date(day, 'Scheduled date')
    if (len(eligibility.scheduled_dates) != len(set(eligibility.scheduled_dates))
            or tuple(sorted(eligibility.scheduled_dates)) != scheduled):
        raise UnsupportedPolicyError('Complete Monday–Friday scheduled-date coverage is required.')


def _classify(attendance, leaves, scheduled):
    _require_type(attendance, tuple, 'Attendance'); _require_type(leaves, tuple, 'Approved leave')
    by_date = {}; leave_by_date = {}
    for row in attendance:
        _require_type(row, AttendanceDay, 'Attendance record'); _date(row.date, 'Attendance date')
        if type(row.status) is not str or row.status not in ('PRESENT', 'LATE', 'ABSENT', 'HALF_DAY', 'ON_LEAVE'):
            raise UnsupportedPolicyError('Unsupported attendance classification.')
        if row.date not in scheduled or row.date in by_date:
            raise PrototypeValidationError('Attendance must have unique scheduled dates only, with no out-of-cutoff records.')
        by_date[row.date] = row
    for row in leaves:
        _require_type(row, ApprovedLeaveDay, 'Approved leave record'); _date(row.date, 'Leave date')
        _require_type(row.is_paid, bool, 'Paid leave classification')
        if row.approved is not True:
            raise PrototypeValidationError('Leave requires explicit synthetic approval.')
        _reference(row.fixture_reference, 'Leave')
        if row.date not in scheduled or row.date in leave_by_date:
            raise PrototypeValidationError('Approved leave must have unique scheduled dates; conflicting leave is unsupported.')
        leave_by_date[row.date] = row
    if set(by_date) != set(scheduled):
        raise PrototypeValidationError('Attendance is missing scheduled days; no salary can be calculated.')
    daily = []
    for day in scheduled:
        status = by_date[day].status; leave = leave_by_date.get(day)
        if (status == 'ON_LEAVE') != (leave is not None):
            raise PrototypeValidationError('Attendance and approved leave are missing or contradictory.')
        classification = ('PAID_LEAVE' if leave.is_paid else 'UNPAID_LEAVE') if leave else status
        units = {'PRESENT': Decimal('0'), 'LATE': Decimal('0'), 'ABSENT': Decimal('1'),
                 'HALF_DAY': Decimal('0.5'), 'PAID_LEAVE': Decimal('0'), 'UNPAID_LEAVE': Decimal('1')}[classification]
        daily.append(DailyExplanation(day, status, classification, units, leave.fixture_reference if leave else None))
    return tuple(daily)


def _adjustments(rows):
    _require_type(rows, tuple, 'Synthetic adjustments')
    seen = set(); earnings = Decimal('0.00'); deductions = Decimal('0.00')
    for row in rows:
        _require_type(row, SyntheticAdjustment, 'Adjustment')
        if type(row.kind) is not str or row.kind not in ('EARNING', 'DEDUCTION'):
            raise PrototypeValidationError('Adjustment must be an EARNING or DEDUCTION.')
        if row.approved is not True:
            raise PrototypeValidationError('Adjustments require explicit synthetic approval.')
        _reference(row.fixture_reference, 'Adjustment')
        if row.fixture_reference in seen:
            raise PrototypeValidationError('Duplicate synthetic adjustment reference; no amount was counted twice.')
        seen.add(row.fixture_reference)
        amount = _money(row.amount, 'Adjustment amount')
        if row.kind == 'EARNING': earnings += amount
        else: deductions += amount
        _money(earnings, 'Aggregate earnings', allow_zero=True)
        _money(deductions, 'Aggregate deductions', allow_zero=True)
    return tuple(sorted(rows, key=lambda row: row.fixture_reference)), earnings, deductions


def calculate(inputs):
    """Calculate only the explicit hypothetical scenario; return no partial result.

    Every stored-money-shaped result is bounded to DECIMAL(12,2). The auxiliary
    daily calculation rate has 50 significant digits, NOT two-place storage scale;
    its exact rational numerator/denominator are returned too. Attendance uses
    (base * aggregate units) / scheduled days, rounded once, never displayed rate.
    """
    _require_type(inputs, CalculationInput, 'Calculation input')
    _validate_policy(inputs.policy)
    scheduled = _scheduled_dates(inputs.cutoff)
    _validate_eligibility(inputs.eligibility, inputs.cutoff, scheduled)
    daily = _classify(inputs.attendance, inputs.approved_leave, scheduled)
    # Own the context so caller precision, rounding, traps and flags cannot change
    # the result. No global Decimal context is modified.
    context = Context(prec=50, rounding=ROUND_HALF_UP, Emin=-999999, Emax=999999,
                      capitals=1, clamp=0, flags=[],
                      traps=[InvalidOperation, DivisionByZero, Overflow])
    with localcontext(context):
        salary = _money(inputs.monthly_salary, 'Monthly salary')
        base = salary / Decimal('2')
        rounded_base = base.quantize(Decimal('0.01'))
        if base != rounded_base:
            raise UnsupportedPolicyError('Odd-cent monthly salary requires an unapproved reconciliation policy; no balancing cent was invented.')
        base = rounded_base
        rate = base / Decimal(len(scheduled))
        display_rate = rate.quantize(Decimal('0.01'))
        units = sum((day.deductible_units for day in daily), Decimal('0'))
        deduction = (base * units / Decimal(len(scheduled))).quantize(Decimal('0.01'))
        adjustments, earnings, other_deductions = _adjustments(inputs.adjustments)
        gross = base + earnings
        total_deductions = deduction + other_deductions
        # Check aggregate overflow BEFORE excess-deduction comparison; never clip.
        for label, value in (('Regular pay', base), ('Displayed daily rate', display_rate),
                             ('Attendance deduction', deduction), ('Gross pay', gross),
                             ('Total deductions', total_deductions)):
            _money(value, label, allow_zero=True)
        if total_deductions > gross:
            raise UnsupportedPolicyError('Deductions exceed gross pay; negative net pay and zero-floor clipping are unsupported.')
        net = gross - total_deductions
        _money(net, 'Net pay', allow_zero=True)
        counts = {kind: sum(day.classification == kind for day in daily)
                  for kind in ('PRESENT', 'LATE', 'ABSENT', 'HALF_DAY', 'PAID_LEAVE', 'UNPAID_LEAVE')}
        explanation = (
            CalculationStep('REGULAR_BASE', f'{salary} / 2', base),
            CalculationStep('DAILY_CALCULATION_RATE', f'{base} / {len(scheduled)} (50 significant digits)', rate),
            CalculationStep('DISPLAY_DAILY_RATE', 'ROUND_HALF_UP(daily calculation rate, 2)', display_rate),
            CalculationStep('ATTENDANCE_DEDUCTION', f'ROUND_HALF_UP(({base} * {units}) / {len(scheduled)}, 2)', deduction),
            CalculationStep('EARNINGS', 'sum(approved synthetic EARNING amounts)', earnings),
            CalculationStep('OTHER_DEDUCTIONS', 'sum(approved synthetic DEDUCTION amounts)', other_deductions),
            CalculationStep('GROSS_PAY', f'{base} + {earnings}', gross),
            CalculationStep('TOTAL_DEDUCTIONS', f'{deduction} + {other_deductions}', total_deductions),
            CalculationStep('NET_PAY', f'{gross} - {total_deductions}', net),
        )
        return CalculationResult(
            scenario=inputs.policy.scenario, cutoff=inputs.cutoff, monthly_salary=salary,
            scheduled_dates=scheduled, daily=daily, adjustments=adjustments,
            regular_pay=base, daily_calculation_rate=rate, daily_rate_numerator=base,
            daily_rate_denominator=len(scheduled), daily_rate=display_rate,
            scheduled_work_days=len(scheduled), present_days=counts['PRESENT'], late_days=counts['LATE'],
            absent_days=counts['ABSENT'], half_day_count=counts['HALF_DAY'],
            paid_leave_days=counts['PAID_LEAVE'], unpaid_leave_days=counts['UNPAID_LEAVE'], unrecorded_days=0,
            deductible_day_equivalents=units, attendance_deduction=deduction,
            additional_earnings=earnings, other_deductions=other_deductions,
            gross_pay=gross, total_deductions=total_deductions, net_pay=net, explanation=explanation)
