"""Exact monetary validation for the existing Payroll DECIMAL(12,2) columns."""
from decimal import Decimal, InvalidOperation
import re

MAX_MONEY = Decimal("9999999999.99")


def payroll_money(value, label="Amount", *, allow_zero=False):
    # Do not accept floats: binary approximations must never become pay inputs.
    if isinstance(value, (float, bool)) or value is None:
        raise ValueError(f"{label} must be a valid decimal amount.")
    if isinstance(value, str) and not re.fullmatch(
            r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value.strip()):
        raise ValueError(f"{label} must be a valid finite decimal amount.")
    try:
        amount = Decimal(value.strip() if isinstance(value, str) else value)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a valid decimal amount.") from None
    if not amount.is_finite():
        raise ValueError(f"{label} must be a finite decimal amount.")
    if amount.as_tuple().exponent < -2:
        raise ValueError(f"{label} must have no more than two decimal places.")
    if amount < 0 or (not allow_zero and amount == 0):
        rule = "zero or greater" if allow_zero else "greater than zero"
        raise ValueError(f"{label} must be {rule}.")
    if amount > MAX_MONEY:
        raise ValueError(f"{label} must not exceed 9,999,999,999.99 (Payroll database limit).")
    return amount


def validate_payroll_totals(**totals):
    """Validate calculated values after existing HALF_UP rounding, before DML."""
    for name, value in totals.items():
        payroll_money(value, name.replace("_", " ").capitalize(), allow_zero=True)


def validate_evidence_money(entry, adjustments):
    """Old matching fingerprints must not authorize previously clipped totals."""
    payroll_money(entry['basic_rate'], 'Saved basic rate')
    validate_payroll_totals(**{name: entry[name] for name in (
        'daily_rate', 'regular_pay', 'additional_earnings', 'gross_pay',
        'attendance_deduction', 'total_deductions', 'net_pay')})
    earnings = Decimal('0.00')
    deductions = Decimal('0.00')
    for adjustment in adjustments:
        amount = payroll_money(adjustment['amount'], 'Saved adjustment amount')
        if adjustment['adjustment_type'] == 'EARNING':
            earnings += amount
        elif adjustment['adjustment_type'] == 'DEDUCTION':
            deductions += amount
        else:
            raise ValueError('Payroll contains an invalid adjustment type. Review the calculation.')
    validate_payroll_totals(additional_earnings=earnings, other_deductions=deductions,
                            gross_pay=entry['regular_pay'] + earnings,
                            total_deductions=entry['attendance_deduction'] + deductions)
