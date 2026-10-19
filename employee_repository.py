from hr_revision import (revision, require_current, require_incrementable, HRWriteResult,
                         HRMissingRecordError)
from database import get_connection
from mysql.connector import Error
from employee_listing import listing_inputs, literal_prefix
from hr_validation import (EMPLOYEE_FIELDS, employee_values, identifier,
                           lock_department, translate_write_error)


def get_employee_page(search='',page=1,page_size=25):
    search,page,page_size=listing_inputs(search,page,page_size)
    where=''
    params=()
    if search:
        where=" WHERE (e.employee_number LIKE %s ESCAPE '!' OR e.first_name LIKE %s ESCAPE '!' OR e.middle_name LIKE %s ESCAPE '!' OR e.last_name LIKE %s ESCAPE '!')"
        params=(literal_prefix(search),)*4
    connection=get_connection()
    cursor=None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ',readonly=True,consistent_snapshot=True)
        cursor=connection.cursor(dictionary=True)
        cursor.execute('SELECT COUNT(*) AS total FROM employees e'+where,params)
        total=cursor.fetchone()['total']
        pages=max(1,(total+page_size-1)//page_size)
        page=min(page,pages)
        cursor.execute('''SELECT e.employee_id,e.employee_number,e.first_name,e.middle_name,
            e.last_name,e.email,e.job_title,e.employment_status,d.department_code,d.department_name
            FROM employees e LEFT JOIN departments d ON e.department_id=d.department_id'''+where+
            ' ORDER BY e.last_name,e.first_name,e.employee_id LIMIT %s OFFSET %s',
            (*params,page_size,(page-1)*page_size))
        return dict(employees=cursor.fetchall(),search=search,page=page,page_size=page_size,
                    total=total,pages=pages)
    finally:
        try:
            if cursor is not None:cursor.close()
        finally:
            try:connection.rollback()
            finally:connection.close()


def get_all_employees():
    connection = get_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                e.employee_id,
                e.revision,
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
                revision,
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
                    last_name, email, phone, job_title, hire_date, employment_status, *, expected_revision):
    expected_revision = revision(expected_revision)
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
        cursor.execute('SELECT department_id, revision FROM employees WHERE employee_id=%s FOR UPDATE', (employee_id,))
        previous = cursor.fetchone()
        if previous is None:
            raise HRMissingRecordError('Employee no longer exists.')
        require_current(previous['revision'], expected_revision)
        require_incrementable(previous['revision'])
        lock_department(cursor, values['department_id'], previous['department_id'])
        cursor.execute("""UPDATE employees SET employee_number=%s, department_id=%s,
            first_name=%s, middle_name=%s, last_name=%s, email=%s, phone=%s,
            job_title=%s, hire_date=%s, employment_status=%s, revision=revision+1
            WHERE employee_id=%s AND revision=%s AND revision<9223372036854775807""",
            (*values.values(), employee_id, expected_revision))
        if cursor.rowcount != 1:
            raise RuntimeError('Employee conditional update failed after locking.')
        connection.commit()
        return HRWriteResult(expected_revision + 1)
    except Error as error:
        connection.rollback()
        raise translate_write_error(error, 'Employee') from None
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()
