# ==========================================================
# DASHBOARD REPOSITORY
# ==========================================================

from datetime import date

from attendance_repository import (
    get_filtered_attendance_records,
)

from employee_repository import (
    get_all_employees,
)

from expense_repository import (
    get_all_expenses,
)

from help_desk_repository import (
    get_all_helpdesk_tickets,
)

from inventory_item_repository import (
    get_all_inventory_items,
)

from it_asset_repository import (
    get_all_it_assets,
)

from leave_repository import (
    get_all_leave_requests,
)

from payroll_period_repository import (
    get_all_payroll_periods,
)

from purchase_request_repository import (
    get_all_purchase_requests,
)


# ==========================================================
# HELPER - COUNT STATUS
# ==========================================================

def _count_status(
    records,
    target_status,
):

    target_status = (
        str(target_status)
        .strip()
        .upper()
    )


    return sum(
        1
        for record in records

        if (
            str(
                record.get(
                    "status",
                    "",
                )
            )
            .strip()
            .upper()
            == target_status
        )
    )


# ==========================================================
# HELPER - COUNT EMPLOYMENT STATUS
# ==========================================================

def _count_employment_status(
    employees,
    target_status,
):

    target_status = (
        str(target_status)
        .strip()
        .upper()
    )


    return sum(
        1
        for employee in employees

        if (
            str(
                employee.get(
                    "employment_status",
                    "",
                )
            )
            .strip()
            .upper()
            == target_status
        )
    )


# ==========================================================
# DASHBOARD SUMMARY
# ==========================================================

def get_dashboard_summary():

    today = date.today()


    # ======================================================
    # LOAD MODULE DATA
    # ==========================================================

    employees = (
        get_all_employees()
    )


    attendance_today = (
        get_filtered_attendance_records(
            attendance_date=today,
        )
    )


    leave_requests = (
        get_all_leave_requests()
    )


    inventory_items = (
        get_all_inventory_items()
    )


    purchase_requests = (
        get_all_purchase_requests()
    )


    expenses = (
        get_all_expenses()
    )


    it_assets = (
        get_all_it_assets()
    )


    helpdesk_tickets = (
        get_all_helpdesk_tickets()
    )


    payroll_periods = (
        get_all_payroll_periods()
    )


    # ======================================================
    # EMPLOYEES
    # ==========================================================

    employee_summary = {

        "total":
            len(employees),

        "active":
            _count_employment_status(
                employees,
                "ACTIVE",
            ),

        "on_leave":
            _count_employment_status(
                employees,
                "ON LEAVE",
            ),

        "inactive":
            _count_employment_status(
                employees,
                "INACTIVE",
            ),
    }


    # ======================================================
    # ATTENDANCE TODAY
    # ==========================================================

    attendance_summary = {

        "total":
            len(attendance_today),

        "present":
            _count_status(
                attendance_today,
                "PRESENT",
            ),

        "late":
            _count_status(
                attendance_today,
                "LATE",
            ),

        "absent":
            _count_status(
                attendance_today,
                "ABSENT",
            ),

        "on_leave":
            _count_status(
                attendance_today,
                "ON_LEAVE",
            ),

        "half_day":
            _count_status(
                attendance_today,
                "HALF_DAY",
            ),
    }


    # ======================================================
    # LEAVE
    # ==========================================================

    leave_summary = {

        "pending":
            _count_status(
                leave_requests,
                "PENDING",
            ),

        "approved":
            _count_status(
                leave_requests,
                "APPROVED",
            ),
    }


    # ======================================================
    # INVENTORY
    #
    # Low-stock calculation will be added later once we
    # finalize the exact stock/reorder policy.
    # ==========================================================

    inventory_summary = {

        "total_items":
            len(inventory_items),

        "active_items":
            sum(
                1
                for item in inventory_items

                if bool(
                    item.get(
                        "is_active"
                    )
                )
            ),
    }


    # ======================================================
    # PROCUREMENT
    # ==========================================================

    procurement_summary = {

        "draft":
            _count_status(
                purchase_requests,
                "DRAFT",
            ),

        "pending_approval":
            _count_status(
                purchase_requests,
                "SUBMITTED",
            ),

        "approved":
            _count_status(
                purchase_requests,
                "APPROVED",
            ),
    }


    # ======================================================
    # FINANCE
    # ==========================================================

    finance_summary = {

        "draft":
            _count_status(
                expenses,
                "DRAFT",
            ),

        "approved":
            _count_status(
                expenses,
                "APPROVED",
            ),

        "paid":
            _count_status(
                expenses,
                "PAID",
            ),
    }


    # ======================================================
    # IT ASSETS
    # ==========================================================

    it_asset_summary = {

        "total":
            len(it_assets),

        "available":
            _count_status(
                it_assets,
                "AVAILABLE",
            ),

        "assigned":
            _count_status(
                it_assets,
                "ASSIGNED",
            ),

        "maintenance":
            _count_status(
                it_assets,
                "MAINTENANCE",
            ),

        "lost":
            _count_status(
                it_assets,
                "LOST",
            ),
    }


    # ======================================================
    # HELP DESK
    # ==========================================================

    open_helpdesk_statuses = {
        "OPEN",
        "IN_PROGRESS",
    }


    open_tickets = sum(
        1
        for ticket in helpdesk_tickets

        if (
            str(
                ticket.get(
                    "status",
                    "",
                )
            )
            .strip()
            .upper()

            in open_helpdesk_statuses
        )
    )


    urgent_open_tickets = sum(
        1
        for ticket in helpdesk_tickets

        if (
            str(
                ticket.get(
                    "priority",
                    "",
                )
            )
            .strip()
            .upper()
            == "URGENT"

            and

            str(
                ticket.get(
                    "status",
                    "",
                )
            )
            .strip()
            .upper()

            in open_helpdesk_statuses
        )
    )


    helpdesk_summary = {

        "total":
            len(helpdesk_tickets),

        "open":
            open_tickets,

        "urgent_open":
            urgent_open_tickets,

        "resolved":
            _count_status(
                helpdesk_tickets,
                "RESOLVED",
            ),
    }


    # ======================================================
    # PAYROLL
    # ==========================================================

    paid_payrolls = [
        period
        for period in payroll_periods

        if (
            str(
                period.get(
                    "status",
                    "",
                )
            )
            .strip()
            .upper()
            == "PAID"
        )
    ]


    latest_paid_payroll = (
        paid_payrolls[0]
        if paid_payrolls
        else None
    )


    payroll_summary = {

        "draft":
            _count_status(
                payroll_periods,
                "DRAFT",
            ),

        "processing":
            _count_status(
                payroll_periods,
                "PROCESSING",
            ),

        "approved":
            _count_status(
                payroll_periods,
                "APPROVED",
            ),

        "paid":
            _count_status(
                payroll_periods,
                "PAID",
            ),

        "latest_paid":
            latest_paid_payroll,
    }


    # ======================================================
    # FINAL DASHBOARD DATA
    # ==========================================================

    return {

        "today":
            today,

        "employees":
            employee_summary,

        "attendance":
            attendance_summary,

        "leave":
            leave_summary,

        "inventory":
            inventory_summary,

        "procurement":
            procurement_summary,

        "finance":
            finance_summary,

        "it_assets":
            it_asset_summary,

        "helpdesk":
            helpdesk_summary,

        "payroll":
            payroll_summary,
    }