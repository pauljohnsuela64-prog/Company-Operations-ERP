# ==========================================================
# PAYROLL CALCULATION REPOSITORY
# ==========================================================

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from database import get_connection


# ==========================================================
# CURRENT PAYROLL POLICY
#
# For the current ERP phase:
#
# - Payroll is semi-monthly
# - Each payroll period represents 50% of monthly basic pay
# - Monday-Friday are scheduled workdays
#
# Later this should move into configurable Payroll Settings.
# ==========================================================

MONTHLY_PERIOD_FACTOR = Decimal("0.50")

HALF_DAY_FACTOR = Decimal("0.50")

MONEY_PLACES = Decimal("0.01")


# ==========================================================
# MONEY ROUNDING
# ==========================================================

def _money(value):

    return Decimal(value).quantize(
        MONEY_PLACES,
        rounding=ROUND_HALF_UP,
    )


# ==========================================================
# GET WEEKDAY WORK DATES
# ==========================================================

def _get_work_dates(
    start_date,
    end_date,
):

    work_dates = []

    current_date = start_date


    while current_date <= end_date:

        # Monday = 0
        # Friday = 4

        if current_date.weekday() < 5:

            work_dates.append(
                current_date
            )


        current_date += timedelta(
            days=1
        )


    return work_dates


# ==========================================================
# CALCULATE MONTHLY PAYROLL PERIOD
#
# This currently calculates MONTHLY employees only.
#
# Missing attendance is NOT treated as absence.
# Instead it is stored in unrecorded_days.
# ==========================================================

