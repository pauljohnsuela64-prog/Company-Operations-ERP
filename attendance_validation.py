"""Attendance storage/input rules, not shift, lateness or payroll policy."""
from datetime import date, datetime, time, timedelta
import re

STATUSES = ('PRESENT', 'LATE', 'ABSENT', 'ON_LEAVE', 'HALF_DAY')
FIELDS = ('employee_id', 'attendance_date', 'time_in', 'time_out', 'status', 'notes')


class AttendanceError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def identifier(value, label='Employee'):
    raw = str(value).strip()
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise AttendanceError(f'{label} must be a valid positive ID.')
    return int(raw)


def text(value, label, maximum):
    if not isinstance(value, str):
        raise AttendanceError(f'{label} must be text.')
    value = value.strip()
    if len(value) > maximum:
        raise AttendanceError(f'{label} must not exceed {maximum} characters.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise AttendanceError(f'{label} must be valid Unicode.') from None
    if any((ord(c) < 32 and c not in '\t\n\r') or ord(c) == 127 for c in value):
        raise AttendanceError(f'{label} contains unsupported control characters.')
    return value


def calendar_date(value):
    if type(value) is date:
        result = value
    else:
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value.strip()):
            raise AttendanceError('Attendance date must be a valid YYYY-MM-DD date.')
        try:
            result = date.fromisoformat(value.strip())
        except ValueError:
            raise AttendanceError('Attendance date must be a valid YYYY-MM-DD date.') from None
    if result.year < 1000:
        raise AttendanceError('Attendance date must be between years 1000 and 9999.')
    return result


def clock(value, label):
    if value is None or value == '':
        return None
    if isinstance(value, time):
        if value.tzinfo is not None or value.microsecond:
            raise AttendanceError(f'{label} must be a local clock time to whole seconds.')
        return value
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{2}:[0-9]{2}(?::[0-9]{2})?', value.strip()):
        raise AttendanceError(f'{label} must be a valid HH:MM or HH:MM:SS time.')
    try:
        return time(*(int(part) for part in value.strip().split(':')))
    except ValueError:
        raise AttendanceError(f'{label} must be a valid HH:MM or HH:MM:SS time.') from None


def values(raw):
    status = text(raw.get('status', ''), 'Status', 20).upper()
    if status not in STATUSES:
        raise AttendanceError('Invalid attendance status.')
    return dict(employee_id=identifier(raw.get('employee_id', '')),
                attendance_date=calendar_date(raw.get('attendance_date', '')),
                time_in=clock(raw.get('time_in'), 'Time In'), time_out=clock(raw.get('time_out'), 'Time Out'),
                status=status, notes=text('' if raw.get('notes') is None else raw.get('notes'), 'Notes', 255) or None)


def form_values(form):
    if any(len(form.getlist(field)) > 1 for field in FIELDS):
        raise AttendanceError('Submit only one value for each Attendance field.')
    return values({field: form.get(field, '') for field in FIELDS})


def listing_values(args):
    fields = dict(search='', date='', status='', department_id='', page='1', page_size='25')
    if hasattr(args, 'getlist') and any(len(args.getlist(field)) > 1 for field in fields):
        raise AttendanceError('Submit only one value for each Attendance filter.')
    raw = {key: args.get(key, default) for key, default in fields.items()}
    search = text(raw['search'], 'Search', 100)
    status = text(raw['status'], 'Status', 20).upper()
    if status and status not in STATUSES:
        raise AttendanceError('Invalid attendance status.')
    page = identifier(raw['page'], 'Page')
    size = identifier(raw['page_size'], 'Page size')
    if size not in (25, 50, 100):
        raise AttendanceError('Page size must be 25, 50 or 100.')
    return dict(search=search, date=calendar_date(raw['date']) if raw['date'] else None,
                status=status, department_id=identifier(raw['department_id'], 'Department') if raw['department_id'] else None,
                page=page, page_size=size)


def time_input(value):
    """MySQL TIME is returned as timedelta; retain seconds in edit inputs."""
    if value is None:
        return ''
    if isinstance(value, timedelta) and 0 <= value.total_seconds() < 86400:
        seconds = int(value.total_seconds())
        return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'
    return str(value)
