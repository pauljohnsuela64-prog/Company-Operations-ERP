from database import get_connection


def get_all_suppliers():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                supplier_id,
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active,
                created_at,
                updated_at
            FROM suppliers
            ORDER BY supplier_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_supplier_by_id(supplier_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                supplier_id,
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active
            FROM suppliers
            WHERE supplier_id = %s
            LIMIT 1
            """,
            (supplier_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_supplier(
    supplier_code,
    supplier_name,
    contact_person=None,
    email=None,
    phone=None,
    address=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO suppliers (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def update_supplier(
    supplier_id,
    supplier_code,
    supplier_name,
    contact_person=None,
    email=None,
    phone=None,
    address=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE suppliers
            SET
                supplier_code = %s,
                supplier_name = %s,
                contact_person = %s,
                email = %s,
                phone = %s,
                address = %s
            WHERE supplier_id = %s
            """,
            (
                supplier_code,
                supplier_name,
                contact_person,
                email,
                phone,
                address,
                supplier_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def set_supplier_active_status(
    supplier_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE suppliers
            SET is_active = %s
            WHERE supplier_id = %s
            """,
            (
                is_active,
                supplier_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()