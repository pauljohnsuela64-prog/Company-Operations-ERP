"""Employee/Department boundaries matching core_schema.sql; no lifecycle policy."""
from datetime import date, datetime
import re


class HRValidationError(ValueError):
    """Expected invalid input or a recoverable integrity conflict."""


EMPLOYMENT_STATUSES = ('Active', 'Inactive', 'On Leave', 'Resigned', 'Terminated')
EMPLOYEE_FIELDS = ('employee_number', 'department_id', 'first_name', 'middle_name',
                   'last_name', 'email', 'phone', 'job_title', 'hire_date')
DEPARTMENT_FIELDS = ('department_code', 'department_name', 'description')


def text(value, label, limit, required=False, uppercase=False):
    if value is not None and not isinstance(value, str):
        raise HRValidationError(f'{label} must be text.')
    value = (value or '').strip()
    if uppercase:
        value = value.upper()
    if required and not value:
        raise HRValidationError(f'{label} is required.')
    if len(value) > limit:
        raise HRValidationError(f'{label} must not exceed {limit} characters.')
    return value or None


def identifier(value, label, optional=False):
    if optional and (value is None or isinstance(value, str) and not value.strip()):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise HRValidationError(f'{label} must be a valid positive identifier.')
    return int(raw)


def hire_date(value):
    if value is None or isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, str):
        value = value.strip()
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                raise ValueError
            value = date.fromisoformat(value)
        except ValueError:
            raise HRValidationError('Hire date must be a valid YYYY-MM-DD date.') from None
    if isinstance(value, datetime) or not isinstance(value, date) or value.year < 1000:
        raise HRValidationError('Hire date must be within MySQL DATE range (1000-9999), without a time.')
    return value


def employee_values(raw, editing=False):
    values = dict(
        employee_number=text(raw.get('employee_number'), 'Employee number', 30, True, True),
        department_id=identifier(raw.get('department_id'), 'Department', True),
        first_name=text(raw.get('first_name'), 'First name', 100, True),
        middle_name=text(raw.get('middle_name'), 'Middle name', 100),
        last_name=text(raw.get('last_name'), 'Last name', 100, True),
        email=text(raw.get('email'), 'Email', 150),
        phone=text(raw.get('phone'), 'Phone', 30),
        job_title=text(raw.get('job_title'), 'Job title', 100),
        hire_date=hire_date(raw.get('hire_date')),
    )
    if values['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+', values['email']):
        raise HRValidationError('Email must be a valid email address.')
    if editing:
        status = text(raw.get('employment_status'), 'Employment status', 30, True)
        if status not in EMPLOYMENT_STATUSES:
            raise HRValidationError('Invalid employment status.')
        values['employment_status'] = status
    return values


def department_values(raw):
    return dict(department_code=text(raw.get('department_code'), 'Department code', 20, True, True),
                department_name=text(raw.get('department_name'), 'Department name', 100, True),
                description=text(raw.get('description'), 'Description', 255))


def form_values(form, fields):
    if any(len(form.getlist(field)) > 1 for field in fields):
        raise HRValidationError('Submit only one value for each field.')
    return {field: form.get(field, '') for field in fields}


def lock_department(cursor, department_id, previous_id=None):
    if department_id is None:
        return
    cursor.execute('SELECT is_active FROM departments WHERE department_id=%s FOR SHARE', (department_id,))
    row = cursor.fetchone()
    if row is None:
        raise HRValidationError('Selected department does not exist.')
    if not row['is_active'] and department_id != previous_id:
        raise HRValidationError('You cannot assign an employee to an inactive department.')


def translate_write_error(error, entity):
    if error.errno == 1062:
        message = ('Employee number or email already exists.' if entity == 'Employee'
                   else 'Department code or department name already exists.')
        return HRValidationError(message)
    if error.errno == 1452:
        return HRValidationError('A selected reference no longer exists. Reload and try again.')
    if error.errno in (1205, 1213):
        return HRValidationError('HR data changed concurrently. Reload and try again.')
    return error
