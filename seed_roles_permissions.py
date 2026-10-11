from database import get_connection


ROLES = [
    ("Super Admin", "Full system access"),
    ("HR Manager", "Manages employees, attendance, and leave"),
    ("Inventory Manager", "Manages inventory, stock, and warehouses"),
    ("Procurement Manager", "Manages suppliers and purchasing"),
    ("IT Manager", "Manages IT assets and help desk"),
    ("Finance Manager", "Manages expenses and financial reports"),
    ("Employee", "Standard employee access"),
]


PERMISSIONS = [
    ("dashboard.view", "View dashboard"),

    ("employees.view", "View employees"),
    ("employees.create", "Create employees"),
    ("employees.edit", "Edit employees"),

    ("departments.view", "View departments"),
    ("departments.manage", "Manage departments"),

    ("inventory.view", "View inventory"),
    ("inventory.manage", "Manage inventory"),

    ("procurement.view", "View procurement records"),
    ("procurement.manage", "Manage procurement records"),
    ("purchase_requests.approve", "Approve purchase requests"),

    ("it_assets.view", "View IT assets"),
    ("it_assets.manage", "Manage IT assets"),

    ("helpdesk.view", "View help desk tickets"),
    ("helpdesk.manage", "Manage help desk tickets"),

    ("expenses.view", "View expenses"),
    ("expenses.manage", "Manage expenses"),

    ("reports.view", "View reports"),

    ("users.manage", "Manage system users"),
    ("roles.manage", "Manage roles and permissions"),

    ("audit_logs.view", "View audit logs"),
]


ROLE_PERMISSION_MAP = {
    "Super Admin": [permission[0] for permission in PERMISSIONS],

    "HR Manager": [
        "dashboard.view",
        "employees.view",
        "employees.create",
        "employees.edit",
        "departments.view",
        "departments.manage",
        "reports.view",
    ],

    "Inventory Manager": [
        "dashboard.view",
        "inventory.view",
        "inventory.manage",
        "reports.view",
    ],

    "Procurement Manager": [
        "dashboard.view",
        "procurement.view",
        "procurement.manage",
        "purchase_requests.approve",
        "reports.view",
    ],

    "IT Manager": [
        "dashboard.view",
        "it_assets.view",
        "it_assets.manage",
        "helpdesk.view",
        "helpdesk.manage",
        "reports.view",
    ],

    "Finance Manager": [
        "dashboard.view",
        "expenses.view",
        "expenses.manage",
        "reports.view",
    ],

    "Employee": [
        "dashboard.view",
    ],
}


def seed_roles(cursor):
    for role_name, description in ROLES:
        cursor.execute(
            """
            INSERT INTO roles (role_name, description)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description)
            """,
            (role_name, description),
        )


def seed_permissions(cursor):
    for permission_code, description in PERMISSIONS:
        cursor.execute(
            """
            INSERT INTO permissions (permission_code, description)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE
                description = VALUES(description)
            """,
            (permission_code, description),
        )


def assign_permissions(cursor):
    cursor.execute("SELECT role_id, role_name FROM roles")
    roles = {role_name: role_id for role_id, role_name in cursor.fetchall()}

    cursor.execute(
        "SELECT permission_id, permission_code FROM permissions"
    )
    permissions = {
        permission_code: permission_id
        for permission_id, permission_code in cursor.fetchall()
    }

    for role_name, permission_codes in ROLE_PERMISSION_MAP.items():
        role_id = roles[role_name]

        for permission_code in permission_codes:
            permission_id = permissions[permission_code]

            cursor.execute(
                """
                INSERT IGNORE INTO role_permissions (
                    role_id,
                    permission_id
                )
                VALUES (%s, %s)
                """,
                (role_id, permission_id),
            )


def main():
    connection = None
    cursor = None

    try:
        connection = get_connection()
        cursor = connection.cursor()

        seed_roles(cursor)
        seed_permissions(cursor)
        assign_permissions(cursor)

        connection.commit()

        print("Roles and permissions seeded successfully.")

    except Exception as error:
        if connection:
            connection.rollback()

        print(f"Seeding failed: {error}")

    finally:
        if cursor:
            cursor.close()

        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()