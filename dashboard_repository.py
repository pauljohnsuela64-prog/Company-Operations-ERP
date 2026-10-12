from database import get_connection


def get_dashboard_summary():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # =====================================================
        # EMPLOYEES
        # =====================================================

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_employees,

                COALESCE(
                    SUM(employment_status = 'Active'),
                    0
                ) AS active_employees,

                COALESCE(
                    SUM(employment_status <> 'Active'),
                    0
                ) AS non_active_employees

            FROM employees
            """
        )

        employee_summary = cursor.fetchone()


        # =====================================================
        # DEPARTMENTS
        # =====================================================

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_departments,

                COALESCE(
                    SUM(is_active = TRUE),
                    0
                ) AS active_departments

            FROM departments
            """
        )

        department_summary = cursor.fetchone()


        # =====================================================
        # INVENTORY ITEMS
        # =====================================================

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_inventory_items

            FROM inventory_items
            """
        )

        inventory_summary = cursor.fetchone()


        # =====================================================
        # LOW STOCK / OUT OF STOCK
        # =====================================================

        cursor.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        total_quantity > 0
                        AND total_quantity <= reorder_level
                    ),
                    0
                ) AS low_stock_items,

                COALESCE(
                    SUM(total_quantity <= 0),
                    0
                ) AS out_of_stock_items

            FROM (
                SELECT
                    i.item_id,
                    i.reorder_level,
                    COALESCE(SUM(s.quantity), 0) AS total_quantity

                FROM inventory_items i

                LEFT JOIN inventory_stock s
                    ON i.item_id = s.item_id

                WHERE i.is_active = TRUE

                GROUP BY
                    i.item_id,
                    i.reorder_level
            ) AS inventory_totals
            """
        )

        stock_summary = cursor.fetchone()


        # =====================================================
        # WAREHOUSES
        # =====================================================

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_warehouses,

                COALESCE(
                    SUM(is_active = TRUE),
                    0
                ) AS active_warehouses

            FROM warehouses
            """
        )

        warehouse_summary = cursor.fetchone()


        return {
            "total_employees":
                employee_summary["total_employees"],

            "active_employees":
                employee_summary["active_employees"],

            "non_active_employees":
                employee_summary["non_active_employees"],

            "total_departments":
                department_summary["total_departments"],

            "active_departments":
                department_summary["active_departments"],

            "total_inventory_items":
                inventory_summary["total_inventory_items"],

            "low_stock_items":
                stock_summary["low_stock_items"],

            "out_of_stock_items":
                stock_summary["out_of_stock_items"],

            "total_warehouses":
                warehouse_summary["total_warehouses"],

            "active_warehouses":
                warehouse_summary["active_warehouses"],
        }

    finally:
        cursor.close()
        connection.close()