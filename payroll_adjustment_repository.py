from payroll_validation import payroll_money, validate_payroll_totals
from payroll_freshness import raise_payroll_lock_error, lock_payroll_inputs
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
    *, earning_delta=Decimal("0"), deduction_delta=Decimal("0"), persist=True,
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


    additional_earnings += earning_delta
    other_deductions += deduction_delta

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


    validate_payroll_totals(regular_pay=regular_pay, attendance_deduction=attendance_deduction,
                            additional_earnings=additional_earnings, other_deductions=other_deductions,
                            gross_pay=gross_pay, total_deductions=total_deductions, net_pay=net_pay)

    # ======================================================
    # DATABASE UPDATE
    # ==========================================================

    if not persist:
        return

    cursor.execute(
        """
        UPDATE payroll_entries

        SET
            additional_earnings = %s,
            gross_pay = %s,
            total_deductions = %s,
            net_pay = %s,
            status = 'DRAFT', calculated_at = NULL, calculated_by = NULL,
            calculation_input_version = NULL, calculation_input_hash = NULL

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

    amount = payroll_money(amount, "Adjustment amount")
    if adjustment_type not in ("EARNING", "DEDUCTION"):
        raise ValueError("Select a valid adjustment type.")
    adjustment_name = (adjustment_name or "").strip()
    notes = (notes or "").strip() or None
    if not adjustment_name or len(adjustment_name) > 100:
        raise ValueError("Adjustment name is required and must not exceed 100 characters.")
    if notes and len(notes) > 255:
        raise ValueError("Notes must not exceed 255 characters.")

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()
        lock_payroll_inputs(cursor)


        # ==================================================
        # LOCK ENTRY + PERIOD
        # ==========================================================

        entry = _lock_adjustment_entry(cursor, payroll_entry_id)


        if not entry:

            raise ValueError(
                "Payroll entry not found."
            )


        if entry['entry_status'] not in ('DRAFT', 'CALCULATED'):
            raise ValueError('Approved or paid payroll entries cannot be adjusted. Review the historical status inconsistency.')

        if entry["period_status"] != "DRAFT":

            raise ValueError(
                (
                    "Payroll adjustments can only "
                    "be changed while the payroll "
                    "period is in Draft status."
                )
            )


        # Validate projected totals before inserting, independently of SQL mode.
        _refresh_payroll_entry_totals(
            cursor, payroll_entry_id,
            earning_delta=amount if adjustment_type == "EARNING" else Decimal("0"),
            deduction_delta=amount if adjustment_type == "DEDUCTION" else Decimal("0"),
            persist=False)

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


    except Exception as error:

        connection.rollback()
        raise_payroll_lock_error(error)
        raise


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# DELETE PAYROLL ADJUSTMENT
# ==========================================================

def delete_payroll_adjustment(
    payroll_entry_id,
    adjustment_id,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()
        lock_payroll_inputs(cursor)


        # ==================================================
        # LOCK ENTRY + PERIOD
        # ==========================================================

        entry = _lock_adjustment_entry(cursor, payroll_entry_id)


        if not entry:

            raise ValueError(
                "Payroll entry not found."
            )


        if entry['entry_status'] not in ('DRAFT', 'CALCULATED'):
            raise ValueError('Approved or paid payroll entries cannot be adjusted. Review the historical status inconsistency.')

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


    except Exception as error:

        connection.rollback()
        raise_payroll_lock_error(error)
        raise


    finally:

        cursor.close()
        connection.close()


def _lock_adjustment_entry(cursor, payroll_entry_id):
    # Guard is already held. Discover the parent without locking the child first.
    cursor.execute("SELECT payroll_period_id FROM payroll_entries WHERE payroll_entry_id = %s",
                   (payroll_entry_id,))
    identity = cursor.fetchone()
    if not identity:
        return None
    period_id = identity["payroll_period_id"]
    cursor.execute("SELECT status FROM payroll_periods WHERE payroll_period_id = %s FOR UPDATE",
                   (period_id,))
    period = cursor.fetchone()
    cursor.execute("SELECT payroll_entry_id, status AS entry_status FROM payroll_entries "
                   "WHERE payroll_entry_id = %s AND payroll_period_id = %s FOR UPDATE",
                   (payroll_entry_id, period_id))
    entry = cursor.fetchone()
    if not period or not entry:
        return None
    entry["period_status"] = period["status"]
    return entry
