from database import get_connection
from mysql.connector import Error
from hr_validation import (EMPLOYEE_FIELDS, employee_values, identifier,
                           lock_department, translate_write_error)


def get_all_employees():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.employee_number,
                e.department_id,
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


def get_employee_by_id(employee_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                employee_id,
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
            FROM employees
            WHERE employee_id = %s
            LIMIT 1
            """,
            (employee_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_employee(employee_number, department_id, first_name, middle_name, last_name,
                    email, phone, job_title, hire_date):
    values = employee_values(dict(zip(EMPLOYEE_FIELDS, (employee_number, department_id,
        first_name, middle_name, last_name, email, phone, job_title, hire_date))))
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        lock_department(cursor, values['department_id'])
        cursor.execute("""INSERT INTO employees
            (employee_number, department_id, first_name, middle_name, last_name,
             email, phone, job_title, hire_date, employment_status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Active')""", tuple(values.values()))
        employee_id = cursor.lastrowid
        connection.commit()
        return employee_id
    except Error as error:
        connection.rollback()
        raise translate_write_error(error, 'Employee') from None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def update_employee(employee_id, employee_number, department_id, first_name, middle_name,
                    last_name, email, phone, job_title, hire_date, employment_status):
    employee_id = identifier(employee_id, 'Employee')
    raw = dict(zip(EMPLOYEE_FIELDS, (employee_number, department_id, first_name,
        middle_name, last_name, email, phone, job_title, hire_date)))
    raw['employment_status'] = employment_status
    values = employee_values(raw, editing=True)
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        # Existing employee first, then department: agrees with IT Asset's
        # asset -> employee -> category -> department order. No asset locks here.
        cursor.execute('SELECT department_id FROM employees WHERE employee_id=%s FOR UPDATE', (employee_id,))
        previous = cursor.fetchone()
        if previous is None:
            connection.rollback()
            return False
        lock_department(cursor, values['department_id'], previous['department_id'])
        cursor.execute("""UPDATE employees SET employee_number=%s, department_id=%s,
            first_name=%s, middle_name=%s, last_name=%s, email=%s, phone=%s,
            job_title=%s, hire_date=%s, employment_status=%s WHERE employee_id=%s""",
            (*values.values(), employee_id))
        connection.commit()
        # True includes a valid no-op update; existence was checked under lock.
        # This is NOT optimistic concurrency protection against stale forms.
        return True
    except Error as error:
        connection.rollback()
        raise translate_write_error(error, 'Employee') from None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
