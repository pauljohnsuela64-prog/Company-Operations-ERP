from database import get_connection


def get_all_inventory_categories():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name,
                description,
                is_active,
                created_at,
                updated_at
            FROM inventory_categories
            ORDER BY category_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_inventory_category_by_id(category_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                category_id,
                category_code,
                category_name,
                description,
                is_active
            FROM inventory_categories
            WHERE category_id = %s
            LIMIT 1
            """,
            (category_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_inventory_category(
    category_code,
    category_name,
    description=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO inventory_categories (
                category_code,
                category_name,
                description,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            """,
            (
                category_code,
                category_name,
                description,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def update_inventory_category(
    category_id,
    category_code,
    category_name,
    description=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE inventory_categories
            SET
                category_code = %s,
                category_name = %s,
                description = %s
            WHERE category_id = %s
            """,
            (
                category_code,
                category_name,
                description,
                category_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def set_inventory_category_active_status(
    category_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE inventory_categories
            SET is_active = %s
            WHERE category_id = %s
            """,
            (
                is_active,
                category_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()