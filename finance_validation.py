"""Finance input boundaries matching DECIMAL, DATE, INT and VARCHAR columns."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

EXPENSE_MAX = Decimal('9999999999.99')
BUDGET_MAX = Decimal('999999999999.99')


def money(value, label='Amount', maximum=EXPENSE_MAX):
    if isinstance(value, (float, bool)):
        raise ValueError(f'{label} must be an exact decimal amount.')
    text = str(value).strip()
    # Accept ordinary decimal input and correctly grouped thousands only.
    if not re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?', text):
        raise ValueError(f'{label} must be a finite positive amount with at most two decimal places.')
    try:
        amount = Decimal(text.replace(',', ''))
    except InvalidOperation:
        raise ValueError(f'{label} must be a valid amount.') from None
    if not amount.is_finite() or amount <= 0 or amount > maximum:
        raise ValueError(f'{label} must be greater than zero and cannot exceed {maximum}.')
    return amount


def identifier(value, label, optional=False):
    if optional and value in (None, ''):
        return None
    text = str(value).strip()
    if not re.fullmatch(r'[0-9]{1,10}', text) or not 1 <= int(text) <= 2147483647:
        raise ValueError(f'{label} must be a valid positive identifier.')
    return int(text)


def calendar_year(value):
    text = str(value).strip()
    if not re.fullmatch(r'[0-9]{4}', text) or not 1000 <= int(text) <= 9999:
        raise ValueError('Budget year must be between 1000 and 9999, matching expense dates.')
    return int(text)


def expense_date(value):
    if isinstance(value, datetime):
        raise ValueError('Expense date must be a date without a time.')
    if not isinstance(value, date):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('Expense date must be a valid YYYY-MM-DD date.')
        try:
            value = date.fromisoformat(value)
        except ValueError:
            raise ValueError('Expense date must be a valid calendar date.') from None
    if value.year < 1000:
        raise ValueError('Expense date must be within MySQL DATE range (1000-9999).')
    return value


def text(value, label, limit, required=False):
    value = '' if value is None else str(value).strip()
    if required and not value:
        raise ValueError(f'{label} is required.')
    if len(value) > limit:
        raise ValueError(f'{label} must not exceed {limit} characters.')
    return value or None


def expense_values(expense_date_value, category_id, department_id, supplier_id,
                   purchase_order_id, description, amount, reference_number, payment_method, notes):
    method = text(payment_method, 'Payment method', 20)
    if method not in (None, 'CASH', 'BANK_TRANSFER', 'CHECK', 'CARD', 'OTHER'):
        raise ValueError('Invalid payment method.')
    return (expense_date(expense_date_value), identifier(category_id, 'Category'),
            identifier(department_id, 'Department', True), identifier(supplier_id, 'Supplier', True),
            identifier(purchase_order_id, 'Purchase order', True), text(description, 'Description', 255, True),
            money(amount), text(reference_number, 'Reference number', 100), method, text(notes, 'Notes', 255))


def budget_values(department_id, year, amount, notes):
    if notes is not None:
        if not isinstance(notes,str):raise ValueError('Notes must be text.')
        if any((ord(c)<32 and c not in '\t\r\n') or ord(c)==127 for c in notes):
            raise ValueError('Notes contain unsupported control characters.')
        try:notes.encode('utf-8')
        except UnicodeError:raise ValueError('Notes must be valid Unicode.') from None
    return (identifier(department_id, 'Department'), calendar_year(year),
            money(amount, 'Budget amount', BUDGET_MAX), text(notes, 'Notes', 255))


def lock_department(cursor, department_id, active=False):
    cursor.execute('SELECT is_active FROM departments WHERE department_id = %s FOR SHARE', (department_id,))
    row = cursor.fetchone()
    if not row or (active and not _column(row, 'is_active')):
        raise ValueError('Selected department is invalid or inactive.' if active else 'Selected department does not exist.')


def _column(row, name):
    return row[name] if isinstance(row, dict) else row[0]


def lock_expense_references(cursor, category_id, department_id, supplier_id, purchase_order_id):
    # PO first, matching procurement's parent-before-master locking order.
    if purchase_order_id is not None:
        cursor.execute('SELECT status FROM purchase_orders WHERE purchase_order_id = %s FOR SHARE', (purchase_order_id,))
        row = cursor.fetchone()
        if not row or _column(row, 'status') == 'CANCELLED':
            raise ValueError('Selected purchase order is invalid or cancelled.')
    cursor.execute('SELECT is_active FROM expense_categories WHERE category_id = %s FOR SHARE', (category_id,))
    row = cursor.fetchone()
    if not row or not _column(row, 'is_active'):
        raise ValueError('Selected expense category is invalid or inactive.')
    if department_id is not None:
        lock_department(cursor, department_id, active=True)
    if supplier_id is not None:
        cursor.execute('SELECT is_active FROM suppliers WHERE supplier_id = %s FOR SHARE', (supplier_id,))
        row = cursor.fetchone()
        if not row or not _column(row, 'is_active'):
            raise ValueError('Selected supplier is invalid or inactive.')
