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