from dataclasses import dataclass
import uuid
import mysql.connector
from procurement_validation import decimal_value, validate_notes
from database import get_connection


def get_all_stock():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                i.item_id,
                s.warehouse_id,
                COALESCE(s.quantity, 0) AS quantity,
                s.item_id IS NOT NULL AS has_stock_record,

                i.item_code,
                i.item_name,
                i.unit_of_measure,
                i.reorder_level,

                w.warehouse_code,
                w.warehouse_name

            FROM inventory_items i
            LEFT JOIN inventory_stock s ON s.item_id = i.item_id
            LEFT JOIN warehouses w ON s.warehouse_id = w.warehouse_id
            WHERE s.item_id IS NOT NULL OR (i.is_active = TRUE
                AND NOT EXISTS (SELECT 1 FROM stock_movements history WHERE history.item_id=i.item_id))

            ORDER BY
                i.item_name,
                w.warehouse_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


class _RetryableStockError(Exception):
    """Only a pre-commit lock failure with a confirmed rollback may retry."""


@dataclass(frozen=True)
class StockResult:
    movement_id: int
    created: bool


def _existing_submission(cursor, submission_id, item_id, warehouse_id, quantity, notes, created_by, incoming, *, current=False):
    cursor.execute("SELECT movement_id,item_id,warehouse_id,movement_type,quantity,notes,created_by,reference_type "
                   "FROM stock_movements WHERE submission_id = %s" + (" FOR UPDATE" if current else ""), (submission_id,))
    row = cursor.fetchone()
    if not row:
        return None
    expected = (item_id, warehouse_id, 'IN' if incoming else 'OUT', quantity, notes or None,
                created_by, 'MANUAL_STOCK_IN' if incoming else 'MANUAL_STOCK_OUT')
    actual = (row['item_id'], row['warehouse_id'], row['movement_type'], row['quantity'],
              row['notes'] or None, row['created_by'], row['reference_type'])
    if actual != expected:
        raise ValueError("This submission identifier was already used for different stock transaction details. Use a new form only for a separate transaction.")
    return StockResult(row['movement_id'], created=False)


def stock_in(item_id, warehouse_id, quantity, notes, created_by, submission_id=None):
    return _write_stock(item_id, warehouse_id, quantity, notes, created_by, incoming=True, submission_id=submission_id)


def stock_out(item_id, warehouse_id, quantity, notes, created_by, submission_id=None):
    return _write_stock(item_id, warehouse_id, quantity, notes, created_by, incoming=False, submission_id=submission_id)


