"""Leave input/storage limits; existing calendar-day and workflow rules only."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re

STATUSES = ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')
REQUEST_FIELDS = ('employee_id', 'leave_type_id', 'start_date', 'end_date', 'reason')
TYPE_FIELDS = ('leave_code', 'leave_name', 'description', 'annual_entitlement', 'is_paid')


class LeaveError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def identifier(value, label='Employee'):
    raw = str(value).strip()
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise LeaveError(f'{label} must be a valid positive ID.')
    return int(raw)


def text(value, label, maximum, required=False):
    if not isinstance(value, str):
        raise LeaveError(f'{label} must be text.')
    value = value.strip()
    if required and not value:
        raise LeaveError(f'{label} is required.')
    if len(value) > maximum:
        raise LeaveError(f'{label} must not exceed {maximum} characters.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise LeaveError(f'{label} must be valid Unicode.') from None
    if any((ord(c) < 32 and c not in '\t\n\r') or ord(c) == 127 for c in value):
        raise LeaveError(f'{label} contains unsupported control characters.')
    return value


def calendar_date(value):
    try:
        if type(value) is date:
            result = value
        elif isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value.strip()):
            result = date.fromisoformat(value.strip())
        else:
            raise ValueError
        if result.year < 1000:
            raise ValueError
        return result
    except ValueError:
        raise LeaveError('Leave dates must be valid YYYY-MM-DD dates between years 1000 and 9999.') from None


def request_values(raw):
    start, end = calendar_date(raw.get('start_date')), calendar_date(raw.get('end_date'))
    if end < start:
        raise LeaveError('End date cannot be earlier than start date.')
    days = (end - start).days + 1
    if days > 999:
        raise LeaveError('The selected range exceeds the existing total-days storage limit (999 days).')
    return dict(employee_id=identifier(raw.get('employee_id')), leave_type_id=identifier(raw.get('leave_type_id'), 'Leave type'),
                start_date=start, end_date=end, total_days=days, reason=text(raw.get('reason'), 'Reason', 500, True))


def unique_values(form, fields):
    if hasattr(form, 'getlist') and any(len(form.getlist(field)) > 1 for field in fields):
        raise LeaveError('Submit only one value for each Leave field or filter.')
    return {field: form.get(field, '') for field in fields}


def entitlement(value):
    if value is None or value == '':
        return None
    try:
        if isinstance(value, bool) or len(str(value)) > 40:
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= Decimal('999.99') or number != number.quantize(Decimal('.01')):
            raise ValueError
        return number
    except (InvalidOperation, ValueError):
        raise LeaveError('Annual entitlement must be between 0 and 999.99 with at most two decimal places, or blank.') from None


def type_values(raw):
    paid = raw.get('is_paid')
    if paid not in (True, False, 0, 1, '', '0', '1', None):
        raise LeaveError('Invalid paid-leave value.')
    return dict(leave_code=text(text(raw.get('leave_code'), 'Leave code', 30, True).upper(), 'Leave code', 30, True),
                leave_name=text(raw.get('leave_name'), 'Leave name', 100, True),
                description=text('' if raw.get('description') is None else raw.get('description'), 'Description', 255) or None,
                annual_entitlement=entitlement(raw.get('annual_entitlement')), is_paid=paid in (True, 1, '1'))


def listing_values(args):
    defaults = dict(search='', status='', leave_type_id='', department_id='', date_from='', date_to='', page='1', page_size='25')
    unique_values(args, defaults)
    raw = {key: args.get(key, default) for key, default in defaults.items()}
    status = text(raw['status'], 'Status', 20).upper()
    if status and status not in STATUSES:
        raise LeaveError('Invalid leave status.')
    lower = calendar_date(raw['date_from']) if raw['date_from'] else None
    upper = calendar_date(raw['date_to']) if raw['date_to'] else None
    if lower and upper and lower > upper:
        raise LeaveError('Filter end date cannot be earlier than start date.')
    size = identifier(raw['page_size'], 'Page size')
    if size not in (25, 50, 100):
        raise LeaveError('Page size must be 25, 50 or 100.')
    return dict(search=text(raw['search'], 'Search', 100), status=status,
                leave_type_id=identifier(raw['leave_type_id'], 'Leave type') if raw['leave_type_id'] else None,
                department_id=identifier(raw['department_id'], 'Department') if raw['department_id'] else None,
                date_from=lower, date_to=upper, page=identifier(raw['page'], 'Page'), page_size=size)
