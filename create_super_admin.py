from getpass import getpass

from werkzeug.security import generate_password_hash

from database import get_connection


def main():
    username = input("Super Admin username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass("Password: ")

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    confirm_password = getpass("Confirm password: ")

    if password != confirm_password:
        print("Passwords do not match.")
        return

    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        # Find the Super Admin role.
        cursor.execute(
            """
            SELECT role_id
            FROM roles
            WHERE role_name = %s
            """,
            ("Super Admin",),
        )

        role = cursor.fetchone()

        if not role:
            print("Super Admin role was not found.")
            return

        role_id = role[0]

        # Prevent duplicate usernames.
        cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE username = %s
            """,
            (username,),
        )

        if cursor.fetchone():
            print("That username already exists.")
            return

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO users (
                employee_id,
                role_id,
                username,
                password_hash,
                is_active
            )
            VALUES (NULL, %s, %s, %s, TRUE)
            """,
            (
                role_id,
                username,
                password_hash,
            ),
        )

        connection.commit()

        print("Super Admin account created successfully.")

    except Exception as error:
        if connection:
            connection.rollback()

        print(f"Account creation failed: {error}")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()