from database import get_connection


def get_user_by_username(username):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                u.user_id,
                u.username,
                u.password_hash,
                u.is_active,
                u.employee_id,
                r.role_id,
                r.role_name
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.username = %s
            LIMIT 1
            """,
            (username,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def update_last_login(user_id):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE users
            SET last_login_at = NOW()
            WHERE user_id = %s
            """,
            (user_id,),
        )

        connection.commit()

    finally:
        cursor.close()
        connection.close()