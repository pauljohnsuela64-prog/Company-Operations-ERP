import payroll_freshness as freshness
# ==========================================================
# PAYROLL PERIOD REPOSITORY
# ==========================================================

import uuid

from database import get_connection


class PayrollScheduleError(ValueError):
    """Safe feedback for the existing nonoverlapping-period invariant."""
    def __init__(self, message, status_code=409):
        super().__init__(message)
        self.status_code = status_code


def _lock_nonoverlapping_schedule(cursor, start_date, end_date, exclude_id=None):
    # Reuse a stable existing row as a writer gate, without changing any grants.
    # All schedule creates/edits acquire it before period locks. Other payroll
    # operations lock periods only, and never acquire this gate in reverse order.
    cursor.execute("SELECT ENGINE FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='payroll_periods'")
    row = cursor.fetchone()
    if not row or row[0] != 'InnoDB':
        raise PayrollScheduleError('Payroll scheduling is temporarily unavailable. Contact an administrator.', 503)
    cursor.execute("SELECT permission_id FROM permissions WHERE permission_code='payroll.process' FOR UPDATE")
    if cursor.fetchone() is None:
        raise PayrollScheduleError('Payroll scheduling is temporarily unavailable. Contact an administrator.', 503)
    # A current read sees a writer that committed while this transaction waited,
    # including under REPEATABLE READ. Route preflight checks remain early feedback.
    cursor.execute("SELECT payroll_period_id FROM payroll_periods WHERE status<>'CANCELLED' "
                   "AND start_date<=%s AND end_date>=%s "
                   "AND (%s IS NULL OR payroll_period_id<>%s) LIMIT 1 FOR UPDATE",
                   (end_date, start_date, exclude_id, exclude_id))
    if cursor.fetchone() is not None:
        raise PayrollScheduleError('This payroll period overlaps another active period. Reload and review the schedule.')


# ==========================================================
# GET ALL PAYROLL PERIODS
# ==========================================================

def get_all_payroll_periods():

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                pp.payroll_period_id,
                pp.period_number,
                pp.period_name,
                pp.start_date,
                pp.end_date,
                pp.pay_date,
                pp.status,
                pp.notes,
                pp.created_at,
                pp.updated_at,
                pp.approved_at,
                pp.paid_at,

                creator.username
                    AS created_by_username,

                updater.username
                    AS updated_by_username,

                approver.username
                    AS approved_by_username,

                payer.username
                    AS paid_by_username

            FROM payroll_periods pp

            INNER JOIN users creator
                ON pp.created_by
                = creator.user_id

            LEFT JOIN users updater
                ON pp.updated_by
                = updater.user_id

            LEFT JOIN users approver
                ON pp.approved_by
                = approver.user_id

            LEFT JOIN users payer
                ON pp.paid_by
                = payer.user_id

            ORDER BY
                pp.start_date DESC,
                pp.payroll_period_id DESC
            """
        )

        return cursor.fetchall()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET PAYROLL PERIOD BY ID
# ==========================================================

def get_payroll_period_by_id(
    payroll_period_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                payroll_period_id,
                period_number,
                period_name,
                start_date,
                end_date,
                pay_date,
                status,
                notes,
                created_by,
                updated_by,
                approved_by,
                approved_at,
                paid_by,
                paid_at,
                created_at,
                updated_at

            FROM payroll_periods

            WHERE payroll_period_id = %s
            """,
            (
                payroll_period_id,
            ),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CHECK OVERLAPPING PAYROLL PERIOD
# ==========================================================

def has_overlapping_payroll_period(
    start_date,
    end_date,
    exclude_payroll_period_id=None,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        query = """
            SELECT
                payroll_period_id,
                period_number,
                period_name,
                start_date,
                end_date,
                status

            FROM payroll_periods

            WHERE
                status <> 'CANCELLED'

                AND start_date <= %s
                AND end_date >= %s
        """

        parameters = [
            end_date,
            start_date,
        ]


        if exclude_payroll_period_id:

            query += """
                AND payroll_period_id <> %s
            """

            parameters.append(
                exclude_payroll_period_id
            )


        query += """
            LIMIT 1
        """


        cursor.execute(
            query,
            tuple(parameters),
        )

        return cursor.fetchone()

    finally:

        cursor.close()
        connection.close()


# ==========================================================
# CREATE PAYROLL PERIOD
# ==========================================================

def create_payroll_period(
    period_name,
    start_date,
    end_date,
    pay_date,
    notes,
    created_by,
):

    connection = get_connection()

    cursor = None

    try:

        connection.start_transaction()
        cursor = connection.cursor()
        freshness.lock_guard(cursor)
        _lock_nonoverlapping_schedule(cursor, start_date, end_date)


        # ==================================================
        # TEMPORARY UNIQUE PERIOD NUMBER
        # ==========================================================

        temporary_number = (
            f"TMP-{uuid.uuid4().hex}"
        )


        cursor.execute(
            """
            INSERT INTO payroll_periods (
                period_number,
                period_name,
                start_date,
                end_date,
                pay_date,
                status,
                notes,
                created_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                'DRAFT',
                %s,
                %s
            )
            """,
            (
                temporary_number,
                period_name,
                start_date,
                end_date,
                pay_date,
                notes,
                created_by,
            ),
        )


        payroll_period_id = (
            cursor.lastrowid
        )


        # ==================================================
        # FINAL PERIOD NUMBER
        # ==========================================================

        period_number = (
            f"PP-{payroll_period_id:06d}"
        )


        cursor.execute(
            """
            UPDATE payroll_periods

            SET period_number = %s

            WHERE payroll_period_id = %s
            """,
            (
                period_number,
                payroll_period_id,
            ),
        )


        connection.commit()

        return payroll_period_id


    except Exception:

        connection.rollback()
        raise


    finally:

        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


# ==========================================================
# UPDATE PAYROLL PERIOD
#
# Only DRAFT periods can be edited.
# ==========================================================

def update_payroll_period(
    payroll_period_id,
    period_name,
    start_date,
    end_date,
    pay_date,
    notes,
    updated_by,
):

    connection = get_connection()

    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        freshness.lock_guard(cursor)
        _lock_nonoverlapping_schedule(cursor, start_date, end_date, payroll_period_id)

        cursor.execute(
            """
            UPDATE payroll_periods

            SET
                period_name = %s,
                start_date = %s,
                end_date = %s,
                pay_date = %s,
                notes = %s,
                updated_by = %s

            WHERE
                payroll_period_id = %s
                AND status = 'DRAFT'
            """,
            (
                period_name,
                start_date,
                end_date,
                pay_date,
                notes,
                updated_by,
                payroll_period_id,
            ),
        )


        updated = (
            cursor.rowcount == 1
        )


        connection.commit()

        return updated


    except Exception:

        connection.rollback()
        raise


    finally:

        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()


# ==========================================================
# CANCEL PAYROLL PERIOD
#
# Only DRAFT periods can be cancelled.
# ==========================================================

def cancel_payroll_period(
    payroll_period_id,
    updated_by,
):

    connection = get_connection()

    cursor = None

    try:
        connection.start_transaction()
        cursor = connection.cursor()
        freshness.lock_guard(cursor)

        cursor.execute(
            """
            UPDATE payroll_periods

            SET
                status = 'CANCELLED',
                updated_by = %s

            WHERE
                payroll_period_id = %s
                AND status = 'DRAFT'
            """,
            (
                updated_by,
                payroll_period_id,
            ),
        )


        cancelled = (
            cursor.rowcount == 1
        )


        connection.commit()

        return cancelled


    except Exception:

        connection.rollback()
        raise


    finally:

        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()
