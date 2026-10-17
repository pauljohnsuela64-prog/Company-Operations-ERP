"""Validation matching procurement and inventory SQL column definitions."""
from decimal import Decimal, InvalidOperation


def decimal_value(value, label, positive=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a valid number.") from None
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise ValueError(f"{label} must be finite and {'greater than zero' if positive else 'zero or greater'}.")
    if amount > Decimal('9999999999.99') or amount != amount.quantize(Decimal('0.01')):
        raise ValueError(f"{label} must have at most two decimal places and cannot exceed 9999999999.99.")
    return amount


def validate_notes(value, label, limit=255):
    if value and len(value) > limit:
        raise ValueError(f"{label} cannot exceed {limit} characters.")


def lock_draft(cursor, table, key, identifier):
    cursor.execute(f"SELECT status FROM {table} WHERE {key} = %s FOR UPDATE", (identifier,))
    row = cursor.fetchone()
    if not row or row[0] != 'DRAFT':
        raise ValueError("Items can only be edited while the parent record is in DRAFT status.")


def lock_item_parent(cursor, item_table, item_key, identifier, parent_table, parent_key):
    cursor.execute(f"SELECT {parent_key} FROM {item_table} WHERE {item_key} = %s", (identifier,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Item not found.")
    lock_draft(cursor, parent_table, parent_key, row[0])
