# ==========================================================
# PAYROLL WORKFLOW REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# VALIDATE PAYROLL READY FOR APPROVAL
# ==========================================================

def _validate_payroll_ready(
    cursor,
    payroll_period_id,
    start_date,
    end_date,
):

    # ======================================================
    # ENTRY SUMMARY
    # ==========================================================

    cursor.execute(
        """
        SELECT
            COUNT(*) AS total_entries,

            COALESCE(
                SUM(
                    status = 'CALCULATED'
                ),
                0
            ) AS calculated_entries,

            COALESCE(
                SUM(
                    unrecorded_days
                ),
                0
            ) AS unrecorded_days,

            COALESCE(
                SUM(
                    calculated_at IS NULL
                ),
                0
            ) AS missing_calculations

        FROM payroll_entries

        WHERE payroll_period_id = %s
        """,
        (
            payroll_period_id,
        ),
    )


    summary = cursor.fetchone()


    total_entries = (
        summary["total_entries"]
        or 0
    )


    calculated_entries = (
        summary["calculated_entries"]
        or 0
    )


    unrecorded_days = (
        summary["unrecorded_days"]
        or 0
    )


    missing_calculations = (
        summary["missing_calculations"]
        or 0
    )


    # ======================================================
    # MUST HAVE ENTRIES
    # ==========================================================

    if total_entries == 0:

        raise ValueError(
            (
                "Payroll cannot be submitted because "
                "no payroll entries have been generated."
            )
        )


    # ======================================================
    # ALL ENTRIES MUST BE CALCULATED
    # ==========================================================

    if calculated_entries != total_entries:

        raise ValueError(
            (
                "Payroll cannot be submitted because "
                "not all payroll entries have been calculated."
            )
        )


    if missing_calculations > 0:

        raise ValueError(
            (
                "Payroll contains entries with missing "
                "calculation information."
            )
        )


    # ======================================================
    # ATTENDANCE MUST BE COMPLETE
    # ==========================================================

    if unrecorded_days > 0:

        raise ValueError(
            (
                "Payroll cannot be submitted because "
                f"{unrecorded_days} scheduled attendance "
                "day(s) are still unrecorded."
            )
        )


    # ======================================================
    # CHECK FOR ATTENDANCE CHANGED AFTER CALCULATION
    #
    # If HR edits Attendance after Payroll was calculated,
    # the payroll must be recalculated before approval.
    # ==========================================================

    cursor.execute(
        """
        SELECT
            COUNT(*) AS stale_count

        FROM payroll_entries pe

        INNER JOIN attendance_records ar
            ON pe.employee_id
            = ar.employee_id

        WHERE
            pe.payroll_period_id = %s

            AND ar.attendance_date
                BETWEEN %s AND %s

            AND WEEKDAY(
                ar.attendance_date
            ) BETWEEN 0 AND 4

            AND ar.updated_at
                > pe.calculated_at
        """,
        (
            payroll_period_id,
            start_date,
            end_date,
        ),
    )


    stale_result = (
        cursor.fetchone()
    )


    stale_count = (
        stale_result["stale_count"]
        or 0
    )


    if stale_count > 0:

        raise ValueError(
            (
                "Attendance was changed after payroll "
                "was calculated. Return the payroll to "
                "Draft and calculate it again before approval."
            )
        )


    return {
        "total_entries":
            total_entries,

        "calculated_entries":
            calculated_entries,

        "unrecorded_days":
            unrecorded_days,
    }


# ==========================================================
# SUBMIT PAYROLL FOR APPROVAL
#
# DRAFT -> PROCESSING
# ==========================================================

