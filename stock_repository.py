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
                s.item_id,
                s.warehouse_id,
                s.quantity,

                i.item_code,
                i.item_name,
                i.unit_of_measure,
                i.reorder_level,

                w.warehouse_code,
                w.warehouse_name

            FROM inventory_stock s

            JOIN inventory_items i
                ON s.item_id = i.item_id

            JOIN warehouses w
                ON s.warehouse_id = w.warehouse_id

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


def stock_in(item_id, warehouse_id, quantity, notes, created_by):
    _write_stock(item_id, warehouse_id, quantity, notes, created_by, incoming=True)


def stock_out(item_id, warehouse_id, quantity, notes, created_by):
    _write_stock(item_id, warehouse_id, quantity, notes, created_by, incoming=False)


def _write_stock(item_id, warehouse_id, quantity, notes, created_by, *, incoming):
    quantity = decimal_value(quantity, "Quantity", positive=True)
    validate_notes(notes, "Stock movement notes")
    identifiers = []
    for value, label in ((item_id, "Item"), (warehouse_id, "Warehouse")):
        if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) <= 2147483647:
            raise ValueError(f"{label} must be a valid identifier.")
        identifiers.append(int(value))
    for attempt in range(3):
        try:
            return _stock_transaction(*identifiers, quantity, notes, created_by, incoming=incoming)
        except _RetryableStockError:
            if attempt == 2:
                raise ValueError("Stock is busy. No changes were saved. Please try again later.") from None
        except mysql.connector.Error as error:
            # Never retry an uncertain commit: manual submissions have no UUID yet.
            raise ValueError("Stock transaction could not be confirmed. Check movement history before submitting again; contact an administrator if needed.") from error


def _stock_transaction(item_id, warehouse_id, quantity, notes, created_by, *, incoming):
    connection = get_connection()
    cursor = None
    committing = False
    try:
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()
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
        balance = decimal_value(stock['quantity'], "Warehouse stock balance")
        if not incoming and quantity > balance:
            raise ValueError("Insufficient stock. Stock cannot go below zero.")
        balance = decimal_value(balance + quantity if incoming else balance - quantity,
                                "Resulting warehouse stock balance")
        cursor.execute("UPDATE inventory_stock SET quantity = %s WHERE item_id = %s AND warehouse_id = %s",
                       (balance, item_id, warehouse_id))
        cursor.execute("INSERT INTO stock_movements (item_id, warehouse_id, movement_type, quantity, "
                       "reference_type, reference_id, notes, created_by) VALUES (%s,%s,%s,%s,%s,NULL,%s,%s)",
                       (item_id, warehouse_id, 'IN' if incoming else 'OUT', quantity,
                        'MANUAL_STOCK_IN' if incoming else 'MANUAL_STOCK_OUT', notes, created_by))
        committing = True
        connection.commit()
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