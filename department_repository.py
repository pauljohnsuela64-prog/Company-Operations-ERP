from database import get_connection
from mysql.connector import Error
from hr_validation import (HRValidationError, department_values, identifier,
                           translate_write_error)


def get_all_departments():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name,
                description,
                is_active,
                created_at,
                updated_at
            FROM departments
            ORDER BY department_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()


def get_department_by_id(department_id):
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name,
                description,
                is_active
            FROM departments
            WHERE department_id = %s
            LIMIT 1
            """,
            (department_id,),
        )

        return cursor.fetchone()

    finally:
        cursor.close()
        connection.close()


def create_department(department_code, department_name, description=None):
    values = department_values(dict(department_code=department_code,
        department_name=department_name, description=description))
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        cursor.execute("""INSERT INTO departments
            (department_code, department_name, description, is_active)
            VALUES (%s,%s,%s,TRUE)""", tuple(values.values()))
        department_id = cursor.lastrowid
        connection.commit()
        return department_id
    except Error as error:
        connection.rollback()
        raise translate_write_error(error, 'Department') from None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def _write_department(department_id, values=None, is_active=None):
    department_id = identifier(department_id, 'Department')
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        cursor.execute('SELECT department_id FROM departments WHERE department_id=%s FOR UPDATE', (department_id,))
        if cursor.fetchone() is None:
            connection.rollback()
            return False
        if values is not None:
            cursor.execute("""UPDATE departments SET department_code=%s,
                department_name=%s, description=%s WHERE department_id=%s""",
                (*values.values(), department_id))
        else:
            cursor.execute('UPDATE departments SET is_active=%s WHERE department_id=%s', (is_active, department_id))
        connection.commit()
        return True
    except Error as error:
        connection.rollback()
        raise translate_write_error(error, 'Department') from None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


def update_department(department_id, department_code, department_name, description=None):
    values = department_values(dict(department_code=department_code,
        department_name=department_name, description=description))
    return _write_department(department_id, values=values)


def set_department_active_status(department_id, is_active):
    if not isinstance(is_active, bool):
        raise HRValidationError('Department status must be active or inactive.')
    return _write_department(department_id, is_active=is_active)


def get_active_departments():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                department_id,
                department_code,
                department_name
            FROM departments
            WHERE is_active = TRUE
            ORDER BY department_name
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()
        connection.close()