from inventory_validation import item_fields, lock_assignment_category
from database import get_connection


def get_all_inventory_items():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                i.item_id,
                i.item_code,
                i.item_name,
                i.category_id,
                i.description,
                i.unit_of_measure,
                i.reorder_level,
                i.is_active,
                c.category_code,
                c.category_name
            FROM inventory_items i
            LEFT JOIN inventory_categories c
                ON i.category_id = c.category_id
            ORDER BY i.item_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_inventory_item_by_id(item_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                item_id,
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                is_active
            FROM inventory_items
            WHERE item_id = %s
            LIMIT 1
            """,
            (item_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_inventory_item(
    item_code,
    item_name,
    category_id,
    description,
    unit_of_measure,
    reorder_level,
):
    item_code, item_name, category_id, description, unit_of_measure, reorder_level = item_fields(
        item_code, item_name, category_id, description, unit_of_measure, reorder_level)
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_assignment_category(cursor, category_id)
        cursor.execute(
            """
            INSERT INTO inventory_items (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
            ),
        )

        item_id = cursor.lastrowid
        connection.commit()
        return item_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def update_inventory_item(
    item_id,
    item_code,
    item_name,
    category_id,
    description,
    unit_of_measure,
    reorder_level,
):
    item_code, item_name, category_id, description, unit_of_measure, reorder_level = item_fields(
        item_code, item_name, category_id, description, unit_of_measure, reorder_level)
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        cursor.execute("SELECT category_id FROM inventory_items WHERE item_id = %s FOR UPDATE", (item_id,))
        existing = cursor.fetchone()
        if not existing:
            raise ValueError("Inventory item no longer exists.")
        lock_assignment_category(cursor, category_id, existing[0])
        cursor.execute(
            """
            UPDATE inventory_items
            SET
                item_code = %s,
                item_name = %s,
                category_id = %s,
                description = %s,
                unit_of_measure = %s,
                reorder_level = %s
            WHERE item_id = %s
            """,
            (
                item_code,
                item_name,
                category_id,
                description,
                unit_of_measure,
                reorder_level,
                item_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def set_inventory_item_active_status(
    item_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE inventory_items
            SET is_active = %s
            WHERE item_id = %s AND is_active <> %s
            """,
            (
                is_active,
                item_id,
                is_active,
            ),
        )

        changed = cursor.rowcount == 1
        connection.commit()
        return changed

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



def get_active_inventory_items():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                item_id,
                item_code,
                item_name,
                unit_of_measure
            FROM inventory_items
            WHERE is_active = TRUE
            ORDER BY item_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()



def get_active_inventory_items():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                item_id,
                item_code,
                item_name,
                unit_of_measure
            FROM inventory_items
            WHERE is_active = TRUE
            ORDER BY item_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()