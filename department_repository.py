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