def submit_payroll_for_approval(
    payroll_period_id,
    submitted_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    try:

        connection.start_transaction()


        # ==================================================
        # LOCK PERIOD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                payroll_period_id,
                period_number,
                start_date,
                end_date,
                status

            FROM payroll_periods

            WHERE payroll_period_id = %s

            FOR UPDATE
            """,
            (
                payroll_period_id,
            ),
        )


        period = cursor.fetchone()


        if not period:

            raise ValueError(
                "Payroll period not found."
            )


        if period["status"] != "DRAFT":

            raise ValueError(
                (
                    "Only a Draft payroll period "
                    "can be submitted for approval."
                )
            )


        # ==================================================
        # VALIDATE
        # ==========================================================

        summary = _validate_payroll_ready(
            cursor=cursor,
            payroll_period_id=payroll_period_id,
            start_date=period["start_date"],
            end_date=period["end_date"],
        )


        # ==================================================
        # MOVE TO PROCESSING
        # ==========================================================

        cursor.execute(
            """
            UPDATE payroll_periods

            SET
                status = 'PROCESSING',
                submitted_by = %s,
                submitted_at = NOW(),
                updated_by = %s

            WHERE payroll_period_id = %s
            """,
            (
                submitted_by,
                submitted_by,
                payroll_period_id,
            ),
        )


        connection.commit()


        return summary


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# RETURN PAYROLL TO DRAFT
#
# PROCESSING -> DRAFT
# ==========================================================

def return_payroll_to_draft(
    payroll_period_id,
    updated_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    try:

        connection.start_transaction()


        cursor.execute(
            """
            SELECT
                payroll_period_id,
                status

            FROM payroll_periods

            WHERE payroll_period_id = %s

            FOR UPDATE
            """,
            (
                payroll_period_id,
            ),
        )


        period = cursor.fetchone()


        if not period:

            raise ValueError(
                "Payroll period not found."
            )


        if period["status"] != "PROCESSING":

            raise ValueError(
                (
                    "Only a payroll period currently "
                    "in Processing can be returned to Draft."
                )
            )


        cursor.execute(
            """
            UPDATE payroll_periods

            SET
                status = 'DRAFT',
                submitted_by = NULL,
                submitted_at = NULL,
                updated_by = %s

            WHERE payroll_period_id = %s
            """,
            (
                updated_by,
                payroll_period_id,
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
# APPROVE PAYROLL
#
# PROCESSING -> APPROVED
# ==========================================================

def approve_payroll_period(
    payroll_period_id,
    approved_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    try:

        connection.start_transaction()


        # ==================================================
        # LOCK PERIOD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                payroll_period_id,
                period_number,
                start_date,
                end_date,
                status

            FROM payroll_periods

            WHERE payroll_period_id = %s

            FOR UPDATE
            """,
            (
                payroll_period_id,
            ),
        )


        period = cursor.fetchone()


        if not period:

            raise ValueError(
                "Payroll period not found."
            )


        if period["status"] != "PROCESSING":

            raise ValueError(
                (
                    "Only a payroll period in Processing "
                    "status can be approved."
                )
            )


        # ==================================================
        # VALIDATE AGAIN BEFORE FINAL APPROVAL
        # ==========================================================

        summary = _validate_payroll_ready(
            cursor=cursor,
            payroll_period_id=payroll_period_id,
            start_date=period["start_date"],
            end_date=period["end_date"],
        )


        # ==================================================
        # APPROVE ALL ENTRIES
        # ==========================================================

        cursor.execute(
            """
            UPDATE payroll_entries

            SET status = 'APPROVED'

            WHERE
                payroll_period_id = %s
                AND status = 'CALCULATED'
            """,
            (
                payroll_period_id,
            ),
        )


        # ==================================================
        # APPROVE PERIOD
        # ==========================================================

        cursor.execute(
            """
            UPDATE payroll_periods

            SET
                status = 'APPROVED',
                approved_by = %s,
                approved_at = NOW(),
                updated_by = %s

            WHERE payroll_period_id = %s
            """,
            (
                approved_by,
                approved_by,
                payroll_period_id,
            ),
        )


        connection.commit()


        return summary


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()