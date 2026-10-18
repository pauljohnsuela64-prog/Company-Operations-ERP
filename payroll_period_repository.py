from payroll_freshness import raise_payroll_lock_error, lock_payroll_inputs
# ==========================================================
# PAYROLL PERIOD REPOSITORY
# ==========================================================

import uuid

from database import get_connection


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

    cursor = connection.cursor()

    try:

        connection.start_transaction()
        lock_payroll_inputs(cursor)


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


    except Exception as error:

        connection.rollback()
        raise_payroll_lock_error(error)
        raise


    finally:

        cursor.close()
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
    cursor = connection.cursor(dictionary=True)
    try:
        connection.start_transaction()
        lock_payroll_inputs(cursor)
        # Match calculation/workflow ordering: period first, then its entries.
        cursor.execute("""SELECT start_date, end_date, status FROM payroll_periods
                          WHERE payroll_period_id = %s FOR UPDATE""", (payroll_period_id,))
        previous = cursor.fetchone()
        if not previous or previous['status'] != 'DRAFT':
            connection.rollback()
            return False
        dates_changed = (str(previous['start_date']) != str(start_date)
                         or str(previous['end_date']) != str(end_date))
        if dates_changed:
            cursor.execute("""SELECT payroll_entry_id, status FROM payroll_entries
                              WHERE payroll_period_id = %s ORDER BY payroll_entry_id FOR UPDATE""",
                           (payroll_period_id,))
            if any(row['status'] not in ('DRAFT', 'CALCULATED') for row in cursor.fetchall()):
                raise ValueError('Payroll history requires review. Approved or paid entries cannot be invalidated.')
        cursor.execute("""UPDATE payroll_periods
                          SET period_name = %s, start_date = %s, end_date = %s,
                              pay_date = %s, notes = %s, updated_by = %s
                          WHERE payroll_period_id = %s AND status = 'DRAFT'""",
                       (period_name, start_date, end_date, pay_date, notes, updated_by, payroll_period_id))
        updated = cursor.rowcount == 1
        if updated and dates_changed:
            # Clear cached calculations, not compensation snapshots or adjustment history.
            cursor.execute("""UPDATE payroll_entries SET
                              status = 'DRAFT', calculated_by = NULL, calculated_at = NULL,
                              calculation_input_version = NULL, calculation_input_hash = NULL,
                              scheduled_work_days = 0, present_days = 0, late_days = 0,
                              absent_days = 0, paid_leave_days = 0, unpaid_leave_days = 0,
                              half_day_count = 0, unrecorded_days = 0, daily_rate = 0,
                              regular_pay = 0, additional_earnings = 0, gross_pay = 0,
                              attendance_deduction = 0, total_deductions = 0, net_pay = 0
                              WHERE payroll_period_id = %s""", (payroll_period_id,))
        connection.commit()
        return updated
    except Exception as error:
        connection.rollback()
        raise_payroll_lock_error(error)
        raise
    finally:
        cursor.close()
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

    cursor = connection.cursor()

    try:
        connection.start_transaction()
        lock_payroll_inputs(cursor)

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


    except Exception as error:

        connection.rollback()
        raise_payroll_lock_error(error)
        raise


    finally:

        cursor.close()
        connection.close()