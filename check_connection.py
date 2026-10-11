from database import get_connection


REQUIRED_TABLES = {
    "roles",
    "permissions",
    "role_permissions",
    "departments",
    "employees",
    "users",
}


def main():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT DATABASE()")
        database_name = cursor.fetchone()[0]

        cursor.execute("SHOW TABLES")
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing_tables = REQUIRED_TABLES - existing_tables

        print(f"Connected database: {database_name}")

        if missing_tables:
            print("Database connection successful, but tables are missing:")
            for table in sorted(missing_tables):
                print(f"- {table}")
            return

        print("Database connection successful!")
        print("All required core ERP tables are available.")

    except Exception as error:
        print(f"Database check failed: {error}")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()