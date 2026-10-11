from getpass import getpass

from werkzeug.security import generate_password_hash

from database import get_connection


def main():
    username = input("Super Admin username: ").strip()

    new_password = getpass("New password: ")
    confirm_password = getpass("Confirm new password: ")

    if len(new_password) < 8:
        print("Password must be at least 8 characters.")
        return

    if new_password != confirm_password:
        print("Passwords do not match.")
        return

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT u.user_id
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            WHERE u.username = %s
              AND r.role_name = 'Super Admin'
            """,
            (username,),
        )

        user = cursor.fetchone()

        if not user:
            print("Super Admin account not found.")
            return

        password_hash = generate_password_hash(new_password)

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (password_hash, user[0]),
        )

        connection.commit()

        print("Super Admin password reset successfully.")

    except Exception as error:
        if connection:
            connection.rollback()

        print(f"Password reset failed: {error}")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()