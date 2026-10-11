from database import get_connection


def get_dashboard_summary():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
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

        return {
            "total_employees": employee_summary["total_employees"],
            "active_employees": employee_summary["active_employees"],
            "non_active_employees": employee_summary["non_active_employees"],
            "total_departments": department_summary["total_departments"],
            "active_departments": department_summary["active_departments"],
        }

    finally:
        cursor.close()
        connection.close()