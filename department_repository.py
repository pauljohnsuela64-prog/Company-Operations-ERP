from database import get_connection


def get_all_departments():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name,
                description,
                is_active,
                created_at,
                updated_at
            FROM departments
            ORDER BY department_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_department_by_id(department_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name,
                description,
                is_active
            FROM departments
            WHERE department_id = %s
            LIMIT 1
            """,
            (department_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_department(
    department_code,
    department_name,
    description=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO departments (
                department_code,
                department_name,
                description,
                is_active
            )
            VALUES (%s, %s, %s, TRUE)
            """,
            (
                department_code,
                department_name,
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


def update_department(
    department_id,
    department_code,
    department_name,
    description=None,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE departments
            SET
                department_code = %s,
                department_name = %s,
                description = %s
            WHERE department_id = %s
            """,
            (
                department_code,
                department_name,
                description,
                department_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



def set_department_active_status(
    department_id,
    is_active,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE departments
            SET is_active = %s
            WHERE department_id = %s
            """,
            (
                is_active,
                department_id,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


def get_active_departments():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name
            FROM departments
            WHERE is_active = TRUE
            ORDER BY department_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()