def _write_stock(item_id, warehouse_id, quantity, notes, created_by, *, incoming, submission_id):
    try:
        submission_id = str(uuid.UUID(str(submission_id)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Missing or invalid submission identifier. Retain the original identifier when retrying a transaction.") from None
    quantity = decimal_value(quantity, "Quantity", positive=True)
    validate_notes(notes, "Stock movement notes")
    identifiers = []
    for value, label in ((item_id, "Item"), (warehouse_id, "Warehouse")):
        if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) <= 2147483647:
            raise ValueError(f"{label} must be a valid identifier.")
        identifiers.append(int(value))
    for attempt in range(3):
        try:
            return _stock_transaction(*identifiers, quantity, notes, created_by, incoming=incoming, submission_id=submission_id)
        except _RetryableStockError:
            if attempt == 2:
                raise ValueError("Stock is busy. No changes were saved. Please try again later.") from None
        except mysql.connector.Error as error:
            if error.errno == 1062:
                # A global UUID collision may involve different stock rows.
                try:
                    with get_connection() as connection:
                        cursor = connection.cursor(dictionary=True)
                        try:
                            existing = _existing_submission(cursor, submission_id, *identifiers, quantity,
                                                            notes, created_by, incoming)
                            if existing:
                                return existing
                        finally:
                            cursor.close()
                except mysql.connector.Error as lookup_error:
                    error = lookup_error
            if error.errno in (1054, 1146):
                raise ValueError("Manual stock submission schema is unavailable. Ask an administrator to verify the stock UUID migration before retrying.") from error
            # Do not replay uncertain commits automatically; resolve with the same UUID.
            raise ValueError("Stock transaction could not be confirmed. Check movement history or retry with the same submission identifier; do not open a new form for this transaction.") from error


def _stock_transaction(item_id, warehouse_id, quantity, notes, created_by, *, incoming, submission_id):
    connection = get_connection()
    cursor = None
    committing = False
    try:
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()
        existing = _existing_submission(cursor, submission_id, item_id, warehouse_id, quantity,
                                        notes, created_by, incoming)
        if existing:
            return existing
        for table, key, identifier, label in (
                ("inventory_items", "item_id", item_id, "Inventory item"),
                ("warehouses", "warehouse_id", warehouse_id, "Warehouse")):
            cursor.execute(f"SELECT is_active FROM {table} WHERE {key} = %s FOR SHARE", (identifier,))
            row = cursor.fetchone()
            if not row or not row['is_active']:
                raise ValueError(f"{label} does not exist or is inactive.")
        if incoming:
            # Reserve missing rows using the same atomic strategy as Goods Receiving.
            # This zero-balance reservation is rolled back if validation fails.
            cursor.execute("INSERT INTO inventory_stock (item_id, warehouse_id, quantity) VALUES (%s, %s, 0) "
                           "ON DUPLICATE KEY UPDATE quantity = quantity", (item_id, warehouse_id))
        cursor.execute("SELECT quantity FROM inventory_stock WHERE item_id = %s AND warehouse_id = %s FOR UPDATE",
                       (item_id, warehouse_id))
        stock = cursor.fetchone()
        if not stock:
            raise ValueError("No stock exists for this item in the selected warehouse.")
        # Current read sees a movement committed while this request waited for stock.
        existing = _existing_submission(cursor, submission_id, item_id, warehouse_id, quantity,
                                        notes, created_by, incoming, current=True)
        if existing:
            return existing
        balance = decimal_value(stock['quantity'], "Warehouse stock balance")
        if not incoming and quantity > balance:
            raise ValueError("Insufficient stock. Stock cannot go below zero.")
        balance = decimal_value(balance + quantity if incoming else balance - quantity,
                                "Resulting warehouse stock balance")
        cursor.execute("UPDATE inventory_stock SET quantity = %s WHERE item_id = %s AND warehouse_id = %s",
                       (balance, item_id, warehouse_id))
        cursor.execute("INSERT INTO stock_movements (item_id, warehouse_id, movement_type, quantity, "
                       "reference_type, reference_id, notes, created_by, submission_id) VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s)",
                       (item_id, warehouse_id, 'IN' if incoming else 'OUT', quantity,
                        'MANUAL_STOCK_IN' if incoming else 'MANUAL_STOCK_OUT', notes, created_by, submission_id))
        movement_id = cursor.lastrowid
        committing = True
        connection.commit()
        return StockResult(movement_id, created=True)
    except Exception as error:
        # A failed rollback propagates, rather than allowing an automatic replay.
        connection.rollback()
        if not committing and isinstance(error, mysql.connector.Error) and error.errno in (1205, 1213):
            raise _RetryableStockError() from error
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


def get_stock_movements():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                sm.movement_id,
                sm.movement_type,
                sm.quantity,
                sm.reference_type,
                sm.notes,
                sm.created_at,

                i.item_code,
                i.item_name,
                i.unit_of_measure,

                w.warehouse_code,
                w.warehouse_name,

                u.username AS created_by_username

            FROM stock_movements sm

            JOIN inventory_items i
                ON sm.item_id = i.item_id

            JOIN warehouses w
                ON sm.warehouse_id = w.warehouse_id

            LEFT JOIN users u
                ON sm.created_by = u.user_id

            ORDER BY
                sm.created_at DESC,
                sm.movement_id DESC
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()