def calculate_monthly_payroll_period(
    payroll_period_id,
    calculated_by,
):

    connection = get_connection()

    cursor = connection.cursor(
        dictionary=True
    )


    try:

        connection.start_transaction()


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
                pay_date,
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
                    "Payroll can only be calculated "
                    "while the payroll period is in Draft status."
                )
            )


        # ==================================================
        # WORKING DAYS
        # ==========================================================

        work_dates = _get_work_dates(
            period["start_date"],
            period["end_date"],
        )


        scheduled_work_days = len(
            work_dates
        )


        if scheduled_work_days == 0:

            raise ValueError(
                (
                    "This payroll period does not contain "
                    "any Monday-Friday workdays."
                )
            )


        work_date_set = set(
            work_dates
        )


        # ==================================================
        # GET MONTHLY PAYROLL ENTRIES
        # ==========================================================

        cursor.execute(
            """
            SELECT
                pe.payroll_entry_id,
                pe.employee_id,
                pe.basic_rate,
                pe.additional_earnings,
                pe.status,

                e.employee_number,
                e.first_name,
                e.middle_name,
                e.last_name

            FROM payroll_entries pe

            INNER JOIN employees e
                ON pe.employee_id
                = e.employee_id

            WHERE
                pe.payroll_period_id = %s
                AND pe.pay_type = 'MONTHLY'

            ORDER BY
                e.last_name,
                e.first_name

            FOR UPDATE
            """,
            (
                payroll_period_id,
            ),
        )


        payroll_entries = (
            cursor.fetchall()
        )


        if not payroll_entries:

            raise ValueError(
                (
                    "No monthly payroll entries "
                    "were found for this period."
                )
            )


        calculated_count = 0

        total_unrecorded_days = 0


        # ==================================================
        # CALCULATE EACH MONTHLY EMPLOYEE
        # ==========================================================

        for entry in payroll_entries:

            employee_id = (
                entry["employee_id"]
            )


            employee_name = (
                f"{entry['first_name']} "
                f"{entry['last_name']}"
            )


            # ==============================================
            # ATTENDANCE
            # ==============================================

            cursor.execute(
                """
                SELECT
                    attendance_date,
                    status

                FROM attendance_records

                WHERE
                    employee_id = %s
                    AND attendance_date
                        BETWEEN %s AND %s

                FOR UPDATE
                """,
                (
                    employee_id,
                    period["start_date"],
                    period["end_date"],
                ),
            )


            attendance_rows = (
                cursor.fetchall()
            )


            attendance_by_date = {
                row["attendance_date"]:
                    row["status"]

                for row in attendance_rows

                if row["attendance_date"]
                in work_date_set
            }


            # ==============================================
            # APPROVED LEAVE
            # ==============================================

            cursor.execute(
                """
                SELECT
                    lr.request_number,
                    lr.start_date,
                    lr.end_date,

                    lt.leave_name,
                    lt.is_paid

                FROM leave_requests lr

                INNER JOIN leave_types lt
                    ON lr.leave_type_id
                    = lt.leave_type_id

                WHERE
                    lr.employee_id = %s
                    AND lr.status = 'APPROVED'
                    AND lr.start_date <= %s
                    AND lr.end_date >= %s

                FOR UPDATE
                """,
                (
                    employee_id,
                    period["end_date"],
                    period["start_date"],
                ),
            )


            approved_leaves = (
                cursor.fetchall()
            )


            # ==============================================
            # ATTENDANCE COUNTERS
            # ==============================================

            present_days = 0

            late_days = 0

            absent_days = 0

            paid_leave_days = 0

            unpaid_leave_days = 0

            half_day_count = 0

            unrecorded_days = 0


            # ==============================================
            # PROCESS EACH SCHEDULED WORKDAY
            # ==============================================

            for work_date in work_dates:

                attendance_status = (
                    attendance_by_date.get(
                        work_date
                    )
                )


                # ==========================================
                # MISSING ATTENDANCE
                # ==========================================

                if not attendance_status:

                    unrecorded_days += 1
                    continue


                # ==========================================
                # PRESENT
                # ==========================================

                if attendance_status == "PRESENT":

                    present_days += 1


                # ==========================================
                # LATE
                #
                # No monetary deduction yet.
                # ==========================================

                elif attendance_status == "LATE":

                    late_days += 1


                # ==========================================
                # ABSENT
                # ==========================================

                elif attendance_status == "ABSENT":

                    absent_days += 1


                # ==========================================
                # HALF DAY
                # ==========================================

                elif attendance_status == "HALF_DAY":

                    half_day_count += 1


                # ==========================================
                # ON LEAVE
                # ==========================================

                elif attendance_status == "ON_LEAVE":

                    matching_leave = None


                    for leave in approved_leaves:

                        if (
                            leave["start_date"]
                            <= work_date
                            <= leave["end_date"]
                        ):

                            matching_leave = leave
                            break


                    # ======================================
                    # ATTENDANCE / LEAVE DATA CONFLICT
                    # ======================================

                    if not matching_leave:

                        raise ValueError(
                            (
                                f"{employee_name} has an "
                                f"ON_LEAVE attendance record "
                                f"for {work_date}, but no "
                                "approved leave request covers "
                                "that date."
                            )
                        )


                    if matching_leave["is_paid"]:

                        paid_leave_days += 1

                    else:

                        unpaid_leave_days += 1


                # ==========================================
                # UNKNOWN STATUS
                # ==========================================

                else:

                    raise ValueError(
                        (
                            f"Unsupported attendance status "
                            f"'{attendance_status}' for "
                            f"{employee_name} on {work_date}."
                        )
                    )


            # ==============================================
            # MONTHLY PERIOD PAY
            #
            # Current policy:
            # 50% of monthly salary per semi-monthly period.
            # ==============================================

            basic_rate = Decimal(
                str(
                    entry["basic_rate"]
                )
            )


            regular_pay = (
                basic_rate
                * MONTHLY_PERIOD_FACTOR
            )


            regular_pay = _money(
                regular_pay
            )


            # ==============================================
            # PERIOD DAILY RATE
            #
            # Used only for attendance deductions.
            # ==============================================

            raw_daily_rate = (
                regular_pay
                / Decimal(
                    scheduled_work_days
                )
            )


            daily_rate = _money(
                raw_daily_rate
            )


            # ==============================================
            # DEDUCTIBLE DAYS
            #
            # ABSENT       = 1.0
            # UNPAID LEAVE = 1.0
            # HALF DAY     = 0.5
            # ==============================================

            deductible_days = (
                Decimal(absent_days)
                + Decimal(
                    unpaid_leave_days
                )
                + (
                    Decimal(
                        half_day_count
                    )
                    * HALF_DAY_FACTOR
                )
            )


            attendance_deduction = (
                raw_daily_rate
                * deductible_days
            )


            attendance_deduction = _money(
                attendance_deduction
            )


            # ==============================================
            # ADDITIONAL EARNINGS
            # ==============================================

            additional_earnings = Decimal(
                str(
                    entry[
                        "additional_earnings"
                    ]
                    or 0
                )
            )


            additional_earnings = _money(
                additional_earnings
            )


            # ==============================================
            # GROSS PAY
            # ==============================================

            gross_pay = _money(
                regular_pay
                + additional_earnings
            )


            # ==============================================
            # TOTAL DEDUCTIONS
            #
            # For now:
            # total deductions = attendance deduction.
            #
            # Government and other deductions come later.
            # ==============================================

            total_deductions = (
                attendance_deduction
            )


            # ==============================================
            # NET PAY
            # ==============================================

            net_pay = (
                gross_pay
                - total_deductions
            )


            if net_pay < 0:

                net_pay = Decimal(
                    "0.00"
                )


            net_pay = _money(
                net_pay
            )


            # ==============================================
            # DATABASE UPDATE
            # ==============================================

            cursor.execute(
                """
                UPDATE payroll_entries

                SET
                    scheduled_work_days = %s,

                    present_days = %s,
                    late_days = %s,
                    absent_days = %s,
                    paid_leave_days = %s,
                    unpaid_leave_days = %s,
                    half_day_count = %s,
                    unrecorded_days = %s,

                    daily_rate = %s,

                    regular_pay = %s,

                    attendance_deduction = %s,

                    gross_pay = %s,

                    total_deductions = %s,

                    net_pay = %s,

                    status = 'CALCULATED',

                    calculated_by = %s,
                    calculated_at = NOW()

                WHERE payroll_entry_id = %s
                """,
                (
                    scheduled_work_days,

                    present_days,
                    late_days,
                    absent_days,
                    paid_leave_days,
                    unpaid_leave_days,
                    half_day_count,
                    unrecorded_days,

                    daily_rate,

                    regular_pay,

                    attendance_deduction,

                    gross_pay,

                    total_deductions,

                    net_pay,

                    calculated_by,
                    entry[
                        "payroll_entry_id"
                    ],
                ),
            )


            calculated_count += 1

            total_unrecorded_days += (
                unrecorded_days
            )


        # ==================================================
        # COMMIT ENTIRE PAYROLL CALCULATION
        # ==========================================================

        connection.commit()


        return {
            "calculated_count":
                calculated_count,

            "unrecorded_days":
                total_unrecorded_days,

            "scheduled_work_days":
                scheduled_work_days,
        }


    except Exception:

        connection.rollback()
        raise


    finally:

        cursor.close()
        connection.close()