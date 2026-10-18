from payroll_validation import payroll_money
from payroll_freshness import raise_payroll_lock_error, lock_payroll_inputs
# ==========================================================
# PAYROLL ENTRY REPOSITORY
# ==========================================================

from database import get_connection


# ==========================================================
# GET PAYROLL ENTRIES BY PERIOD
# ==========================================================

def get_payroll_entries_by_period(
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
                pe.payroll_entry_id,
                pe.payroll_period_id,
                pe.employee_id,
                pe.compensation_id,

                pe.pay_type,
                pe.basic_rate,
                pe.currency_code,

                pe.scheduled_work_days,
                pe.present_days,
                pe.late_days,
                pe.absent_days,
                pe.paid_leave_days,
                pe.unpaid_leave_days,
                pe.half_day_count,
                pe.unrecorded_days,

                pe.daily_rate,

                pe.regular_pay,
                pe.additional_earnings,
                pe.gross_pay,

                pe.attendance_deduction,
                pe.total_deductions,

                pe.net_pay,

                pe.status,

                pe.generated_by,
                pe.calculated_by,
                pe.calculated_at,

                pe.created_at,
                pe.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.job_title,
                e.employment_status,

                d.department_name,

                generator.username
                    AS generated_by_username,

                calculator.username
                    AS calculated_by_username

            FROM payroll_entries pe

            INNER JOIN employees e
                ON pe.employee_id
                = e.employee_id

            LEFT JOIN departments d
                ON e.department_id
                = d.department_id

            INNER JOIN users generator
                ON pe.generated_by
                = generator.user_id

            LEFT JOIN users calculator
                ON pe.calculated_by
                = calculator.user_id

            WHERE pe.payroll_period_id = %s

            ORDER BY
                e.last_name,
                e.first_name
            """,
            (
                payroll_period_id,
            ),
        )


        return cursor.fetchall()


    finally:

        cursor.close()
        connection.close()


# ==========================================================
# GET PAYROLL ENTRY BY ID
# ==========================================================

def get_payroll_entry_by_id(
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
                pe.payroll_entry_id,
                pe.payroll_period_id,
                pe.employee_id,
                pe.compensation_id,

                pe.pay_type,
                pe.basic_rate,
                pe.currency_code,

                pe.scheduled_work_days,
                pe.present_days,
                pe.late_days,
                pe.absent_days,
                pe.paid_leave_days,
                pe.unpaid_leave_days,
                pe.half_day_count,
                pe.unrecorded_days,

                pe.daily_rate,

                pe.regular_pay,
                pe.additional_earnings,
                pe.gross_pay,

                pe.attendance_deduction,
                pe.total_deductions,

                pe.net_pay,
                pe.status,

                pe.calculated_at,
                pe.created_at,
                pe.updated_at,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name,
                e.job_title,

                d.department_name,

                pp.period_number,
                pp.period_name,
                pp.start_date,
                pp.end_date,
                pp.pay_date,

                pp.status
                    AS period_status

            FROM payroll_entries pe

            INNER JOIN employees e
                ON pe.employee_id
                = e.employee_id

            LEFT JOIN departments d
                ON e.department_id
                = d.department_id

            INNER JOIN payroll_periods pp
                ON pe.payroll_period_id
                = pp.payroll_period_id

            WHERE pe.payroll_entry_id = %s
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
# GENERATE PAYROLL ENTRIES
#
# Rules:
#
# - Period must still be DRAFT
# - Employee must be Active or On Leave
# - Employee must have compensation
# - Compensation must already be effective on or before
#   the payroll period START date
# - Existing payroll entries are not duplicated
#
# This operation DOES NOT calculate actual salary yet.
# ==========================================================

def generate_payroll_entries(
    payroll_period_id,
    generated_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )

    try:

        connection.start_transaction()
        lock_payroll_inputs(cursor)


        # ==================================================
        # LOCK PAYROLL PERIOD
        # ==========================================================

        cursor.execute(
            """
            SELECT
                payroll_period_id,
                period_number,
                period_name,
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
                    "Payroll entries can only be generated "
                    "while the payroll period is in Draft status."
                )
            )


        # ==================================================
        # GET ELIGIBLE EMPLOYEES
        #
        # On Leave employees are still included because
        # approved/paid leave may still be payable.
        # ==========================================================

        cursor.execute(
            """
            SELECT
                e.employee_id,

                c.compensation_id,
                c.pay_type,
                c.basic_rate,
                c.currency_code,
                c.effective_date

            FROM employees e

            INNER JOIN employee_compensation c
                ON e.employee_id
                = c.employee_id

            WHERE
                e.employment_status IN (
                    'Active',
                    'On Leave'
                )

                AND c.effective_date <= %s

            ORDER BY
                e.employee_id
            """,
            (
                period["start_date"],
            ),
        )


        eligible_employees = (
            cursor.fetchall()
        )


        if not eligible_employees:

            raise ValueError(
                (
                    "No eligible employees with effective "
                    "compensation were found for this payroll period."
                )
            )


        inserted_count = 0

        existing_count = 0


        # ==================================================
        # CREATE ONE ENTRY PER EMPLOYEE
        # ==========================================================

        for employee in eligible_employees:

            # ==============================================
            # CHECK EXISTING ENTRY
            # ==============================================

            cursor.execute(
                """
                SELECT payroll_entry_id

                FROM payroll_entries

                WHERE
                    payroll_period_id = %s
                    AND employee_id = %s

                FOR UPDATE
                """,
                (
                    payroll_period_id,
                    employee["employee_id"],
                ),
            )


            existing_entry = (
                cursor.fetchone()
            )


            if existing_entry:

                existing_count += 1
                continue


            # ==============================================
            # SNAPSHOT COMPENSATION
            # ==============================================

            payroll_money(employee["basic_rate"], "Saved basic rate")

            cursor.execute(
                """
                INSERT INTO payroll_entries (
                    payroll_period_id,
                    employee_id,
                    compensation_id,
                    pay_type,
                    basic_rate,
                    currency_code,
                    regular_pay,
                    additional_earnings,
                    gross_pay,
                    total_deductions,
                    net_pay,
                    status,
                    generated_by
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    0.00,
                    0.00,
                    0.00,
                    0.00,
                    0.00,
                    'DRAFT',
                    %s
                )
                """,
                (
                    payroll_period_id,
                    employee["employee_id"],
                    employee["compensation_id"],
                    employee["pay_type"],
                    employee["basic_rate"],
                    employee["currency_code"],
                    generated_by,
                ),
            )


            inserted_count += 1


        connection.commit()


        return {
            "eligible_count": len(
                eligible_employees
            ),
            "inserted_count": inserted_count,
            "existing_count": existing_count,
        }


    except Exception as error:

        connection.rollback()
        raise_payroll_lock_error(error)
        raise


    finally:

        cursor.close()
        connection.close()