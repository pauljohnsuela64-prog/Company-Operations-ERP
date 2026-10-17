from inventory_validation import warehouse_fields
from database import get_connection


def get_all_warehouses():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                warehouse_id,
                warehouse_code,
                warehouse_name,
                location,
                is_active,
                created_at,
                updated_at
            FROM warehouses
            ORDER BY warehouse_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_warehouse_by_id(warehouse_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                warehouse_id,
                warehouse_code,
                warehouse_name,
                location,
                is_active
            FROM warehouses
            WHERE warehouse_id = %s
            LIMIT 1
            """,
            (warehouse_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_warehouse(
    warehouse_code,
    warehouse_name,
    location=None,
):
    warehouse_code, warehouse_name, location = warehouse_fields(warehouse_code, warehouse_name, location)
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO warehouses (
                warehouse_code,
                warehouse_name,
                location,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            """,
            (
                warehouse_code,
                warehouse_name,
                location,
            ),
        )

        warehouse_id = cursor.lastrowid
        connection.commit()
        return warehouse_id

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def update_warehouse(
    warehouse_id,
    warehouse_code,
    warehouse_name,
    location=None,
):
    warehouse_code, warehouse_name, location = warehouse_fields(warehouse_code, warehouse_name, location)
    connection = get_connection()
    cursor = connection.cursor()

    try:
        connection.start_transaction()
        cursor.execute("SELECT warehouse_id FROM warehouses WHERE warehouse_id = %s FOR UPDATE", (warehouse_id,))
        if not cursor.fetchone():
            raise ValueError("Warehouse no longer exists.")
        cursor.execute(
            """
            UPDATE warehouses
            SET
                warehouse_code = %s,
                warehouse_name = %s,
                location = %s
            WHERE warehouse_id = %s
            """,
            (
                warehouse_code,
                warehouse_name,
                location,
                warehouse_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def set_warehouse_active_status(
    warehouse_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE warehouses
            SET is_active = %s
            WHERE warehouse_id = %s AND is_active <> %s
            """,
            (
                is_active,
                warehouse_id,
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