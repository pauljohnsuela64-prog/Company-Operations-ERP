"""IT Asset input boundaries matching the checked-in MySQL schema."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

MAX_COST = Decimal('9999999999.99')
CONDITIONS = ('NEW', 'GOOD', 'FAIR', 'POOR', 'DAMAGED')
ASSET_FIELDS = ('asset_tag', 'asset_name', 'category_id', 'brand', 'model', 'serial_number',
                'department_id', 'purchase_date', 'purchase_cost', 'warranty_expiry',
                'condition_status', 'notes')


def identifier(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    raw = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,10}', raw) or not 1 <= int(raw) <= 2147483647:
        raise ValueError(f'{label} must be a valid positive identifier.')
    return int(raw)


def text(value, label, limit, required=False):
    value = '' if value is None else str(value).strip()
    if required and not value:
        raise ValueError(f'{label} is required.')
    if len(value) > limit:
        raise ValueError(f'{label} must not exceed {limit} characters.')
    return value or None


def cost(value, label='Cost'):
    if value in (None, ''):
        return None
    if isinstance(value, (float, bool)):
        raise ValueError(f'{label} must be an exact decimal amount.')
    raw = str(value).strip()
    if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?', raw):
        raise ValueError(f'{label} must be a finite nonnegative amount with at most two decimal places.')
    try:
        amount = Decimal(raw.replace(',', ''))
    except InvalidOperation:
        raise ValueError(f'{label} must be a valid decimal amount.') from None
    if not amount.is_finite() or amount < 0 or amount > MAX_COST:
        raise ValueError(f'{label} must be between 0 and {MAX_COST}.')
    return amount


def calendar_date(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    if isinstance(value, datetime):
        raise ValueError(f'{label} must be a date without a time.')
    if not isinstance(value, date):
        try:
            if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
                raise ValueError
            value = date.fromisoformat(value)
        except ValueError:
            raise ValueError(f'{label} must be a valid YYYY-MM-DD date.') from None
    if value.year < 1000:
        raise ValueError(f'{label} must be within MySQL DATE range (1000-9999).')
    return value


def asset_values(raw):
    condition = text(raw.get('condition_status'), 'Condition', 20, True).upper()
    if condition not in CONDITIONS:
        raise ValueError('Invalid asset condition.')
    return (
        text(str(raw.get('asset_tag') or '').strip().upper(), 'Asset tag', 50, True),
        text(raw.get('asset_name'), 'Asset name', 150, True),
        identifier(raw.get('category_id'), 'Category'),
        text(raw.get('brand'), 'Brand', 100), text(raw.get('model'), 'Model', 100),
        text(raw.get('serial_number'), 'Serial number', 100),
        identifier(raw.get('department_id'), 'Department', True),
        calendar_date(raw.get('purchase_date'), 'Purchase date', True),
        cost(raw.get('purchase_cost'), 'Purchase cost'),
        calendar_date(raw.get('warranty_expiry'), 'Warranty expiry', True),
        condition, text(raw.get('notes'), 'Notes', 255),
    )


def category_values(category_code, category_name, description):
    """Validate normalized category text before any SQL, in every SQL mode."""
    code = text(category_code, 'Category code', 30, True).upper()
    # Uppercasing can expand Unicode characters; enforce the persisted length too.
    code = text(code, 'Category code', 30, True)
    return (code, text(category_name, 'Category name', 100, True),
            text(description, 'Description', 255))


def lock_employee(cursor, employee_id):
    if employee_id is not None:
        cursor.execute('SELECT employee_id, employment_status FROM employees WHERE employee_id=%s FOR SHARE', (employee_id,))
        if not cursor.fetchone():
            raise ValueError('Selected employee does not exist.')
        # Existing policy permits every employment status. No new restriction.


def lock_references(cursor, category_id, department_id, employee_id=None, previous=None):
    # Existing asset first (caller), then employee -> category -> department.
    lock_employee(cursor, employee_id)
    for table, key, value, label in [('it_asset_categories', 'category_id', category_id, 'category'),
                                      ('departments', 'department_id', department_id, 'department')]:
        if value is None:
            continue
        cursor.execute(f'SELECT is_active FROM {table} WHERE {key}=%s FOR SHARE', (value,))
        row = cursor.fetchone()
        unchanged = previous is not None and previous[key] == value
        if not row or (row['is_active'] != 1 and not unchanged):
            raise ValueError(f'Selected {label} is invalid or inactive.')


def translate_write_error(error):
    if getattr(error, 'errno', None) == 1062:
        return ValueError('Asset tag or serial number already exists.')
    if getattr(error, 'errno', None) in (1205, 1213):
        return ValueError('IT asset data changed concurrently. Reload and try again.')
    if getattr(error, 'errno', None) == 1452:
        return ValueError('A related record no longer exists. Reload and try again.')
    return error
