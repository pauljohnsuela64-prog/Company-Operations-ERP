from payroll_validation import payroll_money
# ==========================================================
# PAYROLL REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# GET ALL EMPLOYEE COMPENSATION
# ==========================================================

def get_all_employee_compensation():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                c.compensation_id,
                c.employee_id,
                c.pay_type,
                c.basic_rate,
                c.currency_code,
                c.effective_date,
                c.notes,
                c.created_by,
                c.updated_by,
                c.created_at,
                c.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.job_title,
                e.employment_status,

                d.department_name,

                creator.username
                    AS created_by_username,

                updater.username
                    AS updated_by_username

            FROM employee_compensation c

            INNER JOIN employees e
                ON c.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN users creator
                ON c.created_by = creator.user_id

            LEFT JOIN users updater
                ON c.updated_by = updater.user_id

            ORDER BY
                e.last_name,
                e.first_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET COMPENSATION BY ID
# ==========================================================

def get_employee_compensation_by_id(
    compensation_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                c.compensation_id,
                c.employee_id,
                c.pay_type,
                c.basic_rate,
                c.currency_code,
                c.effective_date,
                c.notes,
                c.created_by,
                c.updated_by,
                c.created_at,
                c.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name

            FROM employee_compensation c

            INNER JOIN employees e
                ON c.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            WHERE c.compensation_id = %s
            """,
            (
                compensation_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET COMPENSATION BY EMPLOYEE
# ==========================================================

def get_employee_compensation_by_employee_id(
    employee_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                compensation_id,
                employee_id,
                pay_type,
                basic_rate,
                currency_code,
                effective_date,
                notes,
                created_at,
                updated_at

            FROM employee_compensation

            WHERE employee_id = %s
            """,
            (
                employee_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET EMPLOYEES WITHOUT COMPENSATION
# ==========================================================

def get_employees_without_compensation():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.job_title,
                e.employment_status,

                d.department_name

            FROM employees e

            LEFT JOIN employee_compensation c
                ON e.employee_id = c.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            WHERE c.compensation_id IS NULL

            ORDER BY
                e.last_name,
                e.first_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE EMPLOYEE COMPENSATION
# ==========================================================

def create_employee_compensation(
    employee_id,
    pay_type,
    basic_rate,
    effective_date,
    notes,
    created_by,
):

    basic_rate = payroll_money(basic_rate, "Basic rate")

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO employee_compensation (
                employee_id,
                pay_type,
                basic_rate,
                currency_code,
                effective_date,
                notes,
                created_by
            )
            VALUES (
                %s,
                %s,
                %s,
                'PHP',
                %s,
                %s,
                %s
            )
            """,
            (
                employee_id,
                pay_type,
                basic_rate,
                effective_date,
                notes,
                created_by,
            ),
        )

        connection.commit()

        return cursor.lastrowid

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# UPDATE EMPLOYEE COMPENSATION
# ==========================================================

def update_employee_compensation(
    compensation_id,
    pay_type,
    basic_rate,
    effective_date,
    notes,
    updated_by,
):

    basic_rate = payroll_money(basic_rate, "Basic rate")

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE employee_compensation

            SET
                pay_type = %s,
                basic_rate = %s,
                effective_date = %s,
                notes = %s,
                updated_by = %s

            WHERE compensation_id = %s
            """,
            (
                pay_type,
                basic_rate,
                effective_date,
                notes,
                updated_by,
                compensation_id,
            ),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()