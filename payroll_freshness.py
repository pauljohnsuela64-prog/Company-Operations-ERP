"""Versioned calculation evidence and transaction-scoped payroll/HR coordination."""
import hashlib
import hmac
import json
from datetime import date,datetime
from decimal import Decimal

VERSION = 1


def lock_payroll_inputs(cursor):
    # First lock in every participating write transaction; never a preflight.
    try:
        cursor.execute('SELECT guard_id FROM payroll_input_guard WHERE guard_id = 1 FOR UPDATE')
        row = cursor.fetchone()
    except Exception as error:
        if getattr(error, 'errno', None) in (1205, 1213):
            raise ValueError('Payroll inputs are being changed concurrently. Reload and retry; no operation was completed.') from error
        if getattr(error, 'errno', None) in (1146, 1054):
            raise ValueError('Payroll safety upgrade is required. Contact an administrator.') from error
        raise
    if row is None:

        raise ValueError('Payroll safety upgrade is incomplete. Contact an administrator.')


def raise_payroll_lock_error(error):
    if getattr(error, 'errno', None) in (1205, 1213):
        raise ValueError('Payroll inputs changed concurrently. Reload and retry; the transaction was rolled back.') from error


def _json_value(value):
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,(date,datetime)):return value.isoformat()
    raise TypeError('Unsupported payroll evidence value')


def fingerprint(cursor, period_id, entry_id):
    cursor.execute('SELECT start_date,end_date FROM payroll_periods WHERE payroll_period_id=%s FOR UPDATE',(period_id,))
    period=cursor.fetchone()
    cursor.execute("""SELECT payroll_entry_id,employee_id,pay_type,basic_rate,currency_code,
        scheduled_work_days,present_days,late_days,absent_days,paid_leave_days,
        unpaid_leave_days,half_day_count,unrecorded_days,daily_rate,regular_pay,
        additional_earnings,gross_pay,attendance_deduction,total_deductions,net_pay
        FROM payroll_entries WHERE payroll_entry_id=%s AND payroll_period_id=%s FOR UPDATE""",(entry_id,period_id))
    entry=cursor.fetchone()
    if not period or not entry:raise ValueError('Payroll calculation record not found.')
    cursor.execute("""SELECT attendance_id,attendance_date,status FROM attendance_records
        WHERE employee_id=%s AND attendance_date BETWEEN %s AND %s
        AND WEEKDAY(attendance_date)<5 ORDER BY attendance_date,attendance_id FOR UPDATE""",
        (entry['employee_id'],period['start_date'],period['end_date']))
    attendance=cursor.fetchall()
    cursor.execute("""SELECT lr.leave_request_id,lr.start_date,lr.end_date,lr.leave_type_id,lt.is_paid
        FROM leave_requests lr JOIN leave_types lt ON lt.leave_type_id=lr.leave_type_id
        WHERE lr.employee_id=%s AND lr.status='APPROVED' AND lr.start_date<=%s AND lr.end_date>=%s
        ORDER BY lr.leave_request_id FOR UPDATE""",(entry['employee_id'],period['end_date'],period['start_date']))
    leaves=cursor.fetchall()
    cursor.execute("""SELECT adjustment_id,adjustment_type,amount FROM payroll_adjustments
        WHERE payroll_entry_id=%s ORDER BY adjustment_id FOR UPDATE""",(entry_id,))
    payload=dict(version=VERSION,period=period,entry=entry,attendance=attendance,leaves=leaves,adjustments=cursor.fetchall())
    return hashlib.sha256(json.dumps(payload,default=_json_value,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()


def seal_calculation(cursor,period_id,entry_id):
    digest=fingerprint(cursor,period_id,entry_id)
    cursor.execute('UPDATE payroll_entries SET calculation_input_version=%s,calculation_input_hash=%s WHERE payroll_entry_id=%s',
                   (VERSION,digest,entry_id))


def verify_calculations(cursor,period_id):
    cursor.execute('SELECT payroll_entry_id,calculation_input_version,calculation_input_hash FROM payroll_entries WHERE payroll_period_id=%s ORDER BY payroll_entry_id FOR UPDATE',(period_id,))
    entries=cursor.fetchall()
    if not entries:raise ValueError('Payroll has no calculated entries. Generate and calculate it first.')
    for entry in entries:
        if entry['calculation_input_version']!=VERSION or not entry['calculation_input_hash']:
            raise ValueError('Payroll calculation is unverified. Draft payroll must be recalculated; submitted payroll must return to Draft. Approved payroll requires an authorized verification/correction process before payment.')
        if not hmac.compare_digest(entry['calculation_input_hash'],fingerprint(cursor,period_id,entry['payroll_entry_id'])):
            raise ValueError('Payroll calculation inputs or results changed. Return submitted payroll to Draft and recalculate. Approved payroll requires an authorized correction process before payment.')
