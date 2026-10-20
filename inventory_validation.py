"""Inventory master-data validation matching the existing MySQL schema."""
from procurement_validation import decimal_value


def text_field(value, label, limit, required=False, upper=False):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValueError(f'{label} must be text.')
    value = value.strip()
    if upper:
        value = value.upper()
    if required and not value:
        raise ValueError(f'{label} is required.')
    if len(value) > limit:
        raise ValueError(f'{label} cannot exceed {limit} characters.')
    return value if required else value or None


def category_identifier(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not str(value).isdecimal() or not 0 < int(value) <= 2147483647:
        raise ValueError('Select a valid inventory category.')
    return int(value)


def category_fields(code, name, description):
    return (text_field(code, 'Category code', 30, True, True),
            text_field(name, 'Category name', 100, True),
            text_field(description, 'Category description', 255))


def warehouse_fields(code, name, location):
    from warehouse_validation import fields
    return fields(code, name, location)


def item_fields(code, name, category, description, unit, reorder):
    return (text_field(code, 'Item code', 50, True, True),
            text_field(name, 'Item name', 150, True), category_identifier(category),
            text_field(description, 'Item description', 255),
            text_field(unit, 'Unit of measure', 30, True),
            decimal_value(reorder, 'Reorder level'))


def lock_assignment_category(cursor, category_id, existing_category=None):
    if category_id is None:
        return
    cursor.execute('SELECT is_active FROM inventory_categories WHERE category_id = %s FOR SHARE', (category_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError('Selected inventory category does not exist.')
    # Retaining an existing inactive assignment is not a new assignment.
    if not row[0] and category_id != existing_category:
        raise ValueError('Inactive inventory categories cannot be used for new assignments.')
