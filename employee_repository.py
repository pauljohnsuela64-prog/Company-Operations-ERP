from database import get_connection


def get_all_employees():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.email,
                e.phone,
                e.job_title,
                e.hire_date,
                e.employment_status,
                d.department_code,
                d.department_name
            FROM employees e
            LEFT JOIN departments d
                ON e.department_id = d.department_id
            ORDER BY e.last_name, e.first_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def create_employee(
    employee_number,
    department_id,
    first_name,
    middle_name,
    last_name,
    email,
    phone,
    job_title,
    hire_date,
):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO employees (
                employee_number,
                department_id,
                first_name,
                middle_name,
                last_name,
                email,
                phone,
                job_title,
                hire_date,
                employment_status
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, 'Active'
            )
            """,
            (
                employee_number,
                department_id,
                first_name,
                middle_name,
                last_name,
                email,
                phone,
                job_title,
                hire_date,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()