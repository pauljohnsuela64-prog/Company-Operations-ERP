# ==========================================================
# LEAVE MANAGEMENT REPOSITORY
# ==========================================================
from datetime import timedelta
import uuid

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

def create_leave_type(
    leave_code,
    leave_name,
    description,
    annual_entitlement,
    is_paid,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO leave_types (
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid,
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
# UPDATE LEAVE TYPE
# ==========================================================

def update_leave_type(
    leave_type_id,
    leave_code,
    leave_name,
    description,
    annual_entitlement,
    is_paid,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE leave_types

            SET
                leave_code = %s,
                leave_name = %s,
                description = %s,
                annual_entitlement = %s,
                is_paid = %s

            WHERE leave_type_id = %s
            """,
            (
                leave_code,
                leave_name,
                description,
                annual_entitlement,
                is_paid,
                leave_type_id,
            ),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CHANGE LEAVE TYPE STATUS
# ==========================================================

def set_leave_type_active_status(
    leave_type_id,
    is_active,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        cursor.execute(
            """
            UPDATE leave_types
            SET is_active = %s
            WHERE leave_type_id = %s
            """,
            (
                is_active,
                leave_type_id,
            ),
        )

        connection.commit()

    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()


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
# CREATE LEAVE REQUEST
# ==========================================================

def create_leave_request(
    employee_id,
    leave_type_id,
    start_date,
    end_date,
    total_days,
    reason,
    requested_by,
):

    connection = get_connection()

    cursor = connection.cursor()

    try:

        # ==================================================
        # TEMPORARY UNIQUE NUMBER
        # ==========================================================

        temporary_number = (
            f"TMP-{uuid.uuid4().hex}"
        )


        cursor.execute(
            """
            INSERT INTO leave_requests (
                request_number,
                employee_id,
                leave_type_id,
                start_date,
                end_date,
                total_days,
                reason,
                status,
                requested_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                'PENDING',
                %s
            )
            """,
            (
                temporary_number,
                employee_id,
                leave_type_id,
                start_date,
                end_date,
                total_days,
                reason,
                requested_by,
            ),
        )


        leave_request_id = (
            cursor.lastrowid
        )


        # ==================================================
        # FINAL REQUEST NUMBER
        # ==========================================================

        request_number = (
            f"LR-{leave_request_id:06d}"
        )


        cursor.execute(
            """
            UPDATE leave_requests

            SET request_number = %s

            WHERE leave_request_id = %s
            """,
            (
                request_number,
                leave_request_id,
            ),
        )


        connection.commit()


        return (
            leave_request_id,
            request_number,
        )


    except Exception:

        connection.rollback()
        raise

    finally:

        cursor.close()
        connection.close()

# ==========================================================
# LEAVE MANAGEMENT - APPROVE REQUEST
#
# Approval also creates ON_LEAVE attendance records.
# Existing non-leave attendance is never overwritten.
# ==========================================================

def approve_leave_request(
    leave_request_id,
    reviewed_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK AND GET REQUEST
        # ==========================================================

        cursor.execute(
            """
            SELECT
                lr.leave_request_id,
                lr.request_number,
                lr.employee_id,
                lr.start_date,
                lr.end_date,
                lr.status,

                lt.leave_name

            FROM leave_requests lr

            INNER JOIN leave_types lt
                ON lr.leave_type_id = lt.leave_type_id

            WHERE lr.leave_request_id = %s

            FOR UPDATE
            """,
            (
                leave_request_id,
            ),
        )


        leave_request = (
            cursor.fetchone()
        )


        if not leave_request:

            raise ValueError(
                "Leave request not found."
            )


        if (
            leave_request["status"]
            != "PENDING"
        ):

            raise ValueError(
                (
                    "Only pending leave requests "
                    "can be approved."
                )
            )


        # ==================================================
        # CHECK ALL ATTENDANCE DATES FIRST
        #
        # We validate everything before writing anything.
        # ==========================================================

        current_date = (
            leave_request["start_date"]
        )

        end_date = (
            leave_request["end_date"]
        )


        while current_date <= end_date:

            cursor.execute(
                """
                SELECT
                    attendance_id,
                    status

                FROM attendance_records

                WHERE
                    employee_id = %s
                    AND attendance_date = %s

                FOR UPDATE
                """,
                (
                    leave_request[
                        "employee_id"
                    ],
                    current_date,
                ),
            )


            attendance = (
                cursor.fetchone()
            )


            if (
                attendance
                and attendance["status"]
                != "ON_LEAVE"
            ):

                raise ValueError(
                    (
                        "Approval blocked. The employee "
                        "already has an attendance record "
                        f"for {current_date} with status "
                        f"{attendance['status']}."
                    )
                )


            current_date += timedelta(
                days=1
            )


        # ==================================================
        # CREATE ON_LEAVE ATTENDANCE
        # ==========================================================

        current_date = (
            leave_request["start_date"]
        )


        while current_date <= end_date:

            cursor.execute(
                """
                SELECT
                    attendance_id

                FROM attendance_records

                WHERE
                    employee_id = %s
                    AND attendance_date = %s

                FOR UPDATE
                """,
                (
                    leave_request[
                        "employee_id"
                    ],
                    current_date,
                ),
            )


            attendance = (
                cursor.fetchone()
            )


            # ==============================================
            # ONLY CREATE IF NONE EXISTS
            # ==============================================

            if not attendance:

                notes = (
                    f"Approved leave "
                    f"{leave_request['request_number']} "
                    f"- {leave_request['leave_name']}"
                )


                cursor.execute(
                    """
                    INSERT INTO attendance_records (
                        employee_id,
                        attendance_date,
                        time_in,
                        time_out,
                        status,
                        notes,
                        created_by
                    )
                    VALUES (
                        %s,
                        %s,
                        NULL,
                        NULL,
                        'ON_LEAVE',
                        %s,
                        %s
                    )
                    """,
                    (
                        leave_request[
                            "employee_id"
                        ],
                        current_date,
                        notes,
                        reviewed_by,
                    ),
                )


            current_date += timedelta(
                days=1
            )


        # ==================================================
        # APPROVE LEAVE REQUEST
        # ==========================================================

        cursor.execute(
            """
            UPDATE leave_requests

            SET
                status = 'APPROVED',
                reviewed_by = %s,
                reviewed_at = NOW(),
                rejection_reason = NULL

            WHERE leave_request_id = %s
            """,
            (
                reviewed_by,
                leave_request_id,
            ),
        )


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# LEAVE MANAGEMENT - REJECT REQUEST
# ==========================================================

def reject_leave_request(
    leave_request_id,
    reviewed_by,
    rejection_reason,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK REQUEST
        # ==========================================================

        cursor.execute(
            """
            SELECT
                leave_request_id,
                status

            FROM leave_requests

            WHERE leave_request_id = %s

            FOR UPDATE
            """,
            (
                leave_request_id,
            ),
        )


        leave_request = (
            cursor.fetchone()
        )


        if not leave_request:

            raise ValueError(
                "Leave request not found."
            )


        if (
            leave_request["status"]
            != "PENDING"
        ):

            raise ValueError(
                (
                    "Only pending leave requests "
                    "can be rejected."
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        cursor.execute(
            """
            UPDATE leave_requests

            SET
                status = 'REJECTED',
                reviewed_by = %s,
                reviewed_at = NOW(),
                rejection_reason = %s

            WHERE leave_request_id = %s
            """,
            (
                reviewed_by,
                rejection_reason,
                leave_request_id,
            ),
        )


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# LEAVE MANAGEMENT - CANCEL REQUEST
# ==========================================================

def cancel_leave_request(
    leave_request_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()


        # ==================================================
        # LOCK REQUEST
        # ==========================================================

        cursor.execute(
            """
            SELECT
                leave_request_id,
                status

            FROM leave_requests

            WHERE leave_request_id = %s

            FOR UPDATE
            """,
            (
                leave_request_id,
            ),
        )


        leave_request = (
            cursor.fetchone()
        )


        if not leave_request:

            raise ValueError(
                "Leave request not found."
            )


        if (
            leave_request["status"]
            != "PENDING"
        ):

            raise ValueError(
                (
                    "Only pending leave requests "
                    "can be cancelled."
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        cursor.execute(
            """
            UPDATE leave_requests

            SET status = 'CANCELLED'

            WHERE leave_request_id = %s
            """,
            (
                leave_request_id,
            ),
        )


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()