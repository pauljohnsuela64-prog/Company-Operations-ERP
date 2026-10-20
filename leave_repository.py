# ==========================================================
# LEAVE MANAGEMENT REPOSITORY
# ==========================================================
from datetime import (
    date,
    timedelta,
)
import uuid
from contextlib import contextmanager
import logging
from mysql.connector import Error
from leave_validation import LeaveError, identifier, request_values, text, type_values, listing_values

from database import get_connection


# ==========================================================
# GET ALL LEAVE TYPES
# ==========================================================

def get_all_leave_types():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                leave_type_id,
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid,
                is_active,
                created_at,
                updated_at

            FROM leave_types

            ORDER BY
                leave_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ACTIVE LEAVE TYPES
# ==========================================================

def get_active_leave_types():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                leave_type_id,
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid

            FROM leave_types

            WHERE is_active = 1

            ORDER BY
                leave_name
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET LEAVE TYPE BY ID
# ==========================================================

def get_leave_type_by_id(
    leave_type_id,
):

    leave_type_id = identifier(leave_type_id, 'Leave type')
    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                leave_type_id,
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid,
                is_active,
                created_at,
                updated_at

            FROM leave_types

            WHERE leave_type_id = %s
            """,
            (
                leave_type_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE LEAVE TYPE
# ==========================================================

def create_leave_type(leave_code, leave_name, description, annual_entitlement, is_paid):
    data = type_values(dict(leave_code=leave_code, leave_name=leave_name, description=description, annual_entitlement=annual_entitlement, is_paid=is_paid))
    with _transaction() as cursor:
        cursor.execute('INSERT INTO leave_types(leave_code,leave_name,description,annual_entitlement,is_paid) VALUES(%s,%s,%s,%s,%s)', tuple(data.values()))
        identity = cursor.lastrowid
    return identity


# ==========================================================
# UPDATE LEAVE TYPE
# ==========================================================

def update_leave_type(leave_type_id, leave_code, leave_name, description, annual_entitlement, is_paid):
    identity = identifier(leave_type_id, 'Leave type')
    data = type_values(dict(leave_code=leave_code, leave_name=leave_name, description=description, annual_entitlement=annual_entitlement, is_paid=is_paid))
    with _transaction() as cursor:
        cursor.execute('SELECT leave_type_id FROM leave_types WHERE leave_type_id=%s FOR UPDATE', (identity,))
        if cursor.fetchone() is None:
            raise LeaveError('Leave type not found.', 404)
        cursor.execute('UPDATE leave_types SET leave_code=%s,leave_name=%s,description=%s,annual_entitlement=%s,is_paid=%s WHERE leave_type_id=%s', (*data.values(), identity))


# ==========================================================
# CHANGE LEAVE TYPE STATUS
# ==========================================================

def set_leave_type_active_status(leave_type_id, is_active):
    identity = identifier(leave_type_id, 'Leave type')
    if type(is_active) is not bool:
        raise LeaveError('Invalid leave type status.')
    with _transaction() as cursor:
        cursor.execute('SELECT leave_type_id FROM leave_types WHERE leave_type_id=%s FOR UPDATE', (identity,))
        if cursor.fetchone() is None:
            raise LeaveError('Leave type not found.', 404)
        cursor.execute('UPDATE leave_types SET is_active=%s WHERE leave_type_id=%s', (is_active, identity))


# ==========================================================
# GET ALL LEAVE REQUESTS
# ==========================================================

def get_all_leave_requests():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                lr.leave_request_id,
                lr.request_number,
                lr.employee_id,
                lr.leave_type_id,
                lr.start_date,
                lr.end_date,
                lr.total_days,
                lr.reason,
                lr.status,
                lr.requested_by,
                lr.reviewed_by,
                lr.reviewed_at,
                lr.rejection_reason,
                lr.created_at,
                lr.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                lt.leave_code,
                lt.leave_name,
                lt.is_paid,

                requester.username
                    AS requested_by_username,

                reviewer.username
                    AS reviewed_by_username

            FROM leave_requests lr

            INNER JOIN employees e
                ON lr.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN leave_types lt
                ON lr.leave_type_id = lt.leave_type_id

            INNER JOIN users requester
                ON lr.requested_by = requester.user_id

            LEFT JOIN users reviewer
                ON lr.reviewed_by = reviewer.user_id

            ORDER BY
                lr.created_at DESC,
                lr.leave_request_id DESC
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET LEAVE REQUEST BY ID
# ==========================================================

def get_leave_request_by_id(
    leave_request_id,
):

    leave_request_id = identifier(leave_request_id, 'Leave request')
    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                lr.leave_request_id,
                lr.request_number,
                lr.employee_id,
                lr.leave_type_id,
                lr.start_date,
                lr.end_date,
                lr.total_days,
                lr.reason,
                lr.status,
                lr.requested_by,
                lr.reviewed_by,
                lr.reviewed_at,
                lr.rejection_reason,
                lr.created_at,
                lr.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                lt.leave_code,
                lt.leave_name,
                lt.is_paid,

                requester.username
                    AS requested_by_username,

                reviewer.username
                    AS reviewed_by_username

            FROM leave_requests lr

            INNER JOIN employees e
                ON lr.employee_id = e.employee_id

            LEFT JOIN departments d
                ON e.department_id = d.department_id

            INNER JOIN leave_types lt
                ON lr.leave_type_id = lt.leave_type_id

            INNER JOIN users requester
                ON lr.requested_by = requester.user_id

            LEFT JOIN users reviewer
                ON lr.reviewed_by = reviewer.user_id

            WHERE lr.leave_request_id = %s
            """,
            (
                leave_request_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CHECK OVERLAPPING LEAVE
# ==========================================================

def has_overlapping_leave_request(
    employee_id,
    start_date,
    end_date,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total

            FROM leave_requests

            WHERE
                employee_id = %s

                AND status IN (
                    'PENDING',
                    'APPROVED'
                )

                AND start_date <= %s

                AND end_date >= %s
            """,
            (
                employee_id,
                end_date,
                start_date,
            ),
        )

        result = cursor.fetchone()

        return result["total"] > 0

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# LEAVE BALANCES - EXISTING EMPLOYEE / YEAR CALCULATION
# ==========================================================

def get_employee_leave_balances(
    employee_id,
    year,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        # ==================================================
        # YEAR RANGE
        # ==========================================================

        year_start = date(
            year,
            1,
            1,
        )

        year_end = date(
            year,
            12,
            31,
        )


        # ==================================================
        # GET LEAVE TYPES + APPROVED USAGE
        #
        # The DATEDIFF calculation only counts the portion
        # of a request that falls inside the selected year.
        #
        # This also supports a leave request that crosses
        # from December into January.
        # ==========================================================

        cursor.execute(
            """
            SELECT
                lt.leave_type_id,
                lt.leave_code,
                lt.leave_name,
                lt.description,
                lt.annual_entitlement,
                lt.is_paid,
                lt.is_active,

                COALESCE(
                    SUM(
                        CASE

                            WHEN
                                lr.status = 'APPROVED'
                                AND lr.start_date <= %s
                                AND lr.end_date >= %s

                            THEN
                                DATEDIFF(
                                    LEAST(
                                        lr.end_date,
                                        %s
                                    ),
                                    GREATEST(
                                        lr.start_date,
                                        %s
                                    )
                                ) + 1

                            ELSE 0

                        END
                    ),
                    0
                ) AS used_days

            FROM leave_types lt

            LEFT JOIN leave_requests lr
                ON lt.leave_type_id = lr.leave_type_id
                AND lr.employee_id = %s

            GROUP BY
                lt.leave_type_id,
                lt.leave_code,
                lt.leave_name,
                lt.description,
                lt.annual_entitlement,
                lt.is_paid,
                lt.is_active

            ORDER BY
                lt.leave_name
            """,
            (
                year_end,
                year_start,
                year_end,
                year_start,
                employee_id,
            ),
        )


        balances = cursor.fetchall()


        # ==================================================
        # CALCULATE REMAINING BALANCE
        # ==========================================================

        for balance in balances:

            if (
                balance[
                    "annual_entitlement"
                ]
                is None
            ):

                # ==========================================
                # NO FIXED LIMIT
                # ==========================================

                balance[
                    "remaining_days"
                ] = None

            else:

                balance[
                    "remaining_days"
                ] = (
                    balance[
                        "annual_entitlement"
                    ]
                    - balance[
                        "used_days"
                    ]
                )


        return balances


    finally:

        cursor.close()
        connection.close()

# ==========================================================
# LEAVE REPORTS - EXISTING SUMMARY
# ==========================================================

def get_leave_report_summary(
    year,
    status=None,
    employee_id=None,
    leave_type_id=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        year_start = date(
            year,
            1,
            1,
        )

        year_end = date(
            year,
            12,
            31,
        )


        query = """
            SELECT
                COUNT(*) AS total_requests,

                COALESCE(
                    SUM(status = 'PENDING'),
                    0
                ) AS pending_count,

                COALESCE(
                    SUM(status = 'APPROVED'),
                    0
                ) AS approved_count,

                COALESCE(
                    SUM(status = 'REJECTED'),
                    0
                ) AS rejected_count,

                COALESCE(
                    SUM(status = 'CANCELLED'),
                    0
                ) AS cancelled_count,

                COALESCE(
                    SUM(
                        CASE

                            WHEN status = 'APPROVED'

                            THEN
                                DATEDIFF(
                                    LEAST(
                                        end_date,
                                        %s
                                    ),
                                    GREATEST(
                                        start_date,
                                        %s
                                    )
                                ) + 1

                            ELSE 0

                        END
                    ),
                    0
                ) AS approved_days

            FROM leave_requests

            WHERE
                start_date <= %s
                AND end_date >= %s
        """


        parameters = [
            year_end,
            year_start,
            year_end,
            year_start,
        ]


        # ==================================================
        # STATUS FILTER
        # ==========================================================

        if status:

            query += """
                AND status = %s
            """

            parameters.append(
                status
            )


        # ==================================================
        # EMPLOYEE FILTER
        # ==========================================================

        if employee_id:

            query += """
                AND employee_id = %s
            """

            parameters.append(
                employee_id
            )


        # ==================================================
        # LEAVE TYPE FILTER
        # ==========================================================

        if leave_type_id:

            query += """
                AND leave_type_id = %s
            """

            parameters.append(
                leave_type_id
            )


        cursor.execute(
            query,
            tuple(parameters),
        )


        return cursor.fetchone()


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# LEAVE REPORTS - BY LEAVE TYPE
# ==========================================================

def get_leave_report_by_type(
    year,
    status=None,
    employee_id=None,
    leave_type_id=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        year_start = date(
            year,
            1,
            1,
        )

        year_end = date(
            year,
            12,
            31,
        )


        query = """
            SELECT
                lt.leave_type_id,
                lt.leave_code,
                lt.leave_name,

                COUNT(
                    lr.leave_request_id
                ) AS total_requests,

                COALESCE(
                    SUM(lr.status = 'PENDING'),
                    0
                ) AS pending_count,

                COALESCE(
                    SUM(lr.status = 'APPROVED'),
                    0
                ) AS approved_count,

                COALESCE(
                    SUM(lr.status = 'REJECTED'),
                    0
                ) AS rejected_count,

                COALESCE(
                    SUM(lr.status = 'CANCELLED'),
                    0
                ) AS cancelled_count,

                COALESCE(
                    SUM(
                        CASE

                            WHEN lr.status = 'APPROVED'

                            THEN
                                DATEDIFF(
                                    LEAST(
                                        lr.end_date,
                                        %s
                                    ),
                                    GREATEST(
                                        lr.start_date,
                                        %s
                                    )
                                ) + 1

                            ELSE 0

                        END
                    ),
                    0
                ) AS approved_days

            FROM leave_requests lr

            INNER JOIN leave_types lt
                ON lr.leave_type_id
                = lt.leave_type_id

            WHERE
                lr.start_date <= %s
                AND lr.end_date >= %s
        """


        parameters = [
            year_end,
            year_start,
            year_end,
            year_start,
        ]


        if status:

            query += """
                AND lr.status = %s
            """

            parameters.append(
                status
            )


        if employee_id:

            query += """
                AND lr.employee_id = %s
            """

            parameters.append(
                employee_id
            )


        if leave_type_id:

            query += """
                AND lr.leave_type_id = %s
            """

            parameters.append(
                leave_type_id
            )


        query += """
            GROUP BY
                lt.leave_type_id,
                lt.leave_code,
                lt.leave_name

            ORDER BY
                lt.leave_name
        """


        cursor.execute(
            query,
            tuple(parameters),
        )


        return cursor.fetchall()


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# LEAVE REPORTS - DETAILED RECORDS
# ==========================================================

def get_leave_report_records(
    year,
    status=None,
    employee_id=None,
    leave_type_id=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        year_start = date(
            year,
            1,
            1,
        )

        year_end = date(
            year,
            12,
            31,
        )


        query = """
            SELECT
                lr.leave_request_id,
                lr.request_number,
                lr.employee_id,
                lr.leave_type_id,
                lr.start_date,
                lr.end_date,
                lr.total_days,
                lr.reason,
                lr.status,
                lr.reviewed_at,
                lr.rejection_reason,
                lr.created_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,

                d.department_name,

                lt.leave_code,
                lt.leave_name,
                lt.is_paid,

                requester.username
                    AS requested_by_username,

                reviewer.username
                    AS reviewed_by_username

            FROM leave_requests lr

            INNER JOIN employees e
                ON lr.employee_id
                = e.employee_id

            LEFT JOIN departments d
                ON e.department_id
                = d.department_id

            INNER JOIN leave_types lt
                ON lr.leave_type_id
                = lt.leave_type_id

            INNER JOIN users requester
                ON lr.requested_by
                = requester.user_id

            LEFT JOIN users reviewer
                ON lr.reviewed_by
                = reviewer.user_id

            WHERE
                lr.start_date <= %s
                AND lr.end_date >= %s
        """


        parameters = [
            year_end,
            year_start,
        ]


        if status:

            query += """
                AND lr.status = %s
            """

            parameters.append(
                status
            )


        if employee_id:

            query += """
                AND lr.employee_id = %s
            """

            parameters.append(
                employee_id
            )


        if leave_type_id:

            query += """
                AND lr.leave_type_id = %s
            """

            parameters.append(
                leave_type_id
            )


        query += """
            ORDER BY
                lr.start_date DESC,
                lr.leave_request_id DESC
        """


        cursor.execute(
            query,
            tuple(parameters),
        )


        return cursor.fetchall()


    finally:

        cursor.close()
        connection.close()

@contextmanager
def _transaction(attendance=False):
    connection = get_connection()  # Existing global schema admission remains active.
    cursor = None
    try:
        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        _check_storage(cursor, attendance)
        yield cursor
        connection.commit()
    except Error as error:
        _rollback(connection)
        if error.errno == 1062:
            raise LeaveError('A conflicting record already exists. Reload and verify before retrying.', 409) from None
        if error.errno == 1452:
            raise LeaveError('A referenced employee, leave type or acting user is no longer available.', 409) from None
        if error.errno in (1205, 1213):
            raise LeaveError('Leave records were busy. Reload and verify before retrying.', 409) from None
        raise LeaveError('Could not confirm the save. Reload and verify before retrying.', 503) from error
    except Exception:
        _rollback(connection)
        raise
    finally:
        failed = False
        try:
            if cursor is not None:
                cursor.close()
        except Error:
            failed = True
        try:
            connection.close()
        except Error:
            failed = True
        if failed:
            raise LeaveError('Could not confirm the save. Reload and verify before retrying.', 503) from None


def _rollback(connection):
    try:
        connection.rollback()
    except Error:
        pass  # Lost COMMIT acknowledgment is uncertain, never automatically replayed.


def _check_storage(cursor, attendance=False):
    tables = ['employees', 'leave_types', 'leave_requests']
    if attendance:
        tables.append('attendance_records')
    cursor.execute('SELECT TABLE_NAME, ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN (' + ','.join(['%s'] * len(tables)) + ')', tuple(tables))
    engines = {row['TABLE_NAME']: row['ENGINE'] for row in cursor.fetchall()}
    if any(engines.get(table) != 'InnoDB' for table in tables):
        logging.getLogger(__name__).error('Leave storage incompatible: required InnoDB tables missing or unsupported.')
        raise LeaveError('Leave is temporarily unavailable. Contact an administrator.', 503)
    if attendance:
        from attendance_repository import _check_storage as check_attendance_storage
        from attendance_validation import AttendanceError
        try:
            check_attendance_storage(cursor)
        except AttendanceError:
            raise LeaveError('Leave is temporarily unavailable. Contact an administrator.', 503) from None


def _lock_employee(cursor, employee_id):
    cursor.execute('SELECT employee_id FROM employees WHERE employee_id=%s FOR UPDATE', (employee_id,))
    if cursor.fetchone() is None:
        raise LeaveError('Employee not found.')


def create_leave_request(employee_id, leave_type_id, start_date, end_date, total_days, reason, requested_by):
    data = request_values(dict(employee_id=employee_id, leave_type_id=leave_type_id, start_date=start_date, end_date=end_date, reason=reason))
    if isinstance(total_days, bool) or total_days != data['total_days']:
        raise LeaveError('Total days must match the inclusive calendar-date range.')
    actor = identifier(requested_by, 'User')
    with _transaction() as cursor:
        # Every cooperating create/approval for this employee takes this lock
        # first, including when no overlapping rows exist yet.
        _lock_employee(cursor, data['employee_id'])
        cursor.execute('SELECT is_active FROM leave_types WHERE leave_type_id=%s FOR SHARE', (data['leave_type_id'],))
        leave_type = cursor.fetchone()
        if not leave_type or not leave_type['is_active']:
            raise LeaveError('Selected leave type is invalid or inactive.')
        cursor.execute("SELECT leave_request_id FROM leave_requests WHERE employee_id=%s AND status IN ('PENDING','APPROVED') AND start_date<=%s AND end_date>=%s FOR UPDATE", (data['employee_id'], data['end_date'], data['start_date']))
        if cursor.fetchall():
            raise LeaveError('This employee already has a pending or approved leave request that overlaps the selected dates.', 409)
        cursor.execute("INSERT INTO leave_requests(request_number,employee_id,leave_type_id,start_date,end_date,total_days,reason,status,requested_by) VALUES(%s,%s,%s,%s,%s,%s,%s,'PENDING',%s)", (f'TMP-{uuid.uuid4().hex}', *data.values(), actor))
        identity = cursor.lastrowid
        number = f'LR-{identity:06d}'
        cursor.execute('UPDATE leave_requests SET request_number=%s WHERE leave_request_id=%s', (number, identity))
    return identity, number


def _pending(cursor, identity):
    cursor.execute('SELECT * FROM leave_requests WHERE leave_request_id=%s FOR UPDATE', (identity,))
    row = cursor.fetchone()
    if not row:
        raise LeaveError('Leave request not found.', 404)
    if row['status'] != 'PENDING':
        raise LeaveError('Only pending leave requests can be changed.', 409)
    return row


def approve_leave_request(leave_request_id, reviewed_by):
    """The single effective approval: existing yearly balance and Attendance rules."""
    identity, actor = identifier(leave_request_id, 'Leave request'), identifier(reviewed_by, 'User')
    with _transaction(attendance=True) as cursor:
        cursor.execute('SELECT employee_id FROM leave_requests WHERE leave_request_id=%s', (identity,))
        reference = cursor.fetchone()
        if not reference:
            raise LeaveError('Leave request not found.', 404)
        _lock_employee(cursor, reference['employee_id'])
        # Lock the referenced type/request in this transaction. The Employee
        # lock serializes cooperating creates/approvals; re-read pending state
        # to catch concurrent cancellation/rejection.
        cursor.execute('SELECT lt.* FROM leave_types lt JOIN leave_requests lr ON lr.leave_type_id=lt.leave_type_id WHERE lr.leave_request_id=%s FOR UPDATE', (identity,))
        leave_type = cursor.fetchone()
        row = _pending(cursor, identity)
        if row['employee_id'] != reference['employee_id'] or not leave_type or row['leave_type_id'] != leave_type['leave_type_id']:
            raise LeaveError('Leave references changed. Reload before retrying.', 409)
        start, end = row['start_date'], row['end_date']
        if (type(start) is not date or type(end) is not date or start.year < 1000
                or end.year < 1000 or end < start or (end - start).days + 1 > 999):
            raise LeaveError('Stored leave dates exceed valid storage limits. Contact an administrator.', 409)
        annual = leave_type['annual_entitlement']
        if annual is not None:
            for year in range(start.year, end.year + 1):
                lower, upper = date(year, 1, 1), date(year, 12, 31)
                requested = (min(end, upper) - max(start, lower)).days + 1
                cursor.execute("SELECT start_date,end_date FROM leave_requests WHERE employee_id=%s AND leave_type_id=%s AND status='APPROVED' AND leave_request_id<>%s AND start_date<=%s AND end_date>=%s FOR UPDATE", (row['employee_id'], row['leave_type_id'], identity, upper, lower))
                used = sum((min(r['end_date'], upper) - max(r['start_date'], lower)).days + 1 for r in cursor.fetchall())
                if requested > annual - used:
                    raise LeaveError(f"Insufficient {leave_type['leave_name']} balance for {year}. Entitlement: {annual} day(s), Used: {used} day(s), Remaining: {annual-used} day(s), Requested: {requested} day(s).", 409)
        # Inclusive offsets avoid incrementing beyond MySQL's maximum DATE.
        missing = []
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            cursor.execute('SELECT attendance_id,status FROM attendance_records WHERE employee_id=%s AND attendance_date=%s FOR UPDATE', (row['employee_id'], day))
            attendance = cursor.fetchone()
            if attendance and attendance['status'] != 'ON_LEAVE':
                raise LeaveError(f"Approval blocked. The employee already has an attendance record for {day} with status {attendance['status']}.", 409)
            if not attendance:
                missing.append(day)
        for day in missing:
            cursor.execute("INSERT INTO attendance_records(employee_id,attendance_date,time_in,time_out,status,notes,created_by) VALUES(%s,%s,NULL,NULL,'ON_LEAVE',%s,%s)", (row['employee_id'], day, f"Approved leave {row['request_number']} - {leave_type['leave_name']}", actor))
        cursor.execute("UPDATE leave_requests SET status='APPROVED',reviewed_by=%s,reviewed_at=NOW(),rejection_reason=NULL WHERE leave_request_id=%s", (actor, identity))


def reject_leave_request(leave_request_id, reviewed_by, rejection_reason):
    identity, actor = identifier(leave_request_id, 'Leave request'), identifier(reviewed_by, 'User')
    reason = text(rejection_reason, 'Rejection reason', 500, True)
    with _transaction() as cursor:
        _pending(cursor, identity)
        cursor.execute("UPDATE leave_requests SET status='REJECTED',reviewed_by=%s,reviewed_at=NOW(),rejection_reason=%s WHERE leave_request_id=%s", (actor, reason, identity))


def cancel_leave_request(leave_request_id):
    identity = identifier(leave_request_id, 'Leave request')
    with _transaction() as cursor:
        _pending(cursor, identity)
        cursor.execute("UPDATE leave_requests SET status='CANCELLED' WHERE leave_request_id=%s", (identity,))


def get_leave_request_page(filters):
    selected = listing_values(filters)
    where, params = ['1=1'], []
    if selected['search']:
        literal = '%' + selected['search'].replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        columns = ('lr.request_number','e.employee_number','e.first_name','e.last_name',"CONCAT(e.first_name,' ',e.last_name)",'lt.leave_name')
        where.append('(' + ' OR '.join(column + " LIKE %s ESCAPE '!'" for column in columns) + ')')
        params.extend([literal] * len(columns))
    for key, column in (('status','lr.status'),('leave_type_id','lr.leave_type_id'),('department_id','e.department_id')):
        if selected[key]:
            where.append(column + '=%s'); params.append(selected[key])
    for key, comparison in (('date_from','lr.end_date>=%s'),('date_to','lr.start_date<=%s')):
        if selected[key]:
            where.append(comparison); params.append(selected[key])
    joins = ' FROM leave_requests lr JOIN employees e ON e.employee_id=lr.employee_id JOIN leave_types lt ON lt.leave_type_id=lr.leave_type_id WHERE ' + ' AND '.join(where)
    connection = get_connection()
    cursor = None
    try:
        connection.start_transaction(isolation_level='REPEATABLE READ', readonly=True, consistent_snapshot=True)
        cursor = connection.cursor(dictionary=True)
        _check_storage(cursor)
        cursor.execute('SELECT COUNT(*) AS total,' + ','.join("COALESCE(SUM(lr.status='" + status + "'),0) AS " + status.lower() for status in ('PENDING','APPROVED','REJECTED','CANCELLED')) + joins, tuple(params))
        summary = cursor.fetchone()
        pages = max(1, (summary['total'] + selected['page_size'] - 1) // selected['page_size'])
        selected['page'] = min(selected['page'], pages)
        cursor.execute('SELECT lr.*,e.employee_number,e.first_name,e.last_name,lt.leave_name' + joins + ' ORDER BY lr.created_at DESC,lr.leave_request_id DESC LIMIT %s OFFSET %s', (*params, selected['page_size'], (selected['page']-1)*selected['page_size']))
        return dict(records=cursor.fetchall(), summary=summary, pages=pages, **selected)
    finally:
        try:
            connection.rollback()
        finally:
            try:
                if cursor is not None: cursor.close()
            finally:
                connection.close()
