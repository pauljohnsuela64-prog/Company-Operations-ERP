# ==========================================================
# ATTENDANCE REPOSITORY
# ==========================================================

import logging

from database import get_connection


# ==========================================================
# GET ALL ATTENDANCE RECORDS
# ==========================================================

def get_all_attendance_records():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                a.attendance_id,
                a.employee_id,
                a.attendance_date,
                a.time_in,
                a.time_out,
                a.status,
                a.notes,
                a.created_by,
                a.updated_by,
                a.created_at,
                a.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                creator.username
                    AS created_by_username,

                updater.username
                    AS updated_by_username

            FROM attendance_records a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN users creator
                ON a.created_by = creator.user_id

            LEFT JOIN users updater
                ON a.updated_by = updater.user_id

            ORDER BY
                a.attendance_date DESC,
                e.last_name,
                e.first_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ATTENDANCE RECORD BY ID
# ==========================================================

def get_attendance_record_by_id(
    attendance_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                a.attendance_id,
                a.employee_id,
                a.attendance_date,
                a.time_in,
                a.time_out,
                a.status,
                a.notes,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name

            FROM attendance_records a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            WHERE a.attendance_id = %s
            """,
            (
                attendance_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE ATTENDANCE RECORD
# ==========================================================

def _check_storage(cursor):
    """Fail closed if a legacy table cannot provide transactions/uniqueness."""
    from attendance_validation import AttendanceError
    cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='attendance_records'")
    row = cursor.fetchone()
    if not row or row['ENGINE'] != 'InnoDB':
        logging.getLogger(__name__).error('Attendance schema incompatible: InnoDB attendance_records required.')
        raise AttendanceError('Attendance is temporarily unavailable. Contact an administrator.', 503)
    cursor.execute("SELECT NON_UNIQUE,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS names,MAX(COALESCE(SUB_PART,0)) AS prefix_length FROM information_schema.statistics WHERE table_schema=DATABASE() AND table_name='attendance_records' GROUP BY INDEX_NAME,NON_UNIQUE")
    if not any(r['NON_UNIQUE'] == 0 and r['names'] == 'employee_id,attendance_date' and not r['prefix_length'] for r in cursor.fetchall()):
        logging.getLogger(__name__).error('Attendance schema incompatible: full Employee/date unique index required.')
        raise AttendanceError('Attendance is temporarily unavailable. Contact an administrator.', 503)


def _rollback_attendance(connection):
    from mysql.connector import Error
    try:
        connection.rollback()
    except Error:
        # A lost connection can prevent rollback, especially after a lost COMMIT
        # acknowledgment. Preserve the safe failure; never infer noncommit/retry.
        pass


def _write_attendance(raw, actor, attendance_id=None):
    from attendance_validation import values, identifier, AttendanceError
    from mysql.connector import Error
    data = values(raw)
    actor = identifier(actor, 'User')
    if attendance_id is not None:
        attendance_id = identifier(attendance_id, 'Attendance')
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        _check_storage(cursor)
        if attendance_id is not None:
            cursor.execute('SELECT attendance_id FROM attendance_records WHERE attendance_id=%s FOR UPDATE', (attendance_id,))
            if cursor.fetchone() is None:
                raise AttendanceError('Attendance record not found.', 404)
        # Reference existence is checked inside the write transaction. No new
        # employee-status eligibility policy is inferred from employment status.
        cursor.execute('SELECT employee_id FROM employees WHERE employee_id=%s FOR SHARE', (data['employee_id'],))
        if cursor.fetchone() is None:
            raise AttendanceError('Employee not found.')
        if attendance_id is None:
            cursor.execute('INSERT INTO attendance_records (employee_id,attendance_date,time_in,time_out,status,notes,created_by) VALUES (%s,%s,%s,%s,%s,%s,%s)', (*data.values(), actor))
            attendance_id = cursor.lastrowid
        else:
            cursor.execute('UPDATE attendance_records SET employee_id=%s,attendance_date=%s,time_in=%s,time_out=%s,status=%s,notes=%s,updated_by=%s WHERE attendance_id=%s', (*data.values(), actor, attendance_id))
        connection.commit()
        return attendance_id
    except Error as error:
        _rollback_attendance(connection)
        if error.errno == 1062:
            raise AttendanceError('This employee already has an attendance record for that date.', 409) from None
        if error.errno == 1452:
            raise AttendanceError('Employee or acting user is no longer available. Reload and verify the record.', 409) from None
        if error.errno in (1205, 1213):
            raise AttendanceError('Attendance was busy. Reload and verify before retrying.', 409) from None
        # A failed acknowledgment is not proof that COMMIT failed. Do not retry
        # automatically or emit a success audit when the result is uncertain.
        raise AttendanceError('Could not confirm the save. Reload and verify before retrying.', 503) from error
    except Exception:
        _rollback_attendance(connection)
        raise
    finally:
        cleanup_failed = False
        try:
            if cursor is not None:
                cursor.close()
        except Error:
            cleanup_failed = True
        try:
            connection.close()
        except Error:
            cleanup_failed = True
        if cleanup_failed:
            raise AttendanceError('Could not confirm the save. Reload and verify before retrying.', 503) from None


def create_attendance_record(employee_id, attendance_date, time_in, time_out, status, notes, created_by):
    return _write_attendance(dict(employee_id=employee_id, attendance_date=attendance_date,
        time_in=time_in, time_out=time_out, status=status, notes=notes), created_by)


def update_attendance_record(attendance_id, employee_id, attendance_date, time_in, time_out, status, notes, updated_by):
    return _write_attendance(dict(employee_id=employee_id, attendance_date=attendance_date,
        time_in=time_in, time_out=time_out, status=status, notes=notes), updated_by, attendance_id)


# ==========================================================
# FILTER ATTENDANCE RECORDS
# ==========================================================

def get_filtered_attendance_records(
    search_text=None,
    attendance_date=None,
    status=None,
    department_id=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        query = """
            SELECT
                a.attendance_id,
                a.employee_id,
                a.attendance_date,
                a.time_in,
                a.time_out,
                a.status,
                a.notes,
                a.created_by,
                a.updated_by,
                a.created_at,
                a.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                creator.username
                    AS created_by_username,

                updater.username
                    AS updated_by_username

            FROM attendance_records a

            INNER JOIN employees e
                ON a.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN users creator
                ON a.created_by = creator.user_id

            LEFT JOIN users updater
                ON a.updated_by = updater.user_id

            WHERE 1 = 1
        """

        parameters = []


        # ==================================================
        # SEARCH
        # ==========================================================

        if search_text:

            query += """
                AND (
                    e.employee_number LIKE %s

                    OR e.first_name LIKE %s

                    OR e.middle_name LIKE %s

                    OR e.last_name LIKE %s

                    OR CONCAT(
                        e.first_name,
                        ' ',
                        e.last_name
                    ) LIKE %s

                    OR d.department_name LIKE %s
                )
            """

            search_value = (
                f"%{search_text}%"
            )

            parameters.extend(
                [
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                    search_value,
                ]
            )


        # ==================================================
        # DATE FILTER
        # ==========================================================

        if attendance_date:

            query += """
                AND a.attendance_date = %s
            """

            parameters.append(
                attendance_date
            )


        # ==================================================
        # STATUS FILTER
        # ==========================================================

        if status:

            query += """
                AND a.status = %s
            """

            parameters.append(
                status
            )


        # ==================================================
        # DEPARTMENT FILTER
        # ==========================================================

        if department_id:

            query += """
                AND e.department_id = %s
            """

            parameters.append(
                department_id
            )


        # ==================================================
        # SORTING
        # ==========================================================

        query += """
            ORDER BY
                a.attendance_date DESC,
                e.last_name,
                e.first_name
        """


        cursor.execute(
            query,
            tuple(parameters),
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()

def get_attendance_page(filters):
    """Bounded page plus filtered totals from one read-only snapshot."""
    from attendance_validation import listing_values
    selected = listing_values(filters)
    where = ['1=1']
    params = []
    if selected['search']:
        literal = '%' + selected['search'].replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        where.append("(" + " OR ".join(column + " LIKE %s ESCAPE '!'" for column in
            ('e.employee_number','e.first_name','e.middle_name','e.last_name',"CONCAT(e.first_name,' ',e.last_name)",'d.department_name')) + ")")
        params.extend([literal] * 6)
    for key, column in (('date','a.attendance_date'),('status','a.status'),('department_id','e.department_id')):
        if selected[key]:
            where.append(column + '=%s')
            params.append(selected[key])
    joins = ' FROM attendance_records a JOIN employees e ON e.employee_id=a.employee_id LEFT JOIN departments d ON d.department_id=e.department_id WHERE ' + ' AND '.join(where)
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', readonly=True, consistent_snapshot=True)
        cursor = connection.cursor(dictionary=True)
        _check_storage(cursor)
        cursor.execute("SELECT COUNT(*) AS total," + ','.join("COALESCE(SUM(a.status='"+status+"'),0) AS "+status.lower() for status in ('PRESENT','LATE','ABSENT','ON_LEAVE','HALF_DAY')) + joins, tuple(params))
        summary = cursor.fetchone()
        pages = max(1, (summary['total'] + selected['page_size'] - 1) // selected['page_size'])
        selected['page'] = min(selected['page'], pages)
        cursor.execute('SELECT a.*,e.employee_number,e.first_name,e.middle_name,e.last_name,d.department_name' + joins + ' ORDER BY a.attendance_date DESC,e.last_name,e.first_name,a.attendance_id LIMIT %s OFFSET %s', (*params, selected['page_size'], (selected['page']-1)*selected['page_size']))
        return dict(records=cursor.fetchall(), summary=summary, pages=pages, **selected)
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()
