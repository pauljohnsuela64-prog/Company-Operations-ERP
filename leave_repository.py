# ==========================================================
# LEAVE MANAGEMENT REPOSITORY
# ==========================================================
from datetime import (
    date,
    timedelta,
)
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

# ==========================================================
# LEAVE BALANCES - EMPLOYEE / YEAR
#
# Balances are calculated from:
#
# Leave Type Annual Entitlement
# minus
# Approved Leave Requests
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
# LEAVE MANAGEMENT - APPROVE REQUEST
#
# Approval:
#
# 1. Validates leave balance
# 2. Protects existing attendance records
# 3. Creates ON_LEAVE attendance
# 4. Marks request APPROVED
#
# All inside one transaction.
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
                lr.leave_type_id,
                lr.start_date,
                lr.end_date,
                lr.total_days,
                lr.status,

                lt.leave_name,
                lt.annual_entitlement

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
        # LEAVE BALANCE PROTECTION
        #
        # NULL entitlement means the leave type currently
        # has no fixed yearly limit.
        # ==========================================================

        annual_entitlement = (
            leave_request[
                "annual_entitlement"
            ]
        )


        if annual_entitlement is not None:

            request_start = (
                leave_request[
                    "start_date"
                ]
            )

            request_end = (
                leave_request[
                    "end_date"
                ]
            )


            # ==============================================
            # CHECK EVERY CALENDAR YEAR TOUCHED BY REQUEST
            # ==============================================

            current_year = (
                request_start.year
            )


            while (
                current_year
                <= request_end.year
            ):

                year_start = date(
                    current_year,
                    1,
                    1,
                )

                year_end = date(
                    current_year,
                    12,
                    31,
                )


                # ==========================================
                # REQUESTED DAYS INSIDE THIS YEAR
                # ==========================================

                request_year_start = max(
                    request_start,
                    year_start,
                )

                request_year_end = min(
                    request_end,
                    year_end,
                )


                requested_days = (
                    request_year_end
                    - request_year_start
                ).days + 1


                # ==========================================
                # LOCK EXISTING APPROVED REQUESTS
                #
                # This prevents two approvals from
                # consuming the same remaining balance
                # at the same time.
                # ==========================================

                cursor.execute(
                    """
                    SELECT
                        leave_request_id,
                        start_date,
                        end_date

                    FROM leave_requests

                    WHERE
                        employee_id = %s

                        AND leave_type_id = %s

                        AND status = 'APPROVED'

                        AND leave_request_id <> %s

                        AND start_date <= %s

                        AND end_date >= %s

                    FOR UPDATE
                    """,
                    (
                        leave_request[
                            "employee_id"
                        ],
                        leave_request[
                            "leave_type_id"
                        ],
                        leave_request_id,
                        year_end,
                        year_start,
                    ),
                )


                approved_requests = (
                    cursor.fetchall()
                )


                # ==========================================
                # CALCULATE USED DAYS
                # ==========================================

                used_days = 0


                for approved in approved_requests:

                    approved_start = max(
                        approved[
                            "start_date"
                        ],
                        year_start,
                    )

                    approved_end = min(
                        approved[
                            "end_date"
                        ],
                        year_end,
                    )


                    used_days += (
                        approved_end
                        - approved_start
                    ).days + 1


                remaining_days = (
                    annual_entitlement
                    - used_days
                )


                # ==========================================
                # INSUFFICIENT BALANCE
                # ==========================================

                if (
                    requested_days
                    > remaining_days
                ):

                    raise ValueError(
                        (
                            f"Insufficient "
                            f"{leave_request['leave_name']} "
                            f"balance for {current_year}. "
                            f"Entitlement: "
                            f"{annual_entitlement} day(s), "
                            f"Used: {used_days} day(s), "
                            f"Remaining: "
                            f"{remaining_days} day(s), "
                            f"Requested: "
                            f"{requested_days} day(s)."
                        )
                    )


                current_year += 1


        # ==================================================
        # CHECK ATTENDANCE CONFLICTS
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
        # CREATE ON_LEAVE ATTENDANCE RECORDS
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
        # APPROVE REQUEST
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
# LEAVE REPORTS - SUMMARY
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