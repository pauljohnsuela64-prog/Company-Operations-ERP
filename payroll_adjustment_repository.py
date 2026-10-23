import payroll_freshness as freshness
# ==========================================================
# PAYROLL ADJUSTMENT REPOSITORY
# ==========================================================

from decimal import Decimal

from database import get_connection


# ==========================================================
# REFRESH PAYROLL TOTALS
#
# This recalculates:
#
# Additional Earnings
# Gross Pay
# Total Deductions
# Net Pay
#
# without changing attendance calculation.
# ==========================================================

def _refresh_payroll_entry_totals(
    cursor,
    payroll_entry_id,
):

    # ======================================================
    # CURRENT PAYROLL VALUES
    # ==========================================================

    cursor.execute(
        """
        SELECT
            regular_pay,
            attendance_deduction

        FROM payroll_entries

        WHERE payroll_entry_id = %s

        FOR UPDATE
        """,
        (
            payroll_entry_id,
        ),
    )


    entry = cursor.fetchone()


    if not entry:

        raise ValueError(
            "Payroll entry not found."
        )


    # ======================================================
    # ADJUSTMENT TOTALS
    # ==========================================================

    cursor.execute(
        """
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN adjustment_type = 'EARNING'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS earnings,

            COALESCE(
                SUM(
                    CASE
                        WHEN adjustment_type = 'DEDUCTION'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS deductions

        FROM payroll_adjustments

        WHERE payroll_entry_id = %s
        """,
        (
            payroll_entry_id,
        ),
    )


    totals = cursor.fetchone()


    regular_pay = Decimal(
        str(
            entry["regular_pay"]
            or 0
        )
    )


    attendance_deduction = Decimal(
        str(
            entry["attendance_deduction"]
            or 0
        )
    )


    additional_earnings = Decimal(
        str(
            totals["earnings"]
            or 0
        )
    )


    other_deductions = Decimal(
        str(
            totals["deductions"]
            or 0
        )
    )


    # ======================================================
    # CALCULATIONS
    # ==========================================================

    gross_pay = (
        regular_pay
        + additional_earnings
    )


    total_deductions = (
        attendance_deduction
        + other_deductions
    )


    net_pay = (
        gross_pay
        - total_deductions
    )


    if net_pay < 0:

        net_pay = Decimal(
            "0.00"
        )


    # ======================================================
    # DATABASE UPDATE
    # ==========================================================

    cursor.execute(
        """
        UPDATE payroll_entries

        SET
            additional_earnings = %s,
            gross_pay = %s,
            total_deductions = %s,
            net_pay = %s

        WHERE payroll_entry_id = %s
        """,
        (
            additional_earnings,
            gross_pay,
            total_deductions,
            net_pay,
            payroll_entry_id,
        ),
    )


# ==========================================================
# GET ADJUSTMENTS
# ==========================================================

def get_payroll_adjustments(
    payroll_entry_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                pa.adjustment_id,
                pa.payroll_entry_id,
                pa.adjustment_type,
                pa.adjustment_name,
                pa.amount,
                pa.notes,
                pa.created_at,

                u.username
                    AS created_by_username

            FROM payroll_adjustments pa

            INNER JOIN users u
                ON pa.created_by
                = u.user_id

            WHERE pa.payroll_entry_id = %s

            ORDER BY
                pa.created_at,
                pa.adjustment_id
            """,
            (
                payroll_entry_id,
            ),
        )


        return cursor.fetchall()


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET ADJUSTMENT TOTALS
# ==========================================================

def get_payroll_adjustment_totals(
    payroll_entry_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        cursor.execute(
            """
            SELECT
                COALESCE(
                    SUM(
                        CASE
                            WHEN adjustment_type = 'EARNING'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS earnings,

                COALESCE(
                    SUM(
                        CASE
                            WHEN adjustment_type = 'DEDUCTION'
                            THEN amount
                            ELSE 0
                        END
                    ),
                    0
                ) AS deductions

            FROM payroll_adjustments

            WHERE payroll_entry_id = %s
            """,
            (
                payroll_entry_id,
            ),
        )


        return cursor.fetchone()


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# ADD PAYROLL ADJUSTMENT
# ==========================================================

def add_payroll_adjustment(
    payroll_entry_id,
    adjustment_type,
    adjustment_name,
    amount,
    notes,
    created_by,
):

    connection = get_connection()

    cursor = None

    try:

        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        freshness.lock_guard(cursor)


        # ==================================================
        # LOCK ENTRY + PERIOD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                pe.payroll_entry_id,
                pp.status AS period_status

            FROM payroll_entries pe

            INNER JOIN payroll_periods pp
                ON pe.payroll_period_id
                = pp.payroll_period_id

            WHERE pe.payroll_entry_id = %s

            FOR UPDATE
            """,
            (
                payroll_entry_id,
            ),
        )


        entry = cursor.fetchone()


        if not entry:

            raise ValueError(
                "Payroll entry not found."
            )


        if entry["period_status"] != "DRAFT":

            raise ValueError(
                (
                    "Payroll adjustments can only "
                    "be changed while the payroll "
                    "period is in Draft status."
                )
            )


        # ==================================================
        # INSERT ADJUSTMENT
        # ==========================================================

        cursor.execute(
            """
            INSERT INTO payroll_adjustments (
                payroll_entry_id,
                adjustment_type,
                adjustment_name,
                amount,
                notes,
                created_by
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            """,
            (
                payroll_entry_id,
                adjustment_type,
                adjustment_name,
                amount,
                notes,
                created_by,
            ),
        )


        # ==================================================
        # REFRESH TOTALS
        # ==========================================================

        _refresh_payroll_entry_totals(
            cursor,
            payroll_entry_id,
        )


        connection.commit()


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
# DELETE PAYROLL ADJUSTMENT
# ==========================================================

def delete_payroll_adjustment(
    payroll_entry_id,
    adjustment_id,
):

    connection = get_connection()

    cursor = None

    try:

        connection.start_transaction()
        cursor = connection.cursor(dictionary=True)
        freshness.lock_guard(cursor)


        # ==================================================
        # LOCK ENTRY + PERIOD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                pe.payroll_entry_id,
                pp.status AS period_status

            FROM payroll_entries pe

            INNER JOIN payroll_periods pp
                ON pe.payroll_period_id
                = pp.payroll_period_id

            WHERE pe.payroll_entry_id = %s

            FOR UPDATE
            """,
            (
                payroll_entry_id,
            ),
        )


        entry = cursor.fetchone()


        if not entry:

            raise ValueError(
                "Payroll entry not found."
            )


        if entry["period_status"] != "DRAFT":

            raise ValueError(
                (
                    "Payroll adjustments can only "
                    "be changed while the payroll "
                    "period is in Draft status."
                )
            )


        # ==================================================
        # DELETE ONLY FROM THIS ENTRY
        # ==========================================================

        cursor.execute(
            """
            DELETE FROM payroll_adjustments

            WHERE
                adjustment_id = %s
                AND payroll_entry_id = %s
            """,
            (
                adjustment_id,
                payroll_entry_id,
            ),
        )


        if cursor.rowcount != 1:

            raise ValueError(
                "Payroll adjustment not found."
            )


        # ==================================================
        # REFRESH TOTALS
        # ==========================================================

        _refresh_payroll_entry_totals(
            cursor,
            payroll_entry_id,
        )


        connection.commit()


    except Exception:

        connection.rollback()
        raise


    finally:

        try:
            if cursor is not None:
                cursor.close()
        finally:
            connection.close()