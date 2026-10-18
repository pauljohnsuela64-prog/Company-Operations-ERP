from inventory_reporting import report_filters, get_movement_page, get_reconciliation_page
from procurement_validation import decimal_value, currency_amount
from csrf_security import init_csrf
from security import configure_security, init_security, begin_session, authenticated, has_permission
import os
import uuid
from functools import wraps

from datetime import (
    date,
    datetime,
)

from dotenv import load_dotenv
from dashboard_repository import get_dashboard_summary

from audit_log_repository import (
    create_audit_log,
    get_audit_log_filter_options,
    get_filtered_audit_logs,
)

from decimal import Decimal, InvalidOperation, localcontext

from payroll_workflow_repository import (
    approve_payroll_period,
    mark_payroll_period_as_paid,
    return_payroll_to_draft,
    submit_payroll_for_approval,
)

from payroll_adjustment_repository import (
    add_payroll_adjustment,
    delete_payroll_adjustment,
    get_payroll_adjustments,
    get_payroll_adjustment_totals,
)

from payroll_entry_repository import (
    generate_payroll_entries,
    get_payroll_entries_by_period,
    get_payroll_entry_by_id,
)


from payroll_calculation_repository import (
    calculate_monthly_payroll_period,
)

from leave_export import (
    generate_leave_report_excel,
)

from payroll_period_repository import (
    cancel_payroll_period,
    create_payroll_period,
    get_all_payroll_periods,
    get_payroll_period_by_id,
    has_overlapping_payroll_period,
    update_payroll_period,
)

from payroll_repository import (
    create_employee_compensation,
    get_all_employee_compensation,
    get_employee_compensation_by_id,
    get_employee_compensation_by_employee_id,
    get_employees_without_compensation,
    update_employee_compensation,
)


from leave_repository import (
    approve_leave_request,
    cancel_leave_request,
    create_leave_request,
    create_leave_type,
    get_active_leave_types,
    get_all_leave_requests,
    get_all_leave_types,
    get_leave_request_by_id,
    get_leave_type_by_id,
    has_overlapping_leave_request,
    reject_leave_request,
    set_leave_type_active_status,
    update_leave_type,
    get_employee_leave_balances,
    get_leave_report_by_type,
    get_leave_report_records,
    get_leave_report_summary,
)


from attendance_repository import (
    create_attendance_record,
    get_all_attendance_records,
    get_attendance_record_by_id,
    get_filtered_attendance_records,
    update_attendance_record,
)


from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


from finance_export import generate_finance_report_excel

from it_asset_export import (
    generate_it_asset_report_excel,
)

from help_desk_repository import (
    assign_helpdesk_ticket,
    close_helpdesk_ticket,
    create_helpdesk_ticket,
    get_active_helpdesk_categories,
    get_all_helpdesk_tickets,
    get_helpdesk_assignable_users,
    get_helpdesk_ticket_by_id,
    resolve_helpdesk_ticket,
    start_helpdesk_ticket,
    get_filtered_helpdesk_tickets,
    get_helpdesk_summary,
    get_helpdesk_ticket_history,
    get_helpdesk_report_by_category,
    get_helpdesk_report_by_technician,
)

from help_desk_export import (
    generate_helpdesk_report_excel,
)

from it_asset_repository import (
    assign_it_asset,
    complete_it_asset_maintenance,
    create_it_asset,
    create_it_asset_category,
    create_it_asset_maintenance,
    get_active_it_asset_categories,
    get_all_it_asset_categories,
    get_all_it_assets,
    get_filtered_it_assets,
    get_it_asset_assignment_history,
    get_it_asset_by_id,
    get_it_asset_category_by_id,
    get_it_asset_maintenance_history,
    get_it_asset_summary,
    mark_it_asset_lost,
    restore_it_asset,
    retire_it_asset,
    set_it_asset_category_active_status,
    unassign_it_asset,
    update_it_asset,
    update_it_asset_category,
    get_it_asset_report_by_category,
    get_it_asset_report_by_department,
)

from budget_repository import (
    create_department_budget,
    get_all_department_budgets,
    get_budget_summary,
    get_department_budget_by_department_and_year,
    get_department_budget_by_id,
    get_department_budget_details_by_id,
    get_paid_expenses_for_budget,
    update_department_budget,
    check_expense_against_budget,
)

from expense_repository import (
    approve_expense,
    cancel_expense,
    create_expense,
    get_all_expenses,
    get_expense_by_id,
    get_finance_summary,
    get_finance_summary_by_year,
    get_monthly_paid_expenses,
    get_paid_expenses_by_category,
    mark_expense_as_paid,
    update_expense,
    get_filtered_expenses,
    search_expenses,
)

from expense_category_repository import (
    create_expense_category,
    get_active_expense_categories,
    get_all_expense_categories,
    get_expense_category_by_id,
    set_expense_category_active_status,
    update_expense_category,
)


from goods_receipt_repository import (
    create_goods_receipt,
    get_all_goods_receipts,
    get_goods_receipt_by_id,
    get_goods_receipt_items,
    get_receivable_purchase_order_by_id,
    get_receivable_purchase_order_items,
    get_receivable_purchase_orders,
    get_goods_receipts_by_purchase_order,
)

from purchase_order_repository import (
    create_purchase_order_from_request,
    get_all_purchase_orders,
    get_purchase_orders_by_request,
    get_purchase_order_by_id,
    get_purchase_order_item_by_id,
    get_purchase_order_items,
    send_purchase_order,
    update_purchase_order_item_cost,
    cancel_purchase_order,
)

from purchase_request_repository import (
    add_purchase_request_item,
    approve_purchase_request,
    create_purchase_request,
    delete_purchase_request_item,
    get_all_purchase_requests,
    get_purchase_request_by_id,
    get_purchase_request_item_by_id,
    get_purchase_request_items,
    reject_purchase_request,
    submit_purchase_request,
    update_purchase_request_item,
)

from supplier_repository import (
    create_supplier,
    get_all_suppliers,
    get_supplier_by_id,
    set_supplier_active_status,
    update_supplier,
    get_active_suppliers,
)

from stock_repository import (
    get_all_stock,
    stock_in,
    stock_out,
)


from inventory_item_repository import (
    create_inventory_item,
    get_all_inventory_items,
    get_inventory_item_by_id,
    set_inventory_item_active_status,
    update_inventory_item,
    get_active_inventory_items,
)

from warehouse_repository import (
    create_warehouse,
    get_all_warehouses,
    get_warehouse_by_id,
    set_warehouse_active_status,
    update_warehouse,
)

from inventory_category_repository import (
    create_inventory_category,
    get_active_inventory_categories,
    get_all_inventory_categories,
    get_inventory_category_by_id,
    set_inventory_category_active_status,
    update_inventory_category,
)
from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from user_repository import (
    count_active_super_admins,
    create_user,
    get_all_permissions,
    get_all_roles,
    get_all_users,
    get_available_user_employees,
    get_permissions_by_role_id,
    get_role_by_id,
    get_role_permission_ids,
    get_user_by_id,
    get_user_by_username,
    get_authorization_state,
    set_user_active_status,
    update_last_login,
    update_role_permissions,
    update_user_password,
    update_user_role,
)

from department_repository import (
    create_department,
    get_active_departments,
    get_all_departments,
    get_department_by_id,
    set_department_active_status,
    update_department,
)

from employee_repository import (
    create_employee,
    get_all_employees,
    get_employee_by_id,
    update_employee,
)

from employee_repository import get_all_employees

load_dotenv()

app = Flask(__name__)

configure_security(app)
init_security(app, lambda user_id: get_authorization_state(user_id))
init_csrf(app)
app.jinja_env.filters["procurement_currency"] = lambda value: format(currency_amount(value), ",.2f")


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not authenticated():
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view

def permission_required(permission_code):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if not authenticated():
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))

            if not has_permission(permission_code):
                flash(
                    "You do not have permission to access that page.",
                    "danger",
                )
                return redirect(url_for("dashboard"))

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


@app.context_processor
def inject_permission_helper():
    return {
        "has_permission": has_permission,
    }


@app.route("/")
def index():
    if authenticated():
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if authenticated():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html")

        user = get_user_by_username(username)

        if not user:
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        if not user["is_active"]:
            flash("This account is inactive.", "danger")
            return render_template("login.html")

        if not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "danger")
            return render_template("login.html")

        begin_session(user)

        update_last_login(user["user_id"])

        flash("Login successful.", "success")

        return redirect(url_for("dashboard"))

    return render_template("login.html")




# ==========================================================
# AUDIT LOG HELPER
#
# Audit logging should not stop the original ERP action
# if the audit insert itself unexpectedly fails.
# ==========================================================

def record_audit_event(
    module,
    action,
    entity_type=None,
    entity_id=None,
    description=None,
    user_id=None,
    username=None,
    entity_lookup=None,
    identifier_key=None,
):

    actor_user_id = (
        user_id
        if user_id is not None
        else session.get("user_id")
    )


    actor_username = (
        username
        or session.get("username")
        or "SYSTEM"
    )


    try:

        # AUDIT LOG: Resolve display identifiers without affecting the action.
        if entity_lookup is not None:
            try:
                entity = entity_lookup(entity_id)
                if entity:
                    entity_id = entity.get(identifier_key) or entity_id
            except Exception:
                # Keep the internal ID if the optional display lookup fails.
                app.logger.exception("Unable to resolve audit entity identifier.")

        create_audit_log(
            user_id=actor_user_id,
            username=actor_username,
            module=module,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
        )


    except Exception:

        app.logger.exception(
            "Unable to write ERP audit log."
        )


@app.route("/dashboard")
@login_required
def dashboard():
    summary = get_dashboard_summary()

    return render_template(
        "dashboard.html",
        summary=summary,
    )


@app.route("/departments")
@permission_required("departments.view")
def departments():
    department_list = get_all_departments()

    return render_template(
        "departments/index.html",
        departments=department_list,
    )

@app.route("/departments/add", methods=["GET", "POST"])
@permission_required("departments.manage")
def add_department():
    if request.method == "POST":
        department_code = request.form.get(
            "department_code",
            "",
        ).strip().upper()

        department_name = request.form.get(
            "department_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        if not department_code or not department_name:
            flash(
                "Department code and name are required.",
                "danger",
            )

            return render_template(
                "departments/add.html",
            )

        if len(department_code) > 20:
            flash(
                "Department code must not exceed 20 characters.",
                "danger",
            )

            return render_template(
                "departments/add.html",
            )

        if len(department_name) > 100:
            flash(
                "Department name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "departments/add.html",
            )

        try:
            create_department(
                department_code,
                department_name,
                description or None,
            )

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Department code or department name already exists.",
                    "danger",
                )

                return render_template(
                    "departments/add.html",
                )

            raise

        flash(
            "Department created successfully.",
            "success",
        )

        return redirect(url_for("departments"))

    return render_template(
        "departments/add.html",
    )

        # ==============================================
        # AUDIT - LOGIN
        # ==============================================

    record_audit_event(
        module="AUTH",
        action="LOGIN",
        entity_type="USER",
        entity_id=user["user_id"],
        description=(
            "User logged in successfully."
            ),
        )

@app.route(
    "/departments/<int:department_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("departments.manage")
def edit_department(department_id):
    department = get_department_by_id(department_id)

    if not department:
        flash("Department not found.", "danger")
        return redirect(url_for("departments"))

    if request.method == "POST":
        department_code = request.form.get(
            "department_code",
            "",
        ).strip().upper()

        department_name = request.form.get(
            "department_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        if not department_code or not department_name:
            flash(
                "Department code and name are required.",
                "danger",
            )

            return render_template(
                "departments/edit.html",
                department=department,
            )

        if len(department_code) > 20:
            flash(
                "Department code must not exceed 20 characters.",
                "danger",
            )

            return render_template(
                "departments/edit.html",
                department=department,
            )

        if len(department_name) > 100:
            flash(
                "Department name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "departments/edit.html",
                department=department,
            )

        try:
            update_department(
                department_id,
                department_code,
                department_name,
                description or None,
            )

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Department code or department name already exists.",
                    "danger",
                )

                return render_template(
                    "departments/edit.html",
                    department=department,
                )

            raise

        flash(
            "Department updated successfully.",
            "success",
        )

        return redirect(url_for("departments"))

    return render_template(
        "departments/edit.html",
        department=department,
    )


@app.route(
    "/departments/<int:department_id>/status",
    methods=["POST"],
)
@permission_required("departments.manage")
def change_department_status(department_id):
    department = get_department_by_id(department_id)

    if not department:
        flash("Department not found.", "danger")
        return redirect(url_for("departments"))

    new_status = not bool(department["is_active"])

    set_department_active_status(
        department_id,
        new_status,
    )

    if new_status:
        flash(
            "Department activated successfully.",
            "success",
        )
    else:
        flash(
            "Department deactivated successfully.",
            "success",
        )

    return redirect(url_for("departments"))

@app.route("/employees")
@permission_required("employees.view")
def employees():
    employee_list = get_all_employees()

    return render_template(
        "employees/index.html",
        employees=employee_list,
    )

@app.route("/employees/add", methods=["GET", "POST"])
@permission_required("employees.create")
def add_employee():
    departments = get_active_departments()

    if request.method == "POST":
        employee_number = request.form.get(
            "employee_number",
            "",
        ).strip().upper()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        first_name = request.form.get(
            "first_name",
            "",
        ).strip()

        middle_name = request.form.get(
            "middle_name",
            "",
        ).strip()

        last_name = request.form.get(
            "last_name",
            "",
        ).strip()

        email = request.form.get(
            "email",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        job_title = request.form.get(
            "job_title",
            "",
        ).strip()

        hire_date = request.form.get(
            "hire_date",
            "",
        ).strip()

        if not employee_number or not first_name or not last_name:
            flash(
                "Employee number, first name, and last name are required.",
                "danger",
            )

            return render_template(
                "employees/add.html",
                departments=departments,
            )

        try:
            create_employee(
                employee_number,
                int(department_id) if department_id else None,
                first_name,
                middle_name or None,
                last_name,
                email or None,
                phone or None,
                job_title or None,
                hire_date or None,
            )

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Employee number or email already exists.",
                    "danger",
                )

                return render_template(
                    "employees/add.html",
                    departments=departments,
                )

            raise

        flash(
            "Employee created successfully.",
            "success",
        )

        return redirect(url_for("employees"))

    return render_template(
        "employees/add.html",
        departments=departments,
    )

@app.route(
    "/employees/<int:employee_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("employees.edit")
def edit_employee(employee_id):
    employee = get_employee_by_id(employee_id)

    if not employee:
        flash("Employee not found.", "danger")
        return redirect(url_for("employees"))

    departments = get_all_departments()

    allowed_statuses = [
        "Active",
        "Inactive",
        "On Leave",
        "Resigned",
        "Terminated",
    ]

    if request.method == "POST":
        employee_number = request.form.get(
            "employee_number",
            "",
        ).strip().upper()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        first_name = request.form.get(
            "first_name",
            "",
        ).strip()

        middle_name = request.form.get(
            "middle_name",
            "",
        ).strip()

        last_name = request.form.get(
            "last_name",
            "",
        ).strip()

        email = request.form.get(
            "email",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        job_title = request.form.get(
            "job_title",
            "",
        ).strip()

        hire_date = request.form.get(
            "hire_date",
            "",
        ).strip()

        employment_status = request.form.get(
            "employment_status",
            "",
        ).strip()

        if not employee_number or not first_name or not last_name:
            flash(
                "Employee number, first name, and last name are required.",
                "danger",
            )

            return render_template(
                "employees/edit.html",
                employee=employee,
                departments=departments,
                allowed_statuses=allowed_statuses,
            )

        if employment_status not in allowed_statuses:
            flash(
                "Invalid employment status.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_employee",
                    employee_id=employee_id,
                )
            )

        selected_department_id = None

        if department_id:
            selected_department = get_department_by_id(
                int(department_id)
            )

            if not selected_department:
                flash(
                    "Selected department does not exist.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_employee",
                        employee_id=employee_id,
                    )
                )

            if (
                not selected_department["is_active"]
                and int(department_id) != employee["department_id"]
            ):
                flash(
                    "You cannot assign an employee to an inactive department.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_employee",
                        employee_id=employee_id,
                    )
                )

            selected_department_id = int(department_id)

        try:
            update_employee(
                employee_id,
                employee_number,
                selected_department_id,
                first_name,
                middle_name or None,
                last_name,
                email or None,
                phone or None,
                job_title or None,
                hire_date or None,
                employment_status,
            )

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Employee number or email already exists.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_employee",
                        employee_id=employee_id,
                    )
                )

            raise

        flash(
            "Employee updated successfully.",
            "success",
        )

        return redirect(url_for("employees"))

    return render_template(
        "employees/edit.html",
        employee=employee,
        departments=departments,
        allowed_statuses=allowed_statuses,
    )

@app.route("/inventory/categories")
@permission_required("inventory.view")
def inventory_categories():
    categories = get_all_inventory_categories()

    return render_template(
        "inventory/categories/index.html",
        categories=categories,
    )

@app.route(
    "/inventory/categories/add",
    methods=["GET", "POST"],
)
@permission_required("inventory.categories.manage")
def add_inventory_category():
    if request.method == "POST":
        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        if not category_code or not category_name:
            flash(
                "Category code and name are required.",
                "danger",
            )

            return render_template(
                "inventory/categories/add.html",
            )

        if len(category_code) > 30:
            flash(
                "Category code must not exceed 30 characters.",
                "danger",
            )

            return render_template(
                "inventory/categories/add.html",
            )

        if len(category_name) > 100:
            flash(
                "Category name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "inventory/categories/add.html",
            )

        try:
            category_id = create_inventory_category(
                category_code,
                category_name,
                description or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/categories/add.html")

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Category code or category name already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/categories/add.html",
                )

            raise

        record_audit_event("INVENTORY", "CREATE", "INVENTORY_CATEGORY", category_id,
                           f"Inventory category {category_code} (ID {category_id}) created.")

        flash(
            "Inventory category created successfully.",
            "success",
        )

        return redirect(
            url_for("inventory_categories")
        )

    return render_template(
        "inventory/categories/add.html",
    )

@app.route(
    "/inventory/categories/<int:category_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("inventory.categories.manage")
def edit_inventory_category(category_id):
    category = get_inventory_category_by_id(category_id)

    if not category:
        flash("Inventory category not found.", "danger")
        return redirect(url_for("inventory_categories"))

    if request.method == "POST":
        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        if not category_code or not category_name:
            flash(
                "Category code and name are required.",
                "danger",
            )

            return render_template(
                "inventory/categories/edit.html",
                category=category,
            )

        try:
            update_inventory_category(
                category_id,
                category_code,
                category_name,
                description or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/categories/edit.html", category=category)

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Category code or category name already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/categories/edit.html",
                    category=category,
                )

            raise

        record_audit_event("INVENTORY", "UPDATE", "INVENTORY_CATEGORY", category_id,
                           f"Inventory category {category_code} (ID {category_id}) updated.")

        flash(
            "Inventory category updated successfully.",
            "success",
        )

        return redirect(url_for("inventory_categories"))

    return render_template(
        "inventory/categories/edit.html",
        category=category,
    )


@app.route(
    "/inventory/categories/<int:category_id>/status",
    methods=["POST"],
)
@permission_required("inventory.categories.manage")
def change_inventory_category_status(category_id):
    category = get_inventory_category_by_id(category_id)

    if not category:
        flash("Inventory category not found.", "danger")
        return redirect(url_for("inventory_categories"))

    new_status = not bool(category["is_active"])

    changed = set_inventory_category_active_status(
        category_id,
        new_status,
    )

    if not changed:
        flash("Inventory category status was not changed. Refresh the page before trying again.", "info")
        return redirect(url_for("inventory_categories"))
    record_audit_event("INVENTORY", "ACTIVATE" if new_status else "DEACTIVATE",
                       "INVENTORY_CATEGORY", category_id,
                       f"Inventory category {category['category_code']} (ID {category_id}) {'activated' if new_status else 'deactivated'}.")

    if new_status:
        flash(
            "Inventory category activated successfully.",
            "success",
        )
    else:
        flash(
            "Inventory category deactivated successfully.",
            "success",
        )

    return redirect(url_for("inventory_categories"))



@app.route("/inventory/warehouses")
@permission_required("inventory.view")
def warehouses():
    warehouse_list = get_all_warehouses()

    return render_template(
        "inventory/warehouses/index.html",
        warehouses=warehouse_list,
    )

@app.route(
    "/inventory/warehouses/add",
    methods=["GET", "POST"],
)
@permission_required("inventory.warehouses.manage")
def add_warehouse():
    if request.method == "POST":
        warehouse_code = request.form.get(
            "warehouse_code",
            "",
        ).strip().upper()

        warehouse_name = request.form.get(
            "warehouse_name",
            "",
        ).strip()

        location = request.form.get(
            "location",
            "",
        ).strip()

        if not warehouse_code or not warehouse_name:
            flash(
                "Warehouse code and name are required.",
                "danger",
            )

            return render_template(
                "inventory/warehouses/add.html",
            )

        if len(warehouse_code) > 30:
            flash(
                "Warehouse code must not exceed 30 characters.",
                "danger",
            )

            return render_template(
                "inventory/warehouses/add.html",
            )

        if len(warehouse_name) > 100:
            flash(
                "Warehouse name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "inventory/warehouses/add.html",
            )

        try:
            warehouse_id = create_warehouse(
                warehouse_code,
                warehouse_name,
                location or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/warehouses/add.html")

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Warehouse code or warehouse name already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/warehouses/add.html",
                )

            raise

        record_audit_event("INVENTORY", "CREATE", "WAREHOUSE", warehouse_id,
                           f"Warehouse {warehouse_code} (ID {warehouse_id}) created.")

        flash(
            "Warehouse created successfully.",
            "success",
        )

        return redirect(url_for("warehouses"))

    return render_template(
        "inventory/warehouses/add.html",
    )


@app.route(
    "/inventory/warehouses/<int:warehouse_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("inventory.warehouses.manage")
def edit_warehouse(warehouse_id):
    warehouse = get_warehouse_by_id(warehouse_id)

    if not warehouse:
        flash("Warehouse not found.", "danger")
        return redirect(url_for("warehouses"))

    if request.method == "POST":
        warehouse_code = request.form.get(
            "warehouse_code",
            "",
        ).strip().upper()

        warehouse_name = request.form.get(
            "warehouse_name",
            "",
        ).strip()

        location = request.form.get(
            "location",
            "",
        ).strip()

        if not warehouse_code or not warehouse_name:
            flash(
                "Warehouse code and name are required.",
                "danger",
            )

            return render_template(
                "inventory/warehouses/edit.html",
                warehouse=warehouse,
            )

        try:
            update_warehouse(
                warehouse_id,
                warehouse_code,
                warehouse_name,
                location or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/warehouses/edit.html", warehouse=warehouse)

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Warehouse code or warehouse name already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/warehouses/edit.html",
                    warehouse=warehouse,
                )

            raise

        record_audit_event("INVENTORY", "UPDATE", "WAREHOUSE", warehouse_id,
                           f"Warehouse {warehouse_code} (ID {warehouse_id}) updated.")

        flash(
            "Warehouse updated successfully.",
            "success",
        )

        return redirect(url_for("warehouses"))

    return render_template(
        "inventory/warehouses/edit.html",
        warehouse=warehouse,
    )


@app.route(
    "/inventory/warehouses/<int:warehouse_id>/status",
    methods=["POST"],
)
@permission_required("inventory.warehouses.manage")
def change_warehouse_status(warehouse_id):
    warehouse = get_warehouse_by_id(warehouse_id)

    if not warehouse:
        flash("Warehouse not found.", "danger")
        return redirect(url_for("warehouses"))

    new_status = not bool(warehouse["is_active"])

    changed = set_warehouse_active_status(
        warehouse_id,
        new_status,
    )

    if not changed:
        flash("Warehouse status was not changed. Refresh the page before trying again.", "info")
        return redirect(url_for("warehouses"))
    record_audit_event("INVENTORY", "ACTIVATE" if new_status else "DEACTIVATE",
                       "WAREHOUSE", warehouse_id,
                       f"Warehouse {warehouse['warehouse_code']} (ID {warehouse_id}) {'activated' if new_status else 'deactivated'}.")

    if new_status:
        flash(
            "Warehouse activated successfully.",
            "success",
        )
    else:
        flash(
            "Warehouse deactivated successfully.",
            "success",
        )

    return redirect(url_for("warehouses"))


@app.route("/inventory/items")
@permission_required("inventory.view")
def inventory_items():
    items = get_all_inventory_items()

    return render_template(
        "inventory/items/index.html",
        items=items,
    )

@app.route(
    "/inventory/items/add",
    methods=["GET", "POST"],
)
@permission_required("inventory.items.manage")
def add_inventory_item():
    categories = get_active_inventory_categories()

    if request.method == "POST":
        item_code = request.form.get(
            "item_code",
            "",
        ).strip().upper()

        item_name = request.form.get(
            "item_name",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        unit_of_measure = request.form.get(
            "unit_of_measure",
            "",
        ).strip()

        reorder_level = request.form.get(
            "reorder_level",
            "0",
        ).strip()

        if not item_code or not item_name or not unit_of_measure:
            flash(
                "Item code, item name, and unit of measure are required.",
                "danger",
            )

            return render_template(
                "inventory/items/add.html",
                categories=categories,
            )

        try:
            reorder_level_value = decimal_value(reorder_level, "Reorder level")

        except ValueError as error:
            flash(
                str(error),
                "danger",
            )

            return render_template(
                "inventory/items/add.html",
                categories=categories,
            )

        try:
            item_id = create_inventory_item(
                item_code,
                item_name,
                category_id if category_id else None,
                description or None,
                unit_of_measure,
                reorder_level_value,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/items/add.html", categories=categories)

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Item code already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/items/add.html",
                    categories=categories,
                )

            raise

        record_audit_event("INVENTORY", "CREATE", "INVENTORY_ITEM", item_id,
                           f"Inventory item {item_code} (ID {item_id}) created.")

        flash(
            "Inventory item created successfully.",
            "success",
        )

        return redirect(url_for("inventory_items"))

    return render_template(
        "inventory/items/add.html",
        categories=categories,
    )


@app.route(
    "/inventory/items/<int:item_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("inventory.items.manage")
def edit_inventory_item(item_id):
    item = get_inventory_item_by_id(item_id)

    if not item:
        flash("Inventory item not found.", "danger")
        return redirect(url_for("inventory_items"))

    categories = [category for category in get_all_inventory_categories()
                  if category["is_active"] or category["category_id"] == item["category_id"]]

    if request.method == "POST":
        item_code = request.form.get(
            "item_code",
            "",
        ).strip().upper()

        item_name = request.form.get(
            "item_name",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        unit_of_measure = request.form.get(
            "unit_of_measure",
            "",
        ).strip()

        reorder_level = request.form.get(
            "reorder_level",
            "0",
        ).strip()

        if not item_code or not item_name or not unit_of_measure:
            flash(
                "Item code, item name, and unit of measure are required.",
                "danger",
            )

            return render_template(
                "inventory/items/edit.html",
                item=item,
                categories=categories,
            )

        try:
            reorder_level_value = decimal_value(reorder_level, "Reorder level")

        except ValueError as error:
            flash(
                str(error),
                "danger",
            )

            return render_template(
                "inventory/items/edit.html",
                item=item,
                categories=categories,
            )

        try:
            update_inventory_item(
                item_id,
                item_code,
                item_name,
                category_id if category_id else None,
                description or None,
                unit_of_measure,
                reorder_level_value,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/items/edit.html", item=item, categories=categories)

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Item code already exists.",
                    "danger",
                )

                return render_template(
                    "inventory/items/edit.html",
                    item=item,
                    categories=categories,
                )

            raise

        record_audit_event("INVENTORY", "UPDATE", "INVENTORY_ITEM", item_id,
                           f"Inventory item {item_code} (ID {item_id}) updated.")

        flash(
            "Inventory item updated successfully.",
            "success",
        )

        return redirect(url_for("inventory_items"))

    return render_template(
        "inventory/items/edit.html",
        item=item,
        categories=categories,
    )

@app.route(
    "/inventory/items/<int:item_id>/status",
    methods=["POST"],
)
@permission_required("inventory.items.manage")
def change_inventory_item_status(item_id):
    item = get_inventory_item_by_id(item_id)

    if not item:
        flash("Inventory item not found.", "danger")
        return redirect(url_for("inventory_items"))

    new_status = not bool(item["is_active"])

    changed = set_inventory_item_active_status(
        item_id,
        new_status,
    )

    if not changed:
        flash("Inventory item status was not changed. Refresh the page before trying again.", "info")
        return redirect(url_for("inventory_items"))
    record_audit_event("INVENTORY", "ACTIVATE" if new_status else "DEACTIVATE",
                       "INVENTORY_ITEM", item_id,
                       f"Inventory item {item['item_code']} (ID {item_id}) {'activated' if new_status else 'deactivated'}.")

    if new_status:
        flash(
            "Inventory item activated successfully.",
            "success",
        )
    else:
        flash(
            "Inventory item deactivated successfully.",
            "success",
        )

    return redirect(url_for("inventory_items"))


@app.route("/inventory/stock")
@permission_required("inventory.view")
def inventory_stock():
    stock_records = get_all_stock()

    return render_template(
        "inventory/stock/index.html",
        stock_records=stock_records,
    )

def _record_manual_stock_audit(result, action, item_id, warehouse_id, items, warehouses):
    if not result.created:
        return
    item_code = next((item.get("item_code") for item in items if item["item_id"] == item_id), None) or str(item_id)
    warehouse_code = next((warehouse.get("warehouse_code") for warehouse in warehouses
                           if warehouse["warehouse_id"] == warehouse_id), None) or str(warehouse_id)
    record_audit_event("INVENTORY", action, "STOCK_MOVEMENT", result.movement_id,
                       f"Manual stock movement {result.movement_id}: {action.replace('_', ' ').lower()} for item {item_code} (ID {item_id}) at warehouse {warehouse_code} (ID {warehouse_id}).")


@app.route(
    "/inventory/stock/in",
    methods=["GET", "POST"],
)
@permission_required("inventory.stock.manage")
def inventory_stock_in():
    submission_id = request.form.get("submission_id", "") if request.method == "POST" else str(uuid.uuid4())
    items = get_all_inventory_items()
    warehouses = get_all_warehouses()

    active_items = [
        item
        for item in items
        if item["is_active"]
    ]

    active_warehouses = [
        warehouse
        for warehouse in warehouses
        if warehouse["is_active"]
    ]

    if request.method == "POST":
        item_id = request.form.get(
            "item_id",
            "",
        ).strip()

        warehouse_id = request.form.get(
            "warehouse_id",
            "",
        ).strip()

        quantity = request.form.get(
            "quantity",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()

        if not item_id or not warehouse_id or not quantity:
            flash(
                "Item, warehouse, and quantity are required.",
                "danger",
            )

            return render_template(
                "inventory/stock/in.html",
                items=active_items,
                warehouses=active_warehouses,
                submission_id=submission_id,
            )

        try:
            if not item_id.isdecimal() or not warehouse_id.isdecimal():
                raise ValueError("Select a valid item and warehouse.")
            item_id_value = int(item_id)
            warehouse_id_value = int(warehouse_id)
            quantity_value = decimal_value(quantity, "Quantity", positive=True)

        except ValueError as error:
            flash(
                str(error) or "Quantity must be greater than zero.",
                "danger",
            )

            return render_template(
                "inventory/stock/in.html",
                items=active_items,
                warehouses=active_warehouses,
                submission_id=submission_id,
            )

        try:
            result = stock_in(item_id_value, warehouse_id_value, quantity_value,
                              notes or None, session["user_id"], submission_id=submission_id)
        except ValueError as error:
            flash(str(error), "danger")
            return render_template("inventory/stock/in.html", items=active_items,
                                   warehouses=active_warehouses, submission_id=submission_id)

        _record_manual_stock_audit(result, "STOCK_IN", item_id_value, warehouse_id_value,
                                   items, warehouses)

        flash(
            "Stock added successfully.",
            "success",
        )

        return redirect(url_for("inventory_stock"))

    return render_template(
        "inventory/stock/in.html",
        items=active_items,
        warehouses=active_warehouses,
        submission_id=submission_id,
    )


@app.route(
    "/inventory/stock/out",
    methods=["GET", "POST"],
)
@permission_required("inventory.stock.manage")
def inventory_stock_out():
    submission_id = request.form.get("submission_id", "") if request.method == "POST" else str(uuid.uuid4())
    items = get_all_inventory_items()
    warehouses = get_all_warehouses()

    active_items = [
        item
        for item in items
        if item["is_active"]
    ]

    active_warehouses = [
        warehouse
        for warehouse in warehouses
        if warehouse["is_active"]
    ]

    if request.method == "POST":
        item_id = request.form.get("item_id", "").strip()
        warehouse_id = request.form.get("warehouse_id", "").strip()
        quantity = request.form.get("quantity", "").strip()
        notes = request.form.get("notes", "").strip()

        try:
            if not item_id.isdecimal() or not warehouse_id.isdecimal():
                raise ValueError("Select a valid item and warehouse.")
            item_id_value = int(item_id)
            warehouse_id_value = int(warehouse_id)
            quantity_value = decimal_value(quantity, "Quantity", positive=True)

        except ValueError as error:
            flash(
                str(error) or "Item, warehouse, and a quantity greater than zero are required.",
                "danger",
            )

            return render_template(
                "inventory/stock/out.html",
                items=active_items,
                warehouses=active_warehouses,
                submission_id=submission_id,
            )

        try:
            result = stock_out(
                item_id_value,
                warehouse_id_value,
                quantity_value,
                notes or None,
                session["user_id"],
                submission_id=submission_id,
            )

        except ValueError as error:
            flash(str(error), "danger")

            return render_template(
                "inventory/stock/out.html",
                items=active_items,
                warehouses=active_warehouses,
                submission_id=submission_id,
            )

        _record_manual_stock_audit(result, "STOCK_OUT", item_id_value, warehouse_id_value,
                                   items, warehouses)

        flash(
            "Stock removed successfully.",
            "success",
        )

        return redirect(url_for("inventory_stock"))

    return render_template(
        "inventory/stock/out.html",
        items=active_items,
        warehouses=active_warehouses,
        submission_id=submission_id,
    )


@app.route("/inventory/stock/movements")
@permission_required("inventory.view")
def stock_movement_history():
    return _inventory_report("inventory/stock/movements.html", get_movement_page, movements=True)


@app.route("/inventory/stock/reconciliation")
@permission_required("inventory.view")
def inventory_reconciliation():
    return _inventory_report("inventory/stock/reconciliation.html", get_reconciliation_page, movements=False)


def _inventory_report(template, reader, *, movements):
    filters = {}
    status = 200
    try:
        filters = report_filters(request.args, movements=movements)
        report = reader(**filters)
    except ValueError as error:
        flash(str(error), "danger")
        status = 400
        report = dict(rows=[], total=0, page=1, pages=1, page_size=50)
    links = {}
    for label, target in (("previous", report['page'] - 1), ("next", report['page'] + 1)):
        if 1 <= target <= report['pages']:
            links[label] = url_for(request.endpoint, **dict(filters, page=target))
    return render_template(template, movements=report['rows'], report=report,
                           filters=filters, page_links=links,
                           items=get_all_inventory_items(), warehouses=get_all_warehouses()), status


@app.route("/procurement/suppliers")
@permission_required("procurement.view")
def suppliers():
    supplier_list = get_all_suppliers()

    return render_template(
        "procurement/suppliers/index.html",
        suppliers=supplier_list,
    )


@app.route(
    "/procurement/suppliers/add",
    methods=["GET", "POST"],
)
@permission_required("procurement.suppliers.manage")
def add_supplier():
    if request.method == "POST":
        supplier_code = request.form.get(
            "supplier_code",
            "",
        ).strip().upper()

        supplier_name = request.form.get(
            "supplier_name",
            "",
        ).strip()

        contact_person = request.form.get(
            "contact_person",
            "",
        ).strip()

        email = request.form.get(
            "email",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        address = request.form.get(
            "address",
            "",
        ).strip()

        if not supplier_code or not supplier_name:
            flash(
                "Supplier code and supplier name are required.",
                "danger",
            )

            return render_template(
                "procurement/suppliers/add.html",
            )

        try:
            supplier_id = create_supplier(
                supplier_code,
                supplier_name,
                contact_person or None,
                email or None,
                phone or None,
                address or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("procurement/suppliers/add.html")

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Supplier code already exists.",
                    "danger",
                )

                return render_template(
                    "procurement/suppliers/add.html",
                )

            raise

        record_audit_event("PROCUREMENT", "CREATE", "SUPPLIER", supplier_id,
                           f"Supplier {supplier_code} (ID {supplier_id}) created.")

        flash(
            "Supplier created successfully.",
            "success",
        )

        return redirect(url_for("suppliers"))

    return render_template(
        "procurement/suppliers/add.html",
    )


@app.route(
    "/procurement/suppliers/<int:supplier_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("procurement.suppliers.manage")
def edit_supplier(supplier_id):
    supplier = get_supplier_by_id(supplier_id)

    if not supplier:
        flash("Supplier not found.", "danger")
        return redirect(url_for("suppliers"))

    if request.method == "POST":
        supplier_code = request.form.get(
            "supplier_code",
            "",
        ).strip().upper()

        supplier_name = request.form.get(
            "supplier_name",
            "",
        ).strip()

        contact_person = request.form.get(
            "contact_person",
            "",
        ).strip()

        email = request.form.get(
            "email",
            "",
        ).strip()

        phone = request.form.get(
            "phone",
            "",
        ).strip()

        address = request.form.get(
            "address",
            "",
        ).strip()

        if not supplier_code or not supplier_name:
            flash(
                "Supplier code and supplier name are required.",
                "danger",
            )

            return render_template(
                "procurement/suppliers/edit.html",
                supplier=supplier,
            )

        try:
            update_supplier(
                supplier_id,
                supplier_code,
                supplier_name,
                contact_person or None,
                email or None,
                phone or None,
                address or None,
            )

        except ValueError as error:
            flash(str(error), "danger")
            return render_template("procurement/suppliers/edit.html", supplier=supplier)

        except Exception as error:
            if getattr(error, "errno", None) == 1062:
                flash(
                    "Supplier code already exists.",
                    "danger",
                )

                return render_template(
                    "procurement/suppliers/edit.html",
                    supplier=supplier,
                )

            raise

        record_audit_event("PROCUREMENT", "UPDATE", "SUPPLIER", supplier_id,
                           f"Supplier {supplier_code} (ID {supplier_id}) updated.")

        flash(
            "Supplier updated successfully.",
            "success",
        )

        return redirect(url_for("suppliers"))

    return render_template(
        "procurement/suppliers/edit.html",
        supplier=supplier,
    )


@app.route(
    "/procurement/suppliers/<int:supplier_id>/status",
    methods=["POST"],
)
@permission_required("procurement.suppliers.manage")
def change_supplier_status(supplier_id):
    supplier = get_supplier_by_id(supplier_id)

    if not supplier:
        flash("Supplier not found.", "danger")
        return redirect(url_for("suppliers"))

    new_status = not bool(supplier["is_active"])

    set_supplier_active_status(
        supplier_id,
        new_status,
    )

    record_audit_event("PROCUREMENT", "ACTIVATE" if new_status else "DEACTIVATE",
                       "SUPPLIER", supplier_id,
                       f"Supplier {supplier['supplier_code']} (ID {supplier_id}) {'activated' if new_status else 'deactivated'}.")

    if new_status:
        flash(
            "Supplier activated successfully.",
            "success",
        )
    else:
        flash(
            "Supplier deactivated successfully.",
            "success",
        )

    return redirect(url_for("suppliers"))


@app.route("/procurement/requests")
@permission_required("procurement.view")
def purchase_requests():
    requests_list = get_all_purchase_requests()

    return render_template(
        "procurement/requests/index.html",
        purchase_requests=requests_list,
    )

@app.route(
    "/procurement/requests/add",
    methods=["GET", "POST"],
)
@permission_required("procurement.requests.create")
def add_purchase_request():
    departments = get_active_departments()

    if request.method == "POST":
        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        purpose = request.form.get(
            "purpose",
            "",
        ).strip()

        if not department_id or not purpose:
            flash(
                "Department and purpose are required.",
                "danger",
            )

            return render_template(
                "procurement/requests/add.html",
                departments=departments,
            )

        try:
            department_id_value = int(
                department_id
            )
        except ValueError:
            flash(
                "Invalid department.",
                "danger",
            )

            return render_template(
                "procurement/requests/add.html",
                departments=departments,
            )

        department = get_department_by_id(
            department_id_value
        )

        if (
            not department
            or not department["is_active"]
        ):
            flash(
                "Selected department is invalid or inactive.",
                "danger",
            )

            return render_template(
                "procurement/requests/add.html",
                departments=departments,
            )

        try:
            request_id, request_number = create_purchase_request(
                session["user_id"], department_id_value, purpose)
        except ValueError as error:
            flash(str(error), "danger")
            return render_template("procurement/requests/add.html", departments=departments)

        flash(
            f"Purchase request {request_number} created successfully.",
            "success",
        )

        return redirect(
            url_for("purchase_requests")
        )

    return render_template(
        "procurement/requests/add.html",
        departments=departments,
    )

@app.route(
    "/procurement/requests/<int:request_id>"
)
@permission_required("procurement.view")
def view_purchase_request(request_id):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )

        return redirect(
            url_for("purchase_requests")
        )

    items = get_purchase_request_items(
        request_id
    )

    linked_orders = get_purchase_orders_by_request(request_id)
    active_order = next((order for order in linked_orders if order["status"] != "CANCELLED"), None)

    return render_template(
        "procurement/requests/view.html",
        purchase_request=purchase_request,
        items=items,
        linked_orders=linked_orders,
        active_order=active_order,
    )





@app.route(
    "/procurement/requests/<int:request_id>/items/add",
    methods=["GET", "POST"],
)
@permission_required("procurement.requests.create")
def add_purchase_request_item_route(request_id):
    purchase_request = get_purchase_request_by_id(request_id)

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(url_for("purchase_requests"))

    if purchase_request["status"] != "DRAFT":
        flash(
            "Items can only be added to draft purchase requests.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    inventory_items = get_active_inventory_items()

    if request.method == "POST":
        item_id = request.form.get("item_id", "").strip()
        quantity = request.form.get("quantity", "").strip()

        estimated_unit_cost = request.form.get(
            "estimated_unit_cost",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()

        if not item_id or not quantity:
            flash(
                "Item and quantity are required.",
                "danger",
            )

            return render_template(
                "procurement/requests/add_item.html",
                purchase_request=purchase_request,
                inventory_items=inventory_items,
            )

        try:
            item_id_value = int(item_id)
            quantity_value = decimal_value(quantity, "Quantity", positive=True)

            if quantity_value <= 0:
                raise ValueError

        except ValueError as error:
            flash(
                str(error) or "Quantity must be greater than zero.",
                "danger",
            )

            return render_template(
                "procurement/requests/add_item.html",
                purchase_request=purchase_request,
                inventory_items=inventory_items,
            )

        cost_value = None

        if estimated_unit_cost:
            try:
                cost_value = decimal_value(estimated_unit_cost, "Estimated unit cost")

                if cost_value < 0:
                    raise ValueError

            except ValueError as error:
                flash(
                    str(error) or "Estimated unit cost must be zero or greater.",
                    "danger",
                )

                return render_template(
                    "procurement/requests/add_item.html",
                    purchase_request=purchase_request,
                    inventory_items=inventory_items,
                )

        try:
            add_purchase_request_item(
                request_id,
                item_id_value,
                quantity_value,
                cost_value,
                notes or None,
            )
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(request.url)

        flash(
            "Item added to purchase request successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    return render_template(
        "procurement/requests/add_item.html",
        purchase_request=purchase_request,
        inventory_items=inventory_items,
    )

@app.route(
    "/procurement/requests/<int:request_id>/items/<int:request_item_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("procurement.requests.create")
def edit_purchase_request_item_route(
    request_id,
    request_item_id,
):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "DRAFT":
        flash(
            "Items can only be edited while the purchase request is in Draft status.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    request_item = get_purchase_request_item_by_id(
        request_item_id
    )

    if (
        not request_item
        or request_item["request_id"] != request_id
    ):
        flash(
            "Purchase request item not found.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    inventory_items = get_active_inventory_items()

    if request.method == "POST":
        item_id = request.form.get(
            "item_id",
            "",
        ).strip()

        quantity = request.form.get(
            "quantity",
            "",
        ).strip()

        estimated_unit_cost = request.form.get(
            "estimated_unit_cost",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()

        if not item_id or not quantity:
            flash(
                "Item and quantity are required.",
                "danger",
            )

            return render_template(
                "procurement/requests/edit_item.html",
                purchase_request=purchase_request,
                request_item=request_item,
                inventory_items=inventory_items,
            )

        try:
            item_id_value = int(item_id)
            quantity_value = decimal_value(quantity, "Quantity", positive=True)

            if quantity_value <= 0:
                raise ValueError

        except ValueError as error:
            flash(
                str(error) or "Quantity must be greater than zero.",
                "danger",
            )

            return render_template(
                "procurement/requests/edit_item.html",
                purchase_request=purchase_request,
                request_item=request_item,
                inventory_items=inventory_items,
            )

        cost_value = None

        if estimated_unit_cost:
            try:
                cost_value = decimal_value(estimated_unit_cost, "Estimated unit cost")

                if cost_value < 0:
                    raise ValueError

            except ValueError as error:
                flash(
                    str(error) or "Estimated unit cost must be zero or greater.",
                    "danger",
                )

                return render_template(
                    "procurement/requests/edit_item.html",
                    purchase_request=purchase_request,
                    request_item=request_item,
                    inventory_items=inventory_items,
                )

        try:
            update_purchase_request_item(
                request_item_id,
                item_id_value,
                quantity_value,
                cost_value,
                notes or None,
            )
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(request.url)

        flash(
            "Purchase request item updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    return render_template(
        "procurement/requests/edit_item.html",
        purchase_request=purchase_request,
        request_item=request_item,
        inventory_items=inventory_items,
    )

@app.route(
    "/procurement/requests/<int:request_id>/items/<int:request_item_id>/delete",
    methods=["POST"],
)
@permission_required("procurement.requests.create")
def delete_purchase_request_item_route(
    request_id,
    request_item_id,
):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "DRAFT":
        flash(
            "Items can only be removed while the purchase request is in Draft status.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    request_item = get_purchase_request_item_by_id(
        request_item_id
    )

    if (
        not request_item
        or request_item["request_id"] != request_id
    ):
        flash(
            "Purchase request item not found.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    try:
        delete_purchase_request_item(request_item_id)
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("view_purchase_request", request_id=request_id))

    flash(
        "Purchase request item removed successfully.",
        "success",
    )

    return redirect(
        url_for(
            "view_purchase_request",
            request_id=request_id,
        )
    )


@app.route(
    "/procurement/requests/<int:request_id>/submit",
    methods=["POST"],
)
@permission_required("procurement.requests.create")
def submit_purchase_request_route(request_id):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "DRAFT":
        flash(
            "Only draft purchase requests can be submitted.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    items = get_purchase_request_items(
        request_id
    )

    if not items:
        flash(
            "You cannot submit a purchase request without any items.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    submitted = submit_purchase_request(
        request_id
    )

    if not submitted:
        flash(
            "Purchase request could not be submitted.",
            "danger",
        )
    else:
        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PROCUREMENT",
            action="SUBMIT",
            entity_type="PURCHASE_REQUEST",
            entity_id=purchase_request.get("request_number") or request_id,
            description="Purchase request submitted.",
        )

        flash(
            "Purchase request submitted successfully.",
            "success",
        )

    return redirect(
        url_for(
            "view_purchase_request",
            request_id=request_id,
        )
    )

@app.route(
    "/procurement/requests/<int:request_id>/approve",
    methods=["POST"],
)
@permission_required("procurement.requests.approve")
def approve_purchase_request_route(request_id):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "SUBMITTED":
        flash(
            "Only submitted purchase requests can be approved.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    approved = approve_purchase_request(
        request_id,
        session["user_id"],
    )

    if approved:
        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PROCUREMENT",
            action="APPROVE",
            entity_type="PURCHASE_REQUEST",
            entity_id=purchase_request.get("request_number") or request_id,
            description="Purchase request approved.",
        )

        flash(
            "Purchase request approved successfully.",
            "success",
        )
    else:
        flash(
            "Purchase request could not be approved.",
            "danger",
        )

    return redirect(
        url_for(
            "view_purchase_request",
            request_id=request_id,
        )
    )

@app.route(
    "/procurement/requests/<int:request_id>/reject",
    methods=["GET", "POST"],
)
@permission_required("procurement.requests.approve")
def reject_purchase_request_route(request_id):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "SUBMITTED":
        flash(
            "Only submitted purchase requests can be rejected.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    if request.method == "POST":
        rejection_reason = request.form.get(
            "rejection_reason",
            "",
        ).strip()

        if not rejection_reason:
            flash(
                "Rejection reason is required.",
                "danger",
            )
            return render_template(
                "procurement/requests/reject.html",
                purchase_request=purchase_request,
            )

        try:
            rejected = reject_purchase_request(
                request_id,
                rejection_reason,
            )
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(request.url)

        if rejected:
            # AUDIT LOG: The business action has committed successfully.
            record_audit_event(
                module="PROCUREMENT",
                action="REJECT",
                entity_type="PURCHASE_REQUEST",
                entity_id=purchase_request.get("request_number") or request_id,
                description="Purchase request rejected.",
            )

            flash(
                "Purchase request rejected successfully.",
                "success",
            )
        else:
            flash(
                "Purchase request could not be rejected.",
                "danger",
            )

        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    return render_template(
        "procurement/requests/reject.html",
        purchase_request=purchase_request,
    )

@app.route("/procurement/orders")
@permission_required("procurement.view")
def purchase_orders():
    orders = get_all_purchase_orders()

    return render_template(
        "procurement/orders/index.html",
        purchase_orders=orders,
    )

@app.route(
    "/procurement/requests/<int:request_id>/create-order",
    methods=["GET", "POST"],
)
@permission_required("procurement.orders.manage")
def create_purchase_order(request_id):
    purchase_request = get_purchase_request_by_id(
        request_id
    )

    if not purchase_request:
        flash(
            "Purchase request not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_requests")
        )

    if purchase_request["status"] != "APPROVED":
        flash(
            "Only approved purchase requests can become purchase orders.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_request",
                request_id=request_id,
            )
        )

    existing_orders = get_purchase_orders_by_request(request_id)
    active_order = next((order for order in existing_orders if order["status"] != "CANCELLED"), None)
    if active_order:
        flash("A purchase order already exists for this purchase request.", "info")
        return redirect(url_for("view_purchase_order", purchase_order_id=active_order["purchase_order_id"]))
    if not get_purchase_request_items(request_id):
        flash("Purchase request has no items.", "danger")
        return redirect(url_for("view_purchase_request", request_id=request_id))

    suppliers = get_active_suppliers()

    if request.method == "POST":
        supplier_id = request.form.get(
            "supplier_id",
            "",
        ).strip()

        expected_delivery_date = request.form.get(
            "expected_delivery_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()

        if not supplier_id:
            flash(
                "Supplier is required.",
                "danger",
            )

            return render_template(
                "procurement/orders/create.html",
                purchase_request=purchase_request,
                suppliers=suppliers,
            )

        try:
            supplier_id_value = int(
                supplier_id
            )

        except ValueError:
            flash(
                "Invalid supplier.",
                "danger",
            )

            return render_template(
                "procurement/orders/create.html",
                purchase_request=purchase_request,
                suppliers=suppliers,
            )

        supplier = get_supplier_by_id(
            supplier_id_value
        )

        if (
            not supplier
            or not supplier["is_active"]
        ):
            flash(
                "Selected supplier is invalid or inactive.",
                "danger",
            )

            return render_template(
                "procurement/orders/create.html",
                purchase_request=purchase_request,
                suppliers=suppliers,
            )

        delivery_date = None

        if expected_delivery_date:
            try:
                delivery_date = date.fromisoformat(
                    expected_delivery_date
                )

            except ValueError:
                flash(
                    "Expected delivery date is invalid. Please select a valid date.",
                    "danger",
                )

                return render_template(
                    "procurement/orders/create.html",
                    purchase_request=purchase_request,
                    suppliers=suppliers,
                )

        try:
            purchase_order_id, po_number = (
                create_purchase_order_from_request(
                    request_id=request_id,
                    supplier_id=supplier_id_value,
                    created_by=session["user_id"],
                    expected_delivery_date=delivery_date,
                    notes=notes or None,
                )
            )

        except ValueError as error:
            flash(
                str(error),
                "danger",
            )

            return redirect(
                url_for(
                    "view_purchase_request",
                    request_id=request_id,
                )
            )

        record_audit_event("PROCUREMENT", "CREATE", "PURCHASE_ORDER", purchase_order_id,
                           f"Purchase order {po_number} (ID {purchase_order_id}) created.")

        flash(
            f"Purchase order {po_number} created successfully.",
            "success",
        )

        return redirect(
            url_for("purchase_orders")
        )

    return render_template(
        "procurement/orders/create.html",
        purchase_request=purchase_request,
        suppliers=suppliers,
    )


@app.route(
    "/procurement/orders/<int:purchase_order_id>"
)
@permission_required("procurement.view")
def view_purchase_order(purchase_order_id):
    purchase_order = get_purchase_order_by_id(
        purchase_order_id
    )

    if not purchase_order:
        flash(
            "Purchase order not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_orders")
        )

    items = get_purchase_order_items(
        purchase_order_id
    )

    receipts = get_goods_receipts_by_purchase_order(purchase_order_id)
    total = _purchase_order_display_totals(items)

    return render_template(
        "procurement/orders/view.html",
        purchase_order=purchase_order,
        items=items,
        receipts=receipts,
        total=total,
    )


def _purchase_order_display_totals(items):
    # Display line amounts rounded to cents; sum the displayed amounts exactly.
    with localcontext() as context:
        context.prec = 40
        for item in items:
            item["line_total"] = currency_amount(item["quantity"] * item["unit_cost"])
        return sum((item["line_total"] for item in items), Decimal("0.00"))


@app.route("/procurement/orders/<int:purchase_order_id>/print")
@permission_required("procurement.view")
def print_purchase_order(purchase_order_id):
    purchase_order = get_purchase_order_by_id(purchase_order_id)
    if not purchase_order:
        flash("Purchase order not found.", "danger")
        return redirect(url_for("purchase_orders"))
    items = get_purchase_order_items(purchase_order_id)
    supplier = get_supplier_by_id(purchase_order["supplier_id"])
    return render_template(
        "procurement/orders/print.html", purchase_order=purchase_order,
        supplier=supplier or {}, items=items, total=_purchase_order_display_totals(items))


@app.route(
    "/procurement/orders/<int:purchase_order_id>/items/<int:purchase_order_item_id>/edit-cost",
    methods=["GET", "POST"],
)
@permission_required("procurement.orders.manage")
def edit_purchase_order_item_cost_route(
    purchase_order_id,
    purchase_order_item_id,
):
    purchase_order = get_purchase_order_by_id(
        purchase_order_id
    )

    if not purchase_order:
        flash(
            "Purchase order not found.",
            "danger",
        )
        return redirect(
            url_for("purchase_orders")
        )

    if purchase_order["status"] != "DRAFT":
        flash(
            "Unit cost can only be edited while the purchase order is in Draft status.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_order",
                purchase_order_id=purchase_order_id,
            )
        )

    purchase_order_item = get_purchase_order_item_by_id(
        purchase_order_item_id
    )

    if (
        not purchase_order_item
        or purchase_order_item["purchase_order_id"]
        != purchase_order_id
    ):
        flash(
            "Purchase order item not found.",
            "danger",
        )
        return redirect(
            url_for(
                "view_purchase_order",
                purchase_order_id=purchase_order_id,
            )
        )

    if request.method == "POST":
        unit_cost = request.form.get(
            "unit_cost",
            "",
        ).strip()

        try:
            unit_cost_value = decimal_value(unit_cost, "Unit cost")

            if unit_cost_value < 0:
                raise ValueError

        except ValueError as error:
            flash(
                str(error) or "Unit cost must be zero or greater.",
                "danger",
            )

            return render_template(
                "procurement/orders/edit_cost.html",
                purchase_order=purchase_order,
                purchase_order_item=purchase_order_item,
            )

        try:
            update_purchase_order_item_cost(
                purchase_order_item_id,
                unit_cost_value,
            )
        except ValueError as error:
            flash(str(error), "danger")
            return redirect(request.url)

        record_audit_event("PROCUREMENT", "UPDATE_COST", "PURCHASE_ORDER", purchase_order_id,
                           f"Purchase order {purchase_order['po_number']} (ID {purchase_order_id}) item {purchase_order_item_id} cost updated.")

        flash(
            "Purchase order item cost updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_purchase_order",
                purchase_order_id=purchase_order_id,
            )
        )

    return render_template(
        "procurement/orders/edit_cost.html",
        purchase_order=purchase_order,
        purchase_order_item=purchase_order_item,
    )


# ==========================================================
# SEND PURCHASE ORDER ROUTE
# Changes PO status from DRAFT -> SENT
# ==========================================================

@app.route(
    "/procurement/orders/<int:purchase_order_id>/send",
    methods=["POST"],
)
@permission_required("procurement.orders.manage")
def send_purchase_order_route(purchase_order_id):

    # # Get the Purchase Order first
    purchase_order = get_purchase_order_by_id(
        purchase_order_id
    )

    # # Make sure the PO exists
    if not purchase_order:
        flash(
            "Purchase order not found.",
            "danger",
        )

        return redirect(
            url_for("purchase_orders")
        )

    # # Only DRAFT purchase orders can be sent
    if purchase_order["status"] != "DRAFT":
        flash(
            "Only draft purchase orders can be sent.",
            "danger",
        )

        return redirect(
            url_for(
                "view_purchase_order",
                purchase_order_id=purchase_order_id,
            )
        )

    # # Change DRAFT -> SENT
    sent = send_purchase_order(
        purchase_order_id
    )

    # # Show result message
    if sent:
        record_audit_event("PROCUREMENT", "MARK_SENT", "PURCHASE_ORDER", purchase_order_id,
                           f"Purchase order {purchase_order['po_number']} (ID {purchase_order_id}) manually issued.")
        flash(
            "Purchase order marked as sent (manually issued).",
            "success",
        )
    else:
        flash(
            "Purchase order could not be sent.",
            "danger",
        )

    # # Return to the PO details page
    return redirect(
        url_for(
            "view_purchase_order",
            purchase_order_id=purchase_order_id,
        )
    )


# ==========================================================
# GOODS RECEIPTS LIST
# Shows POs that can still receive supplier deliveries.
# ==========================================================

@app.route("/procurement/receipts")
@permission_required("procurement.view")
def goods_receipts():

    # # Get SENT / PARTIALLY_RECEIVED purchase orders
    purchase_orders = get_receivable_purchase_orders()

    # # Display them on the Goods Receipts page
    return render_template(
        "procurement/receipts/index.html",
        purchase_orders=purchase_orders,
    )


# ==========================================================
# RECEIVE PURCHASE ORDER ITEMS
#
# GET:
# Displays the receiving form.
#
# POST:
# Creates the Goods Receipt and updates Inventory.
# ==========================================================

@app.route(
    "/procurement/receipts/<int:purchase_order_id>/receive",
    methods=["GET", "POST"],
)
@permission_required("procurement.receipts.manage")
def receive_purchase_order(purchase_order_id):

    # ======================================================
    # GET PURCHASE ORDER
    # ======================================================

    submission_id = request.form.get("submission_id", "") if request.method == "POST" else str(uuid.uuid4())
    # Completed POs must still reach repository idempotency validation on POST.
    purchase_order = (get_purchase_order_by_id(purchase_order_id) if request.method == "POST"
                      else get_receivable_purchase_order_by_id(purchase_order_id))

    if not purchase_order:

        flash(
            "Purchase order is not available for receiving.",
            "danger",
        )

        return redirect(
            url_for("goods_receipts")
        )


    # ======================================================
    # GET REMAINING PO ITEMS
    # ======================================================

    items = get_receivable_purchase_order_items(
        purchase_order_id
    )


    # ======================================================
    # GET ACTIVE WAREHOUSES
    # ======================================================

    all_warehouses = get_all_warehouses()

    warehouses = [
        warehouse
        for warehouse in all_warehouses
        if warehouse["is_active"]
    ]


    # ======================================================
    # FORM SUBMITTED
    # ======================================================

    if request.method == "POST":

        # ==================================================
        # GET WAREHOUSE
        # ==================================================

        warehouse_id = request.form.get(
            "warehouse_id",
            "",
        ).strip()

        if not warehouse_id:

            flash(
                "Receiving warehouse is required.",
                "danger",
            )

            return render_template(
                "procurement/receipts/receive.html",
                purchase_order=purchase_order,
                items=items,
                warehouses=warehouses,
                submission_id=submission_id,
            )


        try:
            warehouse_id_value = int(
                warehouse_id
            )

        except ValueError:

            flash(
                "Invalid warehouse.",
                "danger",
            )

            return render_template(
                "procurement/receipts/receive.html",
                purchase_order=purchase_order,
                items=items,
                warehouses=warehouses,
                submission_id=submission_id,
            )


        # ==================================================
        # GET RECEIPT NOTES
        # ==================================================

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # BUILD RECEIVED ITEMS DICTIONARY
        #
        # Example:
        #
        # {
        #     1: "5",
        #     2: "0"
        # }
        # ==================================================

        received_items = {}

        # Read the original submitted item keys, including items since fully
        # received, so a retry can match its original persisted delivery.
        for field_name in request.form:
            if field_name.startswith("quantity_received_"):
                received_items[field_name.removeprefix("quantity_received_")] = request.form.get(field_name, "0").strip()


        # ==================================================
        # CREATE GOODS RECEIPT
        #
        # This function also:
        # - updates Inventory stock
        # - creates Stock Movement history
        # - updates PO status
        # ==================================================

        try:

            receipt_result = create_goods_receipt(
                purchase_order_id=purchase_order_id,
                warehouse_id=warehouse_id_value,
                received_by=session["user_id"],
                received_items=received_items,
                notes=notes or None,
                submission_id=submission_id,
            )

            receipt_id, receipt_number, new_status = receipt_result

        except ValueError as error:

            flash(
                str(error),
                "danger",
            )

            return render_template(
                "procurement/receipts/receive.html",
                purchase_order=purchase_order,
                items=items,
                warehouses=warehouses,
                submission_id=submission_id,
            )


        # ==================================================
        # SUCCESS
        # ==================================================

        if receipt_result.created:
            record_audit_event("PROCUREMENT", "RECEIVE", "GOODS_RECEIPT", receipt_id,
                               f"Goods receipt {receipt_number} (ID {receipt_id}) received for purchase order {purchase_order['po_number']} (ID {purchase_order_id}).")

        flash(
            f"Goods receipt {receipt_number} saved successfully.",
            "success",
        )

        return redirect(
            url_for("view_goods_receipt", receipt_id=receipt_id)
        )


    # ======================================================
    # DISPLAY FORM
    # ======================================================

    return render_template(
        "procurement/receipts/receive.html",
        purchase_order=purchase_order,
        items=items,
        warehouses=warehouses,
        submission_id=submission_id,
    )


# ==========================================================
# GOODS RECEIPT HISTORY
#
# Shows all completed receipt records.
# ==========================================================

@app.route("/procurement/receipts/history")
@permission_required("procurement.view")
def goods_receipt_history():

    receipts = get_all_goods_receipts()

    return render_template(
        "procurement/receipts/history.html",
        receipts=receipts,
    )

# ==========================================================
# VIEW GOODS RECEIPT DETAILS
#
# Shows one receipt and the exact items received.
# ==========================================================

@app.route(
    "/procurement/receipts/history/<int:receipt_id>"
)
@permission_required("procurement.view")
def view_goods_receipt(receipt_id):

    # # Get receipt information
    receipt = get_goods_receipt_by_id(
        receipt_id
    )

    # # Make sure receipt exists
    if not receipt:

        flash(
            "Goods receipt not found.",
            "danger",
        )

        return redirect(
            url_for("goods_receipt_history")
        )

    # # Get items inside this receipt
    items = get_goods_receipt_items(
        receipt_id
    )

    # # Display receipt details page
    return render_template(
        "procurement/receipts/view.html",
        receipt=receipt,
        items=items,
    )


# ==========================================================
# CANCEL PURCHASE ORDER
# ==========================================================

@app.route(
    "/procurement/orders/<int:purchase_order_id>/cancel",
    methods=["POST"],
)
@permission_required("procurement.orders.manage")
def cancel_purchase_order_route(purchase_order_id):

    try:

        # # Try to cancel the purchase order
        cancel_purchase_order(
            purchase_order_id
        )

        # Identifier lookup is optional and cannot turn a committed cancellation into an error.
        po_number = str(purchase_order_id)
        try:
            order = get_purchase_order_by_id(purchase_order_id)
            if order:
                po_number = order["po_number"]
        except Exception:
            app.logger.exception("Unable to resolve cancelled purchase order identifier.")
        record_audit_event("PROCUREMENT", "CANCEL", "PURCHASE_ORDER", purchase_order_id,
                           f"Purchase order {po_number} (ID {purchase_order_id}) cancelled.")

        flash(
            "Purchase order cancelled successfully.",
            "success",
        )

    except ValueError as error:

        # # Business-rule error
        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_purchase_order",
            purchase_order_id=purchase_order_id,
        )
    )


# ==========================================================
# FINANCE - EXPENSE CATEGORIES
# ==========================================================

@app.route("/finance/expense-categories")
@permission_required("finance.view")
def expense_categories():

    categories = get_all_expense_categories()

    return render_template(
        "finance/expense_categories/index.html",
        categories=categories,
    )

# ==========================================================
# FINANCE - ADD EXPENSE CATEGORY
# ==========================================================

@app.route(
    "/finance/expense-categories/add",
    methods=["GET", "POST"],
)
@permission_required("finance.categories.manage")
def add_expense_category():

    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==================================================

        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()


        # ==================================================
        # VALIDATION
        # ==================================================

        if not category_code or not category_name:

            flash(
                "Category code and category name are required.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/add.html"
            )


        if len(category_code) > 30:

            flash(
                "Category code must not exceed 30 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/add.html"
            )


        if len(category_name) > 100:

            flash(
                "Category name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/add.html"
            )


        if len(description) > 255:

            flash(
                "Description must not exceed 255 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/add.html"
            )


        # ==================================================
        # DATABASE INSERT
        # ==================================================

        try:

            create_expense_category(
                category_code,
                category_name,
                description or None,
            )

        except Exception as error:

            # # MySQL duplicate-entry error
            if getattr(error, "errno", None) == 1062:

                flash(
                    "Expense category code already exists.",
                    "danger",
                )

                return render_template(
                    "finance/expense_categories/add.html"
                )

            raise


        flash(
            "Expense category created successfully.",
            "success",
        )

        return redirect(
            url_for("expense_categories")
        )


    return render_template(
        "finance/expense_categories/add.html"
    )

# ==========================================================
# FINANCE - EXPENSES
# ==========================================================

@app.route("/finance/expenses")
@permission_required("finance.view")
def expenses():

    # ======================================================
    # FILTER INPUT
    # ======================================================

    search_text = request.args.get(
        "search",
        "",
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip()

    selected_category = request.args.get(
        "category_id",
        "",
    ).strip()

    selected_year = request.args.get(
        "year",
        "",
    ).strip()


    # ======================================================
    # STATUS VALIDATION
    # ======================================================

    allowed_statuses = {
        "DRAFT",
        "APPROVED",
        "PAID",
        "CANCELLED",
    }

    if (
        selected_status
        and selected_status not in allowed_statuses
    ):
        selected_status = ""


    # ======================================================
    # CATEGORY VALIDATION
    # ======================================================

    category_id_value = None

    if selected_category:

        try:
            category_id_value = int(selected_category)

        except ValueError:
            selected_category = ""


    # ======================================================
    # YEAR VALIDATION
    # ======================================================

    year_value = None

    if selected_year:

        try:
            year_value = int(selected_year)

        except ValueError:
            selected_year = ""


    # ======================================================
    # GET EXPENSE RECORDS
    # ======================================================

    if search_text:

        expense_list = search_expenses(
            search_text
        )

    else:

        expense_list = get_filtered_expenses(
            status=selected_status or None,
            category_id=category_id_value,
            year=year_value,
            search_text=search_text or None,
        )


    categories = get_all_expense_categories()


    # ======================================================
    # SHOW PAGE
    # ======================================================

    return render_template(
        "finance/expenses/index.html",
        expenses=expense_list,
        categories=categories,
        search_text=search_text,
        selected_status=selected_status,
        selected_category=selected_category,
        selected_year=selected_year,
        current_year=date.today().year,
    )


# ==========================================================
# FINANCE - EDIT EXPENSE CATEGORY
# ==========================================================

@app.route(
    "/finance/expense-categories/<int:category_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("finance.categories.manage")
def edit_expense_category(category_id):

    # ======================================================
    # GET CATEGORY
    # ======================================================

    category = get_expense_category_by_id(category_id)

    if not category:
        flash(
            "Expense category not found.",
            "danger",
        )

        return redirect(
            url_for("expense_categories")
        )


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==================================================

        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()


        # ==================================================
        # VALIDATION
        # ==================================================

        if not category_code or not category_name:

            flash(
                "Category code and category name are required.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/edit.html",
                category=category,
            )


        if len(category_code) > 30:

            flash(
                "Category code must not exceed 30 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/edit.html",
                category=category,
            )


        if len(category_name) > 100:

            flash(
                "Category name must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/edit.html",
                category=category,
            )


        if len(description) > 255:

            flash(
                "Description must not exceed 255 characters.",
                "danger",
            )

            return render_template(
                "finance/expense_categories/edit.html",
                category=category,
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        try:

            update_expense_category(
                category_id,
                category_code,
                category_name,
                description or None,
            )

        except Exception as error:

            if getattr(error, "errno", None) == 1062:

                flash(
                    "Expense category code already exists.",
                    "danger",
                )

                return render_template(
                    "finance/expense_categories/edit.html",
                    category=category,
                )

            raise


        flash(
            "Expense category updated successfully.",
            "success",
        )

        return redirect(
            url_for("expense_categories")
        )


    return render_template(
        "finance/expense_categories/edit.html",
        category=category,
    )


# ==========================================================
# FINANCE - CHANGE EXPENSE CATEGORY STATUS
# ==========================================================

@app.route(
    "/finance/expense-categories/<int:category_id>/status",
    methods=["POST"],
)
@permission_required("finance.categories.manage")
def change_expense_category_status(category_id):

    # ======================================================
    # GET CATEGORY
    # ======================================================

    category = get_expense_category_by_id(category_id)

    if not category:
        flash(
            "Expense category not found.",
            "danger",
        )

        return redirect(
            url_for("expense_categories")
        )


    # ======================================================
    # TOGGLE STATUS
    # ======================================================

    new_status = not bool(category["is_active"])

    set_expense_category_active_status(
        category_id,
        new_status,
    )


    # ======================================================
    # ======================================================
    # SUCCESS MESSAGE
    # ======================================================

    if new_status:

        flash(
            "Expense category activated successfully.",
            "success",
        )

    else:

        flash(
            "Expense category deactivated successfully.",
            "success",
        )


    return redirect(
        url_for("expense_categories")
    )




# ==========================================================
# FINANCE - ADD EXPENSE
# ==========================================================

@app.route(
    "/finance/expenses/add",
    methods=["GET", "POST"],
)
@permission_required("finance.expenses.manage")
def add_expense():

    # ======================================================
    # FORM OPTIONS
    # ======================================================

    categories = get_active_expense_categories()
    departments = get_active_departments()
    suppliers = get_active_suppliers()

    purchase_orders = [
        purchase_order
        for purchase_order in get_all_purchase_orders()
        if purchase_order["status"] != "CANCELLED"
    ]


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==================================================

        expense_date = request.form.get(
            "expense_date",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        supplier_id = request.form.get(
            "supplier_id",
            "",
        ).strip()

        purchase_order_id = request.form.get(
            "purchase_order_id",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        amount = request.form.get(
            "amount",
            "",
        ).strip().replace(",", "")

        reference_number = request.form.get(
            "reference_number",
            "",
        ).strip()

        payment_method = request.form.get(
            "payment_method",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELD VALIDATION
        # ==================================================

        if (
            not expense_date
            or not category_id
            or not description
            or not amount
        ):

            flash(
                "Date, category, description, and amount are required.",
                "danger",
            )

            return render_template(
                "finance/expenses/add.html",
                categories=categories,
                departments=departments,
                suppliers=suppliers,
                purchase_orders=purchase_orders,
            )


        # ==================================================
        # AMOUNT VALIDATION
        # ==================================================

        try:

            amount_value = Decimal(amount)

            if amount_value <= 0:
                raise InvalidOperation

        except (InvalidOperation, ValueError):

            flash(
                "Amount must be greater than zero.",
                "danger",
            )

            return render_template(
                "finance/expenses/add.html",
                categories=categories,
                departments=departments,
                suppliers=suppliers,
                purchase_orders=purchase_orders,
            )


        # ==================================================
        # CATEGORY VALIDATION
        # ==================================================

        try:

            category_id_value = int(category_id)

        except ValueError:

            flash(
                "Invalid expense category.",
                "danger",
            )

            return redirect(
                url_for("add_expense")
            )


        category = get_expense_category_by_id(
            category_id_value
        )

        if not category or not category["is_active"]:

            flash(
                "Selected expense category is invalid or inactive.",
                "danger",
            )

            return redirect(
                url_for("add_expense")
            )


        # ==================================================
        # OPTIONAL DEPARTMENT
        # ==================================================

        department_id_value = None

        if department_id:

            try:

                department_id_value = int(
                    department_id
                )

            except ValueError:

                flash(
                    "Invalid department.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )

            department = get_department_by_id(
                department_id_value
            )

            if not department or not department["is_active"]:

                flash(
                    "Selected department is invalid or inactive.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )


        # ==================================================
        # OPTIONAL SUPPLIER
        # ==================================================

        supplier_id_value = None

        if supplier_id:

            try:

                supplier_id_value = int(
                    supplier_id
                )

            except ValueError:

                flash(
                    "Invalid supplier.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )

            supplier = get_supplier_by_id(
                supplier_id_value
            )

            if not supplier or not supplier["is_active"]:

                flash(
                    "Selected supplier is invalid or inactive.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )


        # ==================================================
        # OPTIONAL PURCHASE ORDER
        # ==================================================

        purchase_order_id_value = None

        if purchase_order_id:

            try:

                purchase_order_id_value = int(
                    purchase_order_id
                )

            except ValueError:

                flash(
                    "Invalid purchase order.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )

            purchase_order = get_purchase_order_by_id(
                purchase_order_id_value
            )

            if (
                not purchase_order
                or purchase_order["status"] == "CANCELLED"
            ):

                flash(
                    "Selected purchase order is invalid or cancelled.",
                    "danger",
                )

                return redirect(
                    url_for("add_expense")
                )


        # ==================================================
        # PAYMENT METHOD VALIDATION
        # ==================================================

        allowed_payment_methods = {
            "CASH",
            "BANK_TRANSFER",
            "CHECK",
            "CARD",
            "OTHER",
        }

        if (
            payment_method
            and payment_method not in allowed_payment_methods
        ):

            flash(
                "Invalid payment method.",
                "danger",
            )

            return redirect(
                url_for("add_expense")
            )


        # ==================================================
        # DATABASE INSERT
        # ==================================================

        expense_id, expense_number = create_expense(
            expense_date,
            category_id_value,
            department_id_value,
            supplier_id_value,
            purchase_order_id_value,
            description,
            amount_value,
            reference_number or None,
            payment_method or None,
            session["user_id"],
            notes or None,
        )


        flash(
            f"Expense {expense_number} created successfully.",
            "success",
        )

        return redirect(
            url_for("expenses")
        )


    # ======================================================
    # SHOW FORM
    # ======================================================

    return render_template(
        "finance/expenses/add.html",
        categories=categories,
        departments=departments,
        suppliers=suppliers,
        purchase_orders=purchase_orders,
        today=date.today().isoformat(),
    )


# ==========================================================
# FINANCE - VIEW EXPENSE
# ==========================================================

@app.route(
    "/finance/expenses/<int:expense_id>"
)
@permission_required("finance.view")
def view_expense(expense_id):

    # ======================================================
    # GET EXPENSE
    # ======================================================

    expense = get_expense_by_id(
        expense_id
    )

    if not expense:

        flash(
            "Expense not found.",
            "danger",
        )

        return redirect(
            url_for("expenses")
        )


    # ======================================================
    # BUDGET IMPACT PREVIEW
    #
    # Only APPROVED expenses need a payment preview.
    # DRAFT, PAID, and CANCELLED expenses do not.
    # ======================================================

    budget_check = None

    if expense["status"] == "APPROVED":

        try:

            budget_check = (
                check_expense_against_budget(
                    expense_id
                )
            )

        except ValueError:

            budget_check = None


    # ======================================================
    # SHOW EXPENSE DETAILS
    # ======================================================

    return render_template(
        "finance/expenses/view.html",
        expense=expense,
        budget_check=budget_check,
    )



# ==========================================================
# FINANCE - APPROVE EXPENSE
# ==========================================================

@app.route(
    "/finance/expenses/<int:expense_id>/approve",
    methods=["POST"],
)
@permission_required("finance.expenses.approve")
def approve_expense_route(expense_id):

    try:

        approve_expense(
            expense_id,
            session["user_id"],
        )

        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="FINANCE",
            action="APPROVE",
            entity_type="EXPENSE",
            entity_id=expense_id,
            description="Expense approved.",
            entity_lookup=get_expense_by_id,
            identifier_key="expense_number",
        )

        flash(
            "Expense approved successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_expense",
            expense_id=expense_id,
        )
    )




# ==========================================================
# FINANCE - MARK EXPENSE AS PAID
# ==========================================================

@app.route(
    "/finance/expenses/<int:expense_id>/paid",
    methods=["POST"],
)
@permission_required("finance.expenses.pay")
def mark_expense_as_paid_route(expense_id):

    try:

        # ==================================================
        # CHECK DEPARTMENT BUDGET
        # ==========================================================

        budget_check = check_expense_against_budget(
            expense_id
        )


        # ==================================================
        # DEPARTMENT HAS NO BUDGET
        # ==========================================================

        if (
            budget_check["budget_required"]
            and not budget_check["budget_found"]
        ):

            flash(
                (
                    f"Payment blocked. "
                    f"{budget_check['department_name']} "
                    f"does not have a budget for "
                    f"{budget_check['budget_year']}."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "view_expense",
                    expense_id=expense_id,
                )
            )


        # ==================================================
        # PAYMENT WOULD EXCEED BUDGET
        # ==========================================================

        if not budget_check["can_pay"]:

            flash(
                (
                    "Payment blocked. This expense would "
                    "exceed the department budget by "
                    f"₱{budget_check['over_by']:,.2f}."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "view_expense",
                    expense_id=expense_id,
                )
            )


        # ==================================================
        # BUDGET CHECK PASSED
        # ==========================================================

        mark_expense_as_paid(
            expense_id
        )

        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="FINANCE",
            action="MARK_PAID",
            entity_type="EXPENSE",
            entity_id=expense_id,
            description="Expense marked as paid.",
            entity_lookup=get_expense_by_id,
            identifier_key="expense_number",
        )

        flash(
            "Expense marked as paid successfully.",
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_expense",
            expense_id=expense_id,
        )
    )


# ==========================================================
# FINANCE - CANCEL EXPENSE
# ==========================================================

@app.route(
    "/finance/expenses/<int:expense_id>/cancel",
    methods=["POST"],
)
@permission_required("finance.expenses.manage")
def cancel_expense_route(expense_id):

    try:

        cancel_expense(
            expense_id
        )

        flash(
            "Expense cancelled successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_expense",
            expense_id=expense_id,
        )
    )



# ==========================================================
# FINANCE - EDIT EXPENSE
#
# Only DRAFT expenses can be edited.
# ==========================================================

@app.route(
    "/finance/expenses/<int:expense_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("finance.expenses.manage")
def edit_expense(expense_id):

    # ======================================================
    # GET EXPENSE
    # ======================================================

    expense = get_expense_by_id(expense_id)

    if not expense:
        flash(
            "Expense not found.",
            "danger",
        )

        return redirect(
            url_for("expenses")
        )


    # ======================================================
    # ONLY DRAFT EXPENSES CAN BE EDITED
    # ======================================================

    if expense["status"] != "DRAFT":

        flash(
            "Only draft expenses can be edited.",
            "danger",
        )

        return redirect(
            url_for(
                "view_expense",
                expense_id=expense_id,
            )
        )


    # ======================================================
    # FORM OPTIONS
    # ======================================================

    categories = get_active_expense_categories()
    departments = get_active_departments()
    suppliers = get_active_suppliers()

    purchase_orders = [
        purchase_order
        for purchase_order in get_all_purchase_orders()
        if purchase_order["status"] != "CANCELLED"
    ]


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==================================================

        expense_date = request.form.get(
            "expense_date",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        supplier_id = request.form.get(
            "supplier_id",
            "",
        ).strip()

        purchase_order_id = request.form.get(
            "purchase_order_id",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        amount = request.form.get(
            "amount",
            "",
        ).strip().replace(",", "")

        reference_number = request.form.get(
            "reference_number",
            "",
        ).strip()

        payment_method = request.form.get(
            "payment_method",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==================================================

        if (
            not expense_date
            or not category_id
            or not description
            or not amount
        ):

            flash(
                "Date, category, description, and amount are required.",
                "danger",
            )

            return render_template(
                "finance/expenses/edit.html",
                expense=expense,
                categories=categories,
                departments=departments,
                suppliers=suppliers,
                purchase_orders=purchase_orders,
            )


        # ==================================================
        # AMOUNT VALIDATION
        # ==================================================

        try:

            amount_value = Decimal(amount)

            if amount_value <= 0:
                raise InvalidOperation

        except (InvalidOperation, ValueError):

            flash(
                "Amount must be greater than zero.",
                "danger",
            )

            return render_template(
                "finance/expenses/edit.html",
                expense=expense,
                categories=categories,
                departments=departments,
                suppliers=suppliers,
                purchase_orders=purchase_orders,
            )


        # ==================================================
        # CATEGORY VALIDATION
        # ==================================================

        try:
            category_id_value = int(category_id)

        except ValueError:

            flash(
                "Invalid expense category.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_expense",
                    expense_id=expense_id,
                )
            )

        category = get_expense_category_by_id(
            category_id_value
        )

        if not category or not category["is_active"]:

            flash(
                "Selected expense category is invalid or inactive.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_expense",
                    expense_id=expense_id,
                )
            )


        # ==================================================
        # OPTIONAL DEPARTMENT
        # ==================================================

        department_id_value = None

        if department_id:

            try:
                department_id_value = int(department_id)

            except ValueError:

                flash("Invalid department.", "danger")

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )

            department = get_department_by_id(
                department_id_value
            )

            if not department or not department["is_active"]:

                flash(
                    "Selected department is invalid or inactive.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )


        # ==================================================
        # OPTIONAL SUPPLIER
        # ==================================================

        supplier_id_value = None

        if supplier_id:

            try:
                supplier_id_value = int(supplier_id)

            except ValueError:

                flash("Invalid supplier.", "danger")

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )

            supplier = get_supplier_by_id(
                supplier_id_value
            )

            if not supplier or not supplier["is_active"]:

                flash(
                    "Selected supplier is invalid or inactive.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )


        # ==================================================
        # OPTIONAL PURCHASE ORDER
        # ==================================================

        purchase_order_id_value = None

        if purchase_order_id:

            try:
                purchase_order_id_value = int(
                    purchase_order_id
                )

            except ValueError:

                flash(
                    "Invalid purchase order.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )

            purchase_order = get_purchase_order_by_id(
                purchase_order_id_value
            )

            if (
                not purchase_order
                or purchase_order["status"] == "CANCELLED"
            ):

                flash(
                    "Selected purchase order is invalid or cancelled.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_expense",
                        expense_id=expense_id,
                    )
                )


        # ==================================================
        # PAYMENT METHOD VALIDATION
        # ==================================================

        allowed_payment_methods = {
            "CASH",
            "BANK_TRANSFER",
            "CHECK",
            "CARD",
            "OTHER",
        }

        if (
            payment_method
            and payment_method not in allowed_payment_methods
        ):

            flash(
                "Invalid payment method.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_expense",
                    expense_id=expense_id,
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        try:

            update_expense(
                expense_id,
                expense_date,
                category_id_value,
                department_id_value,
                supplier_id_value,
                purchase_order_id_value,
                description,
                amount_value,
                reference_number or None,
                payment_method or None,
                notes or None,
            )

        except ValueError as error:

            flash(
                str(error),
                "danger",
            )

            return redirect(
                url_for(
                    "view_expense",
                    expense_id=expense_id,
                )
            )


        flash(
            "Expense updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_expense",
                expense_id=expense_id,
            )
        )


    # ======================================================
    # SHOW EDIT FORM
    # ======================================================

    return render_template(
        "finance/expenses/edit.html",
        expense=expense,
        categories=categories,
        departments=departments,
        suppliers=suppliers,
        purchase_orders=purchase_orders,
    )



# ==========================================================
# FINANCE - SUMMARY
# ==========================================================

@app.route("/finance")
@permission_required("finance.view")
def finance_summary():

    # ======================================================
    # SELECTED YEAR
    # ======================================================

    current_year = date.today().year

    selected_year = request.args.get(
        "year",
        str(current_year),
    ).strip()

    try:

        selected_year = int(selected_year)

    except ValueError:

        selected_year = current_year


    # ======================================================
    # SUMMARY DATA
    # ======================================================

    summary = get_finance_summary_by_year(
    selected_year
)

    monthly_paid_expenses = get_monthly_paid_expenses(
        selected_year
    )

    paid_expenses_by_category = (
        get_paid_expenses_by_category(
            selected_year
        )
    )


    # ======================================================
    # SHOW FINANCE SUMMARY
    # ======================================================

    return render_template(
        "finance/index.html",
        summary=summary,
        monthly_paid_expenses=monthly_paid_expenses,
        paid_expenses_by_category=paid_expenses_by_category,
        selected_year=selected_year,
        current_year=current_year,
    )


# ==========================================================
# FINANCE - DEPARTMENT BUDGETS
# ==========================================================

@app.route("/finance/budgets")
@permission_required("finance.view")
def department_budgets():

    # ======================================================
    # SELECTED YEAR
    # ======================================================

    current_year = date.today().year

    selected_year = request.args.get(
        "year",
        str(current_year),
    ).strip()

    try:
        selected_year = int(selected_year)

    except ValueError:
        selected_year = current_year


    # ======================================================
    # GET BUDGET RECORDS
    # ======================================================

    budget_list = get_all_department_budgets(
        year=selected_year
    )


    # ======================================================
    # GET BUDGET SUMMARY
    # ======================================================

    budget_summary = get_budget_summary(
        selected_year
    )


    # ======================================================
    # SHOW BUDGET PAGE
    # ======================================================

    return render_template(
        "finance/budgets/index.html",
        budgets=budget_list,
        budget_summary=budget_summary,
        selected_year=selected_year,
        current_year=current_year,
    )

# ==========================================================
# FINANCE - ADD DEPARTMENT BUDGET
# ==========================================================

@app.route(
    "/finance/budgets/add",
    methods=["GET", "POST"],
)
@permission_required("finance.expenses.manage")
def add_department_budget():

    # ======================================================
    # GET ACTIVE DEPARTMENTS
    # ======================================================

    departments = get_active_departments()


    # ======================================================
    # FORM SUBMISSION
    # ======================================================

    if request.method == "POST":

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        budget_year = request.form.get(
            "budget_year",
            "",
        ).strip()

        budget_amount = request.form.get(
            "budget_amount",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==================================================

        if (
            not department_id
            or not budget_year
            or not budget_amount
        ):
            flash(
                "Department, year, and budget amount are required.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )


        # ==================================================
        # DEPARTMENT VALIDATION
        # ==================================================

        try:
            department_id = int(department_id)

        except ValueError:

            flash(
                "Invalid department.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )


        # ==================================================
        # YEAR VALIDATION
        # ==================================================

        try:
            budget_year = int(budget_year)

        except ValueError:

            flash(
                "Budget year must be a valid year.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )


        # ==================================================
        # AMOUNT VALIDATION
        # ==================================================

        try:
            budget_amount = Decimal(
                budget_amount.replace(",", "")
            )

        except InvalidOperation:

            flash(
                "Budget amount must be a valid number.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )

        if budget_amount <= 0:

            flash(
                "Budget amount must be greater than zero.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )


        # ==================================================
        # DUPLICATE BUDGET CHECK
        # ==================================================

        existing_budget = (
            get_department_budget_by_department_and_year(
                department_id,
                budget_year,
            )
        )

        if existing_budget:

            flash(
                "This department already has a budget "
                "for the selected year.",
                "danger",
            )

            return render_template(
                "finance/budgets/add.html",
                departments=departments,
            )


        # ==================================================
        # DATABASE INSERT
        # ==================================================

        create_department_budget(
            department_id=department_id,
            budget_year=budget_year,
            budget_amount=budget_amount,
            notes=notes or None,
            created_by=session["user_id"],
        )


        # ==================================================
        # SUCCESS
        # ==================================================

        flash(
            "Department budget created successfully.",
            "success",
        )

        return redirect(
            url_for("department_budgets")
        )


    # ======================================================
    # SHOW ADD FORM
    # ======================================================

    return render_template(
        "finance/budgets/add.html",
        departments=departments,
    )


# ==========================================================
# FINANCE - EDIT DEPARTMENT BUDGET
# ==========================================================

@app.route(
    "/finance/budgets/<int:budget_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("finance.expenses.manage")
def edit_department_budget(budget_id):

    # ======================================================
    # GET EXISTING BUDGET
    # ======================================================

    budget = get_department_budget_by_id(
        budget_id
    )

    if not budget:

        flash(
            "Department budget was not found.",
            "danger",
        )

        return redirect(
            url_for("department_budgets")
        )


    # ======================================================
    # GET ACTIVE DEPARTMENTS
    # ======================================================

    departments = get_active_departments()


    # ======================================================
    # FORM SUBMISSION
    # ======================================================

    if request.method == "POST":

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        budget_year = request.form.get(
            "budget_year",
            "",
        ).strip()

        budget_amount = request.form.get(
            "budget_amount",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==================================================

        if (
            not department_id
            or not budget_year
            or not budget_amount
        ):

            flash(
                "Department, year, and budget amount are required.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )


        # ==================================================
        # DEPARTMENT VALIDATION
        # ==================================================

        try:
            department_id = int(department_id)

        except ValueError:

            flash(
                "Invalid department.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )


        # ==================================================
        # YEAR VALIDATION
        # ==================================================

        try:
            budget_year = int(budget_year)

        except ValueError:

            flash(
                "Budget year must be a valid year.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )


        # ==================================================
        # AMOUNT VALIDATION
        # ==================================================

        try:

            budget_amount = Decimal(
                budget_amount.replace(",", "")
            )

        except InvalidOperation:

            flash(
                "Budget amount must be a valid number.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )

        if budget_amount <= 0:

            flash(
                "Budget amount must be greater than zero.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )


        # ==================================================
        # DUPLICATE DEPARTMENT / YEAR CHECK
        # ==================================================

        duplicate_budget = (
            get_department_budget_by_department_and_year(
                department_id,
                budget_year,
            )
        )

        if (
            duplicate_budget
            and duplicate_budget["budget_id"]
            != budget_id
        ):

            flash(
                "This department already has a budget "
                "for the selected year.",
                "danger",
            )

            return render_template(
                "finance/budgets/edit.html",
                budget=budget,
                departments=departments,
            )


        # ==================================================
        # DATABASE UPDATE
        # ==================================================

        try:

            update_department_budget(
                budget_id=budget_id,
                department_id=department_id,
                budget_year=budget_year,
                budget_amount=budget_amount,
                notes=notes or None,
            )

        except ValueError as error:

            flash(
                str(error),
                "danger",
            )

            return redirect(
                url_for("department_budgets")
            )


        # ==================================================
        # SUCCESS
        # ==================================================

        flash(
            "Department budget updated successfully.",
            "success",
        )

        return redirect(
            url_for("department_budgets")
        )


    # ======================================================
    # SHOW EDIT FORM
    # ======================================================

    return render_template(
        "finance/budgets/edit.html",
        budget=budget,
        departments=departments,
    )


# ==========================================================
# FINANCE - VIEW DEPARTMENT BUDGET
# ==========================================================

@app.route(
    "/finance/budgets/<int:budget_id>"
)
@permission_required("finance.view")
def view_department_budget(budget_id):

    # ======================================================
    # GET BUDGET DETAILS
    # ======================================================

    budget = get_department_budget_details_by_id(
        budget_id
    )

    if not budget:

        flash(
            "Department budget was not found.",
            "danger",
        )

        return redirect(
            url_for("department_budgets")
        )


    # ======================================================
    # GET PAID EXPENSES
    # ======================================================

    paid_expenses = get_paid_expenses_for_budget(
        budget_id
    )


    # ======================================================
    # CALCULATE USAGE
    # ======================================================

    budget_amount = float(
        budget["budget_amount"]
    )

    spent_amount = float(
        budget["spent_amount"]
    )

    if budget_amount > 0:

        usage_percentage = (
            spent_amount
            / budget_amount
            * 100
        )

    else:

        usage_percentage = 0


    # ======================================================
    # SHOW BUDGET DETAILS PAGE
    # ======================================================

    return render_template(
        "finance/budgets/view.html",
        budget=budget,
        paid_expenses=paid_expenses,
        usage_percentage=usage_percentage,
    )

# ==========================================================
# FINANCE - REPORTS
# ==========================================================

@app.route("/finance/reports")
@permission_required("finance.view")
def finance_reports():

    # ======================================================
    # SELECTED YEAR
    # ======================================================

    current_year = date.today().year

    selected_year = request.args.get(
        "year",
        str(current_year),
    ).strip()

    try:
        selected_year = int(selected_year)

    except ValueError:
        selected_year = current_year


    # ======================================================
    # REPORT SUMMARY
    # ======================================================

    summary = get_finance_summary_by_year(
        selected_year
    )


    # ======================================================
    # MONTHLY PAID EXPENSES
    # ======================================================

    monthly_expenses = get_monthly_paid_expenses(
        selected_year
    )


    # ======================================================
    # PAID EXPENSES BY CATEGORY
    # ======================================================

    category_expenses = get_paid_expenses_by_category(
        selected_year
    )


    # ======================================================
    # ALL EXPENSE RECORDS FOR YEAR
    # ======================================================

    expense_records = get_filtered_expenses(
        year=selected_year
    )


    # ======================================================
    # SHOW REPORT PAGE
    # ======================================================

    return render_template(
        "finance/reports/index.html",
        summary=summary,
        monthly_expenses=monthly_expenses,
        category_expenses=category_expenses,
        expense_records=expense_records,
        selected_year=selected_year,
        current_year=current_year,
    )


# ==========================================================
# FINANCE - EXPORT REPORT TO EXCEL
# ==========================================================

@app.route("/finance/reports/export")
@permission_required("finance.view")
def export_finance_report():

    # ======================================================
    # SELECTED YEAR
    # ======================================================

    current_year = date.today().year

    selected_year = request.args.get(
        "year",
        str(current_year),
    ).strip()

    try:
        selected_year = int(selected_year)

    except ValueError:
        selected_year = current_year


    # ======================================================
    # GET REPORT DATA
    # ======================================================

    summary = get_finance_summary_by_year(
        selected_year
    )

    monthly_expenses = get_monthly_paid_expenses(
        selected_year
    )

    category_expenses = get_paid_expenses_by_category(
        selected_year
    )

    expense_records = get_filtered_expenses(
        year=selected_year
    )


    # ======================================================
    # GENERATE EXCEL FILE
    # ======================================================

    excel_file = generate_finance_report_excel(
        selected_year,
        summary,
        monthly_expenses,
        category_expenses,
        expense_records,
    )


    # ======================================================
    # DOWNLOAD FILE
    # ======================================================

    return send_file(
        excel_file,
        as_attachment=True,
        download_name=(
            f"Finance_Report_{selected_year}.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )

# ==========================================================
# PAYROLL - EMPLOYEE COMPENSATION
# ==========================================================

@app.route("/payroll/compensation")
@permission_required("payroll.view")
def payroll_compensation():

    compensation_records = (
        get_all_employee_compensation()
    )

    return render_template(
        "payroll/compensation/index.html",
        compensation_records=compensation_records,
    )

# ==========================================================
# PAYROLL - ADD EMPLOYEE COMPENSATION
# ==========================================================

@app.route(
    "/payroll/compensation/add",
    methods=["GET", "POST"],
)
@permission_required(
    "payroll.compensation.manage"
)
def add_payroll_compensation():

    employees = (
        get_employees_without_compensation()
    )


    allowed_pay_types = {
        "MONTHLY",
        "DAILY",
        "HOURLY",
    }


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()

        pay_type = request.form.get(
            "pay_type",
            "",
        ).strip().upper()

        basic_rate = request.form.get(
            "basic_rate",
            "",
        ).strip()

        effective_date = request.form.get(
            "effective_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not employee_id
            or not pay_type
            or not basic_rate
            or not effective_date
        ):

            flash(
                (
                    "Employee, pay type, basic rate, "
                    "and effective date are required."
                ),
                "danger",
            )

            return render_template(
                "payroll/compensation/add.html",
                employees=employees,
                today=date.today().isoformat(),
            )


        # ==================================================
        # EMPLOYEE VALIDATION
        # ==========================================================

        try:

            employee_id_value = int(
                employee_id
            )

        except ValueError:

            flash(
                "Invalid employee.",
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        employee = get_employee_by_id(
            employee_id_value
        )


        if not employee:

            flash(
                "Employee not found.",
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        existing_compensation = (
            get_employee_compensation_by_employee_id(
                employee_id_value
            )
        )


        if existing_compensation:

            flash(
                (
                    "This employee already has "
                    "compensation configured."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "payroll_compensation"
                )
            )


        # ==================================================
        # PAY TYPE VALIDATION
        # ==========================================================

        if (
            pay_type
            not in allowed_pay_types
        ):

            flash(
                "Invalid pay type.",
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        # ==================================================
        # RATE VALIDATION
        # ==========================================================

        try:

            basic_rate_value = Decimal(
                basic_rate
            )


            if basic_rate_value <= 0:

                raise ValueError


            if (
                basic_rate_value
                > Decimal("9999999999.99")
            ):

                raise ValueError


        except (
            InvalidOperation,
            ValueError,
        ):

            flash(
                (
                    "Basic rate must be a valid "
                    "positive amount."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        # ==================================================
        # EFFECTIVE DATE
        # ==========================================================

        try:

            effective_date_value = (
                date.fromisoformat(
                    effective_date
                )
            )

        except ValueError:

            flash(
                "Invalid effective date.",
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        # ==================================================
        # NOTES
        # ==========================================================

        if len(notes) > 255:

            flash(
                (
                    "Notes must not exceed "
                    "255 characters."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "add_payroll_compensation"
                )
            )


        # ==================================================
        # CREATE
        # ==========================================================

        try:

            create_employee_compensation(
                employee_id=employee_id_value,
                pay_type=pay_type,
                basic_rate=basic_rate_value,
                effective_date=effective_date_value,
                notes=notes or None,
                created_by=session["user_id"],
            )


        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "This employee already has "
                        "compensation configured."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "payroll_compensation"
                    )
                )

            raise


        flash(
            (
                "Employee compensation "
                "created successfully."
            ),
            "success",
        )


        return redirect(
            url_for(
                "payroll_compensation"
            )
        )


    return render_template(
        "payroll/compensation/add.html",
        employees=employees,
        today=date.today().isoformat(),
    )

# ==========================================================
# PAYROLL - EDIT EMPLOYEE COMPENSATION
# ==========================================================

@app.route(
    "/payroll/compensation/<int:compensation_id>/edit",
    methods=["GET", "POST"],
)
@permission_required(
    "payroll.compensation.manage"
)
def edit_payroll_compensation(
    compensation_id,
):

    compensation = (
        get_employee_compensation_by_id(
            compensation_id
        )
    )


    if not compensation:

        flash(
            "Compensation record not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_compensation"
            )
        )


    allowed_pay_types = {
        "MONTHLY",
        "DAILY",
        "HOURLY",
    }


    if request.method == "POST":

        pay_type = request.form.get(
            "pay_type",
            "",
        ).strip().upper()

        basic_rate = request.form.get(
            "basic_rate",
            "",
        ).strip()

        effective_date = request.form.get(
            "effective_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # PAY TYPE
        # ==========================================================

        if (
            pay_type
            not in allowed_pay_types
        ):

            flash(
                "Invalid pay type.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_compensation",
                    compensation_id=compensation_id,
                )
            )


        # ==================================================
        # RATE
        # ==========================================================

        try:

            basic_rate_value = Decimal(
                basic_rate
            )


            if basic_rate_value <= 0:

                raise ValueError


            if (
                basic_rate_value
                > Decimal("9999999999.99")
            ):

                raise ValueError


        except (
            InvalidOperation,
            ValueError,
        ):

            flash(
                (
                    "Basic rate must be a valid "
                    "positive amount."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_compensation",
                    compensation_id=compensation_id,
                )
            )


        # ==================================================
        # EFFECTIVE DATE
        # ==========================================================

        try:

            effective_date_value = (
                date.fromisoformat(
                    effective_date
                )
            )

        except ValueError:

            flash(
                "Invalid effective date.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_compensation",
                    compensation_id=compensation_id,
                )
            )


        # ==================================================
        # NOTES
        # ==========================================================

        if len(notes) > 255:

            flash(
                (
                    "Notes must not exceed "
                    "255 characters."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_compensation",
                    compensation_id=compensation_id,
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        update_employee_compensation(
            compensation_id=compensation_id,
            pay_type=pay_type,
            basic_rate=basic_rate_value,
            effective_date=effective_date_value,
            notes=notes or None,
            updated_by=session["user_id"],
        )


        flash(
            (
                "Employee compensation "
                "updated successfully."
            ),
            "success",
        )


        return redirect(
            url_for(
                "payroll_compensation"
            )
        )


    return render_template(
        "payroll/compensation/edit.html",
        compensation=compensation,
    )

# ==========================================================
# PAYROLL - PERIODS
# ==========================================================

@app.route("/payroll/periods")
@permission_required("payroll.view")
def payroll_periods():

    periods = get_all_payroll_periods()

    return render_template(
        "payroll/periods/index.html",
        periods=periods,
    )

# ==========================================================
# PAYROLL - VIEW PERIOD
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>"
)
@permission_required("payroll.view")
def view_payroll_period(
    payroll_period_id,
):

    period = get_payroll_period_by_id(
        payroll_period_id
    )


    if not period:

        flash(
            "Payroll period not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    entries = (
        get_payroll_entries_by_period(
            payroll_period_id
        )
    )


    return render_template(
        "payroll/periods/view.html",
        period=period,
        entries=entries,
    )

# ==========================================================
# PAYROLL - SUBMIT FOR APPROVAL
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/submit",
    methods=["POST"],
)
@permission_required("payroll.process")
def submit_payroll_for_approval_route(
    payroll_period_id,
):

    try:

        result = submit_payroll_for_approval(
            payroll_period_id=payroll_period_id,
            submitted_by=session["user_id"],
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PAYROLL",
            action="SUBMIT",
            entity_type="PAYROLL_PERIOD",
            entity_id=payroll_period_id,
            description="Payroll period submitted for approval.",
            entity_lookup=get_payroll_period_by_id,
            identifier_key="period_number",
        )

        flash(
            (
                "Payroll submitted for approval successfully. "
                f"{result['total_entries']} payroll "
                "entry/entries are ready for review."
            ),
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )



# ==========================================================
# PAYROLL - RETURN TO DRAFT
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/return-to-draft",
    methods=["POST"],
)
@permission_required("payroll.process")
def return_payroll_to_draft_route(
    payroll_period_id,
):

    try:

        return_payroll_to_draft(
            payroll_period_id=payroll_period_id,
            updated_by=session["user_id"],
        )
        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PAYROLL",
            action="RETURN_TO_DRAFT",
            entity_type="PAYROLL_PERIOD",
            entity_id=payroll_period_id,
            description="Payroll period returned to draft.",
            entity_lookup=get_payroll_period_by_id,
            identifier_key="period_number",
        )

        flash(
            (
                "Payroll returned to Draft. "
                "Adjustments and recalculation are unlocked again."
            ),
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )

# ==========================================================
# PAYROLL - APPROVE
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/approve",
    methods=["POST"],
)
@permission_required("payroll.approve")
def approve_payroll_period_route(
    payroll_period_id,
):

    try:

        result = approve_payroll_period(
            payroll_period_id=payroll_period_id,
            approved_by=session["user_id"],
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PAYROLL",
            action="APPROVE",
            entity_type="PAYROLL_PERIOD",
            entity_id=payroll_period_id,
            description="Payroll period approved.",
            entity_lookup=get_payroll_period_by_id,
            identifier_key="period_number",
        )

        flash(
            (
                "Payroll approved successfully. "
                f"{result['total_entries']} payroll "
                "entry/entries are now finalized."
            ),
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )

# ==========================================================
# PAYROLL - GENERATE ENTRIES
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/generate",
    methods=["POST"],
)
@permission_required("payroll.process")
def generate_payroll_entries_route(
    payroll_period_id,
):

    period = get_payroll_period_by_id(
        payroll_period_id
    )


    if not period:

        flash(
            "Payroll period not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    if period["status"] != "DRAFT":

        flash(
            (
                "Payroll entries can only be generated "
                "for a Draft payroll period."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_period",
                payroll_period_id=payroll_period_id,
            )
        )


    try:

        result = generate_payroll_entries(
            payroll_period_id=payroll_period_id,
            generated_by=session["user_id"],
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_period",
                payroll_period_id=payroll_period_id,
            )
        )


    # ======================================================
    # RESULT MESSAGE
    # ==========================================================

    if result["inserted_count"] > 0:

        flash(
            (
                f"{result['inserted_count']} payroll "
                "entr"
                f"{'y' if result['inserted_count'] == 1 else 'ies'} "
                "generated successfully."
            ),
            "success",
        )


    if (
        result["inserted_count"] == 0
        and result["existing_count"] > 0
    ):

        flash(
            (
                "All eligible employees already have "
                "payroll entries for this period."
            ),
            "info",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )


# ==========================================================
# IT MANAGEMENT - IT ASSETS
# ==========================================================

@app.route("/it/assets")
@permission_required("it_assets.view")
def it_assets():

    # ======================================================
    # FILTER INPUT
    # ======================================================

    search_text = request.args.get(
        "search",
        "",
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip().upper()

    selected_category = request.args.get(
        "category_id",
        "",
    ).strip()

    selected_department = request.args.get(
        "department_id",
        "",
    ).strip()


    # ======================================================
    # STATUS VALIDATION
    # ======================================================

    allowed_statuses = {
        "AVAILABLE",
        "ASSIGNED",
        "MAINTENANCE",
        "RETIRED",
        "LOST",
    }

    if (
        selected_status
        and selected_status not in allowed_statuses
    ):
        selected_status = ""


    # ======================================================
    # FILTER ID VALIDATION
    # ======================================================

    try:

        category_id_value = (
            int(selected_category)
            if selected_category
            else None
        )

        department_id_value = (
            int(selected_department)
            if selected_department
            else None
        )

    except ValueError:

        category_id_value = None
        department_id_value = None

        selected_category = ""
        selected_department = ""


    # ======================================================
    # GET ASSETS
    # ======================================================

    asset_list = get_filtered_it_assets(
        search_text=search_text or None,
        status=selected_status or None,
        category_id=category_id_value,
        department_id=department_id_value,
    )


    # ======================================================
    # SUMMARY
    # ======================================================

    summary = get_it_asset_summary()


    # ======================================================
    # FILTER OPTIONS
    # ======================================================

    categories = get_active_it_asset_categories()

    departments = get_active_departments()


    # ======================================================
    # SHOW PAGE
    # ======================================================

    return render_template(
        "it_assets/index.html",
        assets=asset_list,
        summary=summary,
        categories=categories,
        departments=departments,
        search_text=search_text,
        selected_status=selected_status,
        selected_category=selected_category,
        selected_department=selected_department,
    )

# ==========================================================
# PAYROLL - VIEW ENTRY
# ==========================================================

@app.route(
    "/payroll/entries/<int:payroll_entry_id>"
)
@permission_required("payroll.view")
def view_payroll_entry(
    payroll_entry_id,
):

    entry = get_payroll_entry_by_id(
        payroll_entry_id
    )


    if not entry:

        flash(
            "Payroll entry not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    adjustments = (
        get_payroll_adjustments(
            payroll_entry_id
        )
    )


    adjustment_totals = (
        get_payroll_adjustment_totals(
            payroll_entry_id
        )
    )


    return render_template(
        "payroll/entries/view.html",
        entry=entry,
        adjustments=adjustments,
        adjustment_totals=adjustment_totals,
    )

# ==========================================================
# PAYROLL - ADD ADJUSTMENT
# ==========================================================

@app.route(
    "/payroll/entries/<int:payroll_entry_id>/adjustments/add",
    methods=["POST"],
)
@permission_required("payroll.process")
def add_payroll_adjustment_route(
    payroll_entry_id,
):

    entry = get_payroll_entry_by_id(
        payroll_entry_id
    )


    if not entry:

        flash(
            "Payroll entry not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    adjustment_type = request.form.get(
        "adjustment_type",
        "",
    ).strip().upper()

    adjustment_name = request.form.get(
        "adjustment_name",
        "",
    ).strip()

    amount = request.form.get(
        "amount",
        "",
    ).strip()

    notes = request.form.get(
        "notes",
        "",
    ).strip()


    # ======================================================
    # TYPE
    # ==========================================================

    if adjustment_type not in {
        "EARNING",
        "DEDUCTION",
    }:

        flash(
            "Invalid payroll adjustment type.",
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    # ======================================================
    # NAME
    # ==========================================================

    if not adjustment_name:

        flash(
            "Adjustment name is required.",
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    if len(adjustment_name) > 100:

        flash(
            (
                "Adjustment name must not "
                "exceed 100 characters."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    # ======================================================
    # AMOUNT
    # ==========================================================

    try:

        amount_value = Decimal(
            amount
        )


        if amount_value <= 0:

            raise ValueError


        if (
            amount_value
            > Decimal("9999999999.99")
        ):

            raise ValueError


    except (
        InvalidOperation,
        ValueError,
    ):

        flash(
            (
                "Amount must be a valid "
                "positive value."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    # ======================================================
    # NOTES
    # ==========================================================

    if len(notes) > 255:

        flash(
            (
                "Notes must not exceed "
                "255 characters."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    # ======================================================
    # DATABASE
    # ==========================================================

    try:

        add_payroll_adjustment(
            payroll_entry_id=payroll_entry_id,
            adjustment_type=adjustment_type,
            adjustment_name=adjustment_name,
            amount=amount_value,
            notes=notes or None,
            created_by=session["user_id"],
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    flash(
        "Payroll adjustment added successfully.",
        "success",
    )


    return redirect(
        url_for(
            "view_payroll_entry",
            payroll_entry_id=payroll_entry_id,
        )
    )

# ==========================================================
# PAYROLL - DELETE ADJUSTMENT
# ==========================================================

@app.route(
    "/payroll/entries/<int:payroll_entry_id>/adjustments/<int:adjustment_id>/delete",
    methods=["POST"],
)
@permission_required("payroll.process")
def delete_payroll_adjustment_route(
    payroll_entry_id,
    adjustment_id,
):

    try:

        delete_payroll_adjustment(
            payroll_entry_id=payroll_entry_id,
            adjustment_id=adjustment_id,
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    flash(
        "Payroll adjustment removed successfully.",
        "success",
    )


    return redirect(
        url_for(
            "view_payroll_entry",
            payroll_entry_id=payroll_entry_id,
        )
    )

# ==========================================================
# PAYROLL - CREATE PERIOD
# ==========================================================

@app.route(
    "/payroll/periods/add",
    methods=["GET", "POST"],
)
@permission_required("payroll.process")
def add_payroll_period():

    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        period_name = request.form.get(
            "period_name",
            "",
        ).strip()

        start_date = request.form.get(
            "start_date",
            "",
        ).strip()

        end_date = request.form.get(
            "end_date",
            "",
        ).strip()

        pay_date = request.form.get(
            "pay_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not period_name
            or not start_date
            or not end_date
            or not pay_date
        ):

            flash(
                (
                    "Period name, start date, "
                    "end date, and pay date "
                    "are required."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        # ==================================================
        # TEXT VALIDATION
        # ==========================================================

        if len(period_name) > 100:

            flash(
                (
                    "Period name must not exceed "
                    "100 characters."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        if len(notes) > 255:

            flash(
                (
                    "Notes must not exceed "
                    "255 characters."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        # ==================================================
        # DATE VALIDATION
        # ==========================================================

        try:

            start_date_value = (
                date.fromisoformat(
                    start_date
                )
            )

            end_date_value = (
                date.fromisoformat(
                    end_date
                )
            )

            pay_date_value = (
                date.fromisoformat(
                    pay_date
                )
            )


        except ValueError:

            flash(
                "Invalid payroll period date.",
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        # ==================================================
        # DATE ORDER
        # ==========================================================

        if (
            end_date_value
            < start_date_value
        ):

            flash(
                (
                    "End date cannot be earlier "
                    "than start date."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        if (
            pay_date_value
            < end_date_value
        ):

            flash(
                (
                    "Pay date cannot be earlier "
                    "than the payroll period end date."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        # ==================================================
        # OVERLAP PROTECTION
        # ==========================================================

        overlapping_period = (
            has_overlapping_payroll_period(
                start_date=start_date_value,
                end_date=end_date_value,
            )
        )


        if overlapping_period:

            flash(
                (
                    "This payroll period overlaps "
                    f"{overlapping_period['period_number']} "
                    f"({overlapping_period['start_date']} "
                    f"to "
                    f"{overlapping_period['end_date']})."
                ),
                "danger",
            )

            return render_template(
                "payroll/periods/add.html"
            )


        # ==================================================
        # CREATE PERIOD
        # ==========================================================

        try:

            create_payroll_period(
                period_name=period_name,
                start_date=start_date_value,
                end_date=end_date_value,
                pay_date=pay_date_value,
                notes=notes or None,
                created_by=session["user_id"],
            )


        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "A payroll period with "
                        "that name already exists."
                    ),
                    "danger",
                )

                return render_template(
                    "payroll/periods/add.html"
                )

            raise


        flash(
            "Payroll period created successfully.",
            "success",
        )


        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    return render_template(
        "payroll/periods/add.html"
    )

# ==========================================================
# PAYROLL - EDIT PERIOD
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("payroll.process")
def edit_payroll_period(
    payroll_period_id,
):

    period = get_payroll_period_by_id(
        payroll_period_id
    )


    if not period:

        flash(
            "Payroll period not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    # ======================================================
    # ONLY DRAFT PERIODS MAY BE EDITED
    # ==========================================================

    if period["status"] != "DRAFT":

        flash(
            (
                "Only draft payroll periods "
                "can be edited."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    if request.method == "POST":

        period_name = request.form.get(
            "period_name",
            "",
        ).strip()

        start_date = request.form.get(
            "start_date",
            "",
        ).strip()

        end_date = request.form.get(
            "end_date",
            "",
        ).strip()

        pay_date = request.form.get(
            "pay_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED
        # ==========================================================

        if (
            not period_name
            or not start_date
            or not end_date
            or not pay_date
        ):

            flash(
                "All payroll period fields are required.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        # ==================================================
        # LENGTH VALIDATION
        # ==========================================================

        if len(period_name) > 100:

            flash(
                (
                    "Period name must not exceed "
                    "100 characters."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        if len(notes) > 255:

            flash(
                (
                    "Notes must not exceed "
                    "255 characters."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        # ==================================================
        # DATE VALIDATION
        # ==========================================================

        try:

            start_date_value = (
                date.fromisoformat(
                    start_date
                )
            )

            end_date_value = (
                date.fromisoformat(
                    end_date
                )
            )

            pay_date_value = (
                date.fromisoformat(
                    pay_date
                )
            )


        except ValueError:

            flash(
                "Invalid payroll period date.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        if (
            end_date_value
            < start_date_value
        ):

            flash(
                (
                    "End date cannot be earlier "
                    "than start date."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        if (
            pay_date_value
            < end_date_value
        ):

            flash(
                (
                    "Pay date cannot be earlier "
                    "than the payroll period end date."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        # ==================================================
        # OVERLAP CHECK
        # ==========================================================

        overlapping_period = (
            has_overlapping_payroll_period(
                start_date=start_date_value,
                end_date=end_date_value,
                exclude_payroll_period_id=payroll_period_id,
            )
        )


        if overlapping_period:

            flash(
                (
                    "This payroll period overlaps "
                    f"{overlapping_period['period_number']} "
                    f"({overlapping_period['start_date']} "
                    f"to "
                    f"{overlapping_period['end_date']})."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_payroll_period",
                    payroll_period_id=payroll_period_id,
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        try:

            updated = (
                update_payroll_period(
                    payroll_period_id=payroll_period_id,
                    period_name=period_name,
                    start_date=start_date_value,
                    end_date=end_date_value,
                    pay_date=pay_date_value,
                    notes=notes or None,
                    updated_by=session["user_id"],
                )
            )


        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "A payroll period with "
                        "that name already exists."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_payroll_period",
                        payroll_period_id=payroll_period_id,
                    )
                )

            raise


        if not updated:

            flash(
                (
                    "Payroll period could not be updated. "
                    "It may no longer be in Draft status."
                ),
                "danger",
            )

        else:

            flash(
                "Payroll period updated successfully.",
                "success",
            )


        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    return render_template(
        "payroll/periods/edit.html",
        period=period,
    )

# ==========================================================
# PAYROLL - CANCEL PERIOD
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/cancel",
    methods=["POST"],
)
@permission_required("payroll.process")
def cancel_payroll_period_route(
    payroll_period_id,
):

    period = get_payroll_period_by_id(
        payroll_period_id
    )


    if not period:

        flash(
            "Payroll period not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    if period["status"] != "DRAFT":

        flash(
            (
                "Only draft payroll periods "
                "can be cancelled."
            ),
            "danger",
        )


        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    cancelled = cancel_payroll_period(
        payroll_period_id=payroll_period_id,
        updated_by=session["user_id"],
    )


    if cancelled:

        flash(
            "Payroll period cancelled successfully.",
            "success",
        )

    else:

        flash(
            "Payroll period could not be cancelled.",
            "danger",
        )


    return redirect(
        url_for(
            "payroll_periods"
        )
    )




# ==========================================================
# IT MANAGEMENT - ADD ASSET
# ==========================================================

@app.route(
    "/it/assets/add",
    methods=["GET", "POST"],
)
@permission_required("it_assets.manage")
def add_it_asset():

    # ======================================================
    # FORM OPTIONS
    # ======================================================

    categories = get_active_it_asset_categories()
    departments = get_active_departments()
    employees = get_all_employees()

    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        asset_tag = request.form.get(
            "asset_tag",
            "",
        ).strip().upper()

        asset_name = request.form.get(
            "asset_name",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        brand = request.form.get(
            "brand",
            "",
        ).strip()

        model = request.form.get(
            "model",
            "",
        ).strip()

        serial_number = request.form.get(
            "serial_number",
            "",
        ).strip()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        assigned_employee_id = request.form.get(
            "assigned_employee_id",
            "",
        ).strip()

        purchase_date = request.form.get(
            "purchase_date",
            "",
        ).strip()

        purchase_cost = request.form.get(
            "purchase_cost",
            "",
        ).strip()

        warranty_expiry = request.form.get(
            "warranty_expiry",
            "",
        ).strip()

        condition_status = request.form.get(
            "condition_status",
            "GOOD",
        ).strip().upper()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not asset_tag
            or not asset_name
            or not category_id
        ):

            flash(
                "Asset tag, asset name, and category are required.",
                "danger",
            )

            return render_template(
                "it_assets/add.html",
                categories=categories,
                departments=departments,
                employees=employees,
            )


        # ==================================================
        # ID VALIDATION
        # ==========================================================

        try:
            category_id_value = int(category_id)

            department_id_value = (
                int(department_id)
                if department_id
                else None
            )

            assigned_employee_id_value = (
                int(assigned_employee_id)
                if assigned_employee_id
                else None
            )

        except ValueError:

            flash(
                "Invalid category, department, or employee.",
                "danger",
            )

            return redirect(
                url_for("add_it_asset")
            )


        # ==================================================
        # PURCHASE COST VALIDATION
        # ==========================================================

        purchase_cost_value = None

        if purchase_cost:

            try:

                purchase_cost_value = Decimal(
                    purchase_cost.replace(",", "")
                )

                if purchase_cost_value < 0:
                    raise ValueError

            except (
                InvalidOperation,
                ValueError,
            ):

                flash(
                    "Purchase cost must be zero or greater.",
                    "danger",
                )

                return redirect(
                    url_for("add_it_asset")
                )


        # ==================================================
        # CONDITION VALIDATION
        # ==========================================================

        allowed_conditions = {
            "NEW",
            "GOOD",
            "FAIR",
            "POOR",
            "DAMAGED",
        }

        if condition_status not in allowed_conditions:

            flash(
                "Invalid asset condition.",
                "danger",
            )

            return redirect(
                url_for("add_it_asset")
            )


        # ==================================================
        # ASSET STATUS
        #
        # If assigned to an employee, mark it ASSIGNED.
        # Otherwise it starts AVAILABLE.
        # ==========================================================

        if assigned_employee_id_value:

            asset_status = "ASSIGNED"

        else:

            asset_status = "AVAILABLE"


        # ==================================================
        # DATABASE INSERT
        # ==========================================================

        try:

            asset_id = create_it_asset(
                asset_tag=asset_tag,
                asset_name=asset_name,
                category_id=category_id_value,
                brand=brand or None,
                model=model or None,
                serial_number=serial_number or None,
                department_id=department_id_value,
                assigned_employee_id=assigned_employee_id_value,
                purchase_date=purchase_date or None,
                purchase_cost=purchase_cost_value,
                warranty_expiry=warranty_expiry or None,
                status=asset_status,
                condition_status=condition_status,
                notes=notes or None,
                created_by=session["user_id"],
            )

        except Exception as error:

            if getattr(error, "errno", None) == 1062:

                flash(
                    "Asset tag or serial number already exists.",
                    "danger",
                )

                return redirect(
                    url_for("add_it_asset")
                )

            raise


        # ==================================================
        # SUCCESS
        # ==========================================================

        flash(
            f"IT asset {asset_tag} created successfully.",
            "success",
        )

        return redirect(
            url_for("it_assets")
        )


    # ======================================================
    # SHOW FORM
    # ======================================================

    return render_template(
        "it_assets/add.html",
        categories=categories,
        departments=departments,
        employees=employees,
    )

# ==========================================================
# IT MANAGEMENT - VIEW ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>"
)
@permission_required("it_assets.view")
def view_it_asset(asset_id):

    

    asset = get_it_asset_by_id(
        asset_id
    )

    maintenance_history = (
    get_it_asset_maintenance_history(
        asset_id
    )
)

    assignment_history = (
    get_it_asset_assignment_history(
        asset_id
    )
)

    if not asset:

        flash(
            "IT asset not found.",
            "danger",
        )

        return redirect(
            url_for("it_assets")
        )

    employees = get_all_employees()

    return render_template(
    "it_assets/view.html",
    asset=asset,
    employees=employees,
    maintenance_history=maintenance_history,
    assignment_history=assignment_history,
)



# ==========================================================
# IT MANAGEMENT - EDIT ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("it_assets.manage")
def edit_it_asset(asset_id):

    asset = get_it_asset_by_id(
        asset_id
    )

    if not asset:

        flash(
            "IT asset not found.",
            "danger",
        )

        return redirect(
            url_for("it_assets")
        )

    categories = get_active_it_asset_categories()
    departments = get_active_departments()

    if request.method == "POST":

        asset_tag = request.form.get(
            "asset_tag",
            "",
        ).strip().upper()

        asset_name = request.form.get(
            "asset_name",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        brand = request.form.get(
            "brand",
            "",
        ).strip()

        model = request.form.get(
            "model",
            "",
        ).strip()

        serial_number = request.form.get(
            "serial_number",
            "",
        ).strip()

        department_id = request.form.get(
            "department_id",
            "",
        ).strip()

        purchase_date = request.form.get(
            "purchase_date",
            "",
        ).strip()

        purchase_cost = request.form.get(
            "purchase_cost",
            "",
        ).strip()

        warranty_expiry = request.form.get(
            "warranty_expiry",
            "",
        ).strip()

        condition_status = request.form.get(
            "condition_status",
            "GOOD",
        ).strip().upper()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not asset_tag
            or not asset_name
            or not category_id
        ):

            flash(
                "Asset tag, asset name, and category are required.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_it_asset",
                    asset_id=asset_id,
                )
            )


        # ==================================================
        # ID VALIDATION
        # ==========================================================

        try:

            category_id_value = int(
                category_id
            )

            department_id_value = (
                int(department_id)
                if department_id
                else None
            )

        except ValueError:

            flash(
                "Invalid category or department.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_it_asset",
                    asset_id=asset_id,
                )
            )


        # ==================================================
        # COST VALIDATION
        # ==========================================================

        purchase_cost_value = None

        if purchase_cost:

            try:

                purchase_cost_value = Decimal(
                    purchase_cost.replace(",", "")
                )

                if purchase_cost_value < 0:
                    raise ValueError

            except (
                InvalidOperation,
                ValueError,
            ):

                flash(
                    "Purchase cost must be zero or greater.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_it_asset",
                        asset_id=asset_id,
                    )
                )


        # ==================================================
        # CONDITION VALIDATION
        # ==========================================================

        allowed_conditions = {
            "NEW",
            "GOOD",
            "FAIR",
            "POOR",
            "DAMAGED",
        }

        if condition_status not in allowed_conditions:

            flash(
                "Invalid asset condition.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_it_asset",
                    asset_id=asset_id,
                )
            )


        # ==================================================
        # UPDATE
        # ==========================================================

        try:

            update_it_asset(
                asset_id=asset_id,
                asset_tag=asset_tag,
                asset_name=asset_name,
                category_id=category_id_value,
                brand=brand or None,
                model=model or None,
                serial_number=serial_number or None,
                department_id=department_id_value,
                purchase_date=purchase_date or None,
                purchase_cost=purchase_cost_value,
                warranty_expiry=warranty_expiry or None,
                condition_status=condition_status,
                notes=notes or None,
            )

        except Exception as error:

            if getattr(error, "errno", None) == 1062:

                flash(
                    "Asset tag or serial number already exists.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_it_asset",
                        asset_id=asset_id,
                    )
                )

            raise


        flash(
            "IT asset updated successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )

    return render_template(
        "it_assets/edit.html",
        asset=asset,
        categories=categories,
        departments=departments,
    )


# ==========================================================
# IT MANAGEMENT - ASSIGN ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/assign",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def assign_it_asset_route(asset_id):

    employee_id = request.form.get(
        "employee_id",
        "",
    ).strip()

    if not employee_id:

        flash(
            "Select an employee.",
            "danger",
        )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )

    try:
        employee_id_value = int(
            employee_id
        )

    except ValueError:

        flash(
            "Invalid employee.",
            "danger",
        )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )

    employee = get_employee_by_id(
        employee_id_value
    )

    if not employee:

        flash(
            "Employee not found.",
            "danger",
        )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )

    try:

        assign_it_asset(
    asset_id=asset_id,
    employee_id=employee_id_value,
    department_id=employee["department_id"],
    assigned_by=session["user_id"],
)

        flash(
            "IT asset assigned successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_it_asset",
            asset_id=asset_id,
        )
    )


# ==========================================================
# IT MANAGEMENT - UNASSIGN ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/unassign",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def unassign_it_asset_route(asset_id):

    try:

        unassign_it_asset(
    asset_id=asset_id,
    returned_by=session["user_id"],
)

        flash(
            "IT asset unassigned successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_it_asset",
            asset_id=asset_id,
        )
    )


# ==========================================================
# IT MANAGEMENT - ADD ASSET MAINTENANCE
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/maintenance/add",
    methods=["GET", "POST"],
)
@permission_required("it_assets.manage")
def add_it_asset_maintenance(asset_id):

    asset = get_it_asset_by_id(
        asset_id
    )

    if not asset:

        flash(
            "IT asset not found.",
            "danger",
        )

        return redirect(
            url_for("it_assets")
        )

    if request.method == "POST":

        maintenance_type = request.form.get(
            "maintenance_type",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        vendor = request.form.get(
            "vendor",
            "",
        ).strip()

        cost = request.form.get(
            "cost",
            "",
        ).strip()

        start_date = request.form.get(
            "start_date",
            "",
        ).strip()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # VALIDATION
        # ==========================================================

        if (
            not maintenance_type
            or not description
            or not start_date
        ):

            flash(
                "Maintenance type, description, and "
                "start date are required.",
                "danger",
            )

            return redirect(
                url_for(
                    "add_it_asset_maintenance",
                    asset_id=asset_id,
                )
            )

        cost_value = None

        if cost:

            try:

                cost_value = Decimal(
                    cost.replace(",", "")
                )

                if cost_value < 0:
                    raise ValueError

            except (
                InvalidOperation,
                ValueError,
            ):

                flash(
                    "Maintenance cost must be zero or greater.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "add_it_asset_maintenance",
                        asset_id=asset_id,
                    )
                )


        # ==================================================
        # CREATE RECORD
        # ==========================================================

        try:

            create_it_asset_maintenance(
                asset_id=asset_id,
                maintenance_type=maintenance_type,
                description=description,
                vendor=vendor or None,
                cost=cost_value,
                start_date=start_date,
                notes=notes or None,
                created_by=session["user_id"],
            )

            flash(
                "Maintenance record created successfully.",
                "success",
            )

        except ValueError as error:

            flash(
                str(error),
                "danger",
            )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )


    return render_template(
        "it_assets/add_maintenance.html",
        asset=asset,
    )


# ==========================================================
# IT MANAGEMENT - COMPLETE MAINTENANCE
# ==========================================================

@app.route(
    "/it/assets/maintenance/<int:maintenance_id>/complete",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def complete_it_asset_maintenance_route(
    maintenance_id,
):

    completed_date = request.form.get(
        "completed_date",
        "",
    ).strip()

    if not completed_date:

        flash(
            "Completion date is required.",
            "danger",
        )

        return redirect(
            url_for("it_assets")
        )

    try:

        asset_id = complete_it_asset_maintenance(
            maintenance_id,
            completed_date,
        )

        flash(
            "Maintenance completed successfully.",
            "success",
        )

        return redirect(
            url_for(
                "view_it_asset",
                asset_id=asset_id,
            )
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for("it_assets")
        )


# ==========================================================
# IT MANAGEMENT - RETIRE ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/retire",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def retire_it_asset_route(asset_id):

    try:

        retire_it_asset(
            asset_id
        )

        flash(
            "IT asset retired successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_it_asset",
            asset_id=asset_id,
        )
    )


# ==========================================================
# IT MANAGEMENT - MARK AS LOST
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/lost",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def mark_it_asset_lost_route(asset_id):

    try:

        mark_it_asset_lost(
            asset_id
        )

        flash(
            "IT asset marked as lost.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_it_asset",
            asset_id=asset_id,
        )
    )


# ==========================================================
# IT MANAGEMENT - RESTORE ASSET
# ==========================================================

@app.route(
    "/it/assets/<int:asset_id>/restore",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def restore_it_asset_route(asset_id):

    try:

        restore_it_asset(
            asset_id
        )

        flash(
            "IT asset restored successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_it_asset",
            asset_id=asset_id,
        )
    )



# ==========================================================
# IT MANAGEMENT - ASSET CATEGORIES
# ==========================================================

@app.route("/it/assets/categories")
@permission_required("it_assets.view")
def it_asset_categories():

    categories = get_all_it_asset_categories()

    return render_template(
        "it_assets/categories/index.html",
        categories=categories,
    )


# ==========================================================
# IT MANAGEMENT - ADD ASSET CATEGORY
# ==========================================================

@app.route(
    "/it/assets/categories/add",
    methods=["GET", "POST"],
)
@permission_required("it_assets.manage")
def add_it_asset_category():

    if request.method == "POST":

        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()


        # ==================================================
        # VALIDATION
        # ==========================================================

        if not category_code or not category_name:

            flash(
                "Category code and category name are required.",
                "danger",
            )

            return render_template(
                "it_assets/categories/add.html"
            )


        # ==================================================
        # DATABASE INSERT
        # ==========================================================

        try:

            create_it_asset_category(
                category_code,
                category_name,
                description or None,
            )

        except Exception as error:

            if getattr(error, "errno", None) == 1062:

                flash(
                    "Asset category code already exists.",
                    "danger",
                )

                return render_template(
                    "it_assets/categories/add.html"
                )

            raise


        flash(
            "Asset category created successfully.",
            "success",
        )

        return redirect(
            url_for("it_asset_categories")
        )


    return render_template(
        "it_assets/categories/add.html"
    )


# ==========================================================
# IT MANAGEMENT - EDIT ASSET CATEGORY
# ==========================================================

@app.route(
    "/it/assets/categories/<int:category_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("it_assets.manage")
def edit_it_asset_category(category_id):

    category = get_it_asset_category_by_id(
        category_id
    )

    if not category:

        flash(
            "Asset category not found.",
            "danger",
        )

        return redirect(
            url_for("it_asset_categories")
        )


    if request.method == "POST":

        category_code = request.form.get(
            "category_code",
            "",
        ).strip().upper()

        category_name = request.form.get(
            "category_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()


        if not category_code or not category_name:

            flash(
                "Category code and category name are required.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_it_asset_category",
                    category_id=category_id,
                )
            )


        try:

            update_it_asset_category(
                category_id,
                category_code,
                category_name,
                description or None,
            )

        except Exception as error:

            if getattr(error, "errno", None) == 1062:

                flash(
                    "Asset category code already exists.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_it_asset_category",
                        category_id=category_id,
                    )
                )

            raise


        flash(
            "Asset category updated successfully.",
            "success",
        )

        return redirect(
            url_for("it_asset_categories")
        )


    return render_template(
        "it_assets/categories/edit.html",
        category=category,
    )




# ==========================================================
# IT MANAGEMENT - CATEGORY STATUS
# ==========================================================

@app.route(
    "/it/assets/categories/<int:category_id>/status",
    methods=["POST"],
)
@permission_required("it_assets.manage")
def change_it_asset_category_status(category_id):

    category = get_it_asset_category_by_id(
        category_id
    )

    if not category:

        flash(
            "Asset category not found.",
            "danger",
        )

        return redirect(
            url_for("it_asset_categories")
        )

    new_status = not bool(
        category["is_active"]
    )

    set_it_asset_category_active_status(
        category_id,
        new_status,
    )

    flash(
        (
            "Asset category activated successfully."
            if new_status
            else "Asset category deactivated successfully."
        ),
        "success",
    )

    return redirect(
        url_for("it_asset_categories")
    )

# ==========================================================
# IT MANAGEMENT - IT ASSET REPORTS
# ==========================================================

@app.route("/it/assets/reports")
@permission_required("it_assets.view")
def it_asset_reports():

    # ======================================================
    # SUMMARY
    # ======================================================

    summary = get_it_asset_summary()


    # ======================================================
    # CATEGORY REPORT
    # ======================================================

    category_summary = (
        get_it_asset_report_by_category()
    )


    # ======================================================
    # DEPARTMENT REPORT
    # ======================================================

    department_summary = (
        get_it_asset_report_by_department()
    )


    # ======================================================
    # ASSET REGISTER
    # ======================================================

    assets = get_filtered_it_assets()


    # ======================================================
    # SHOW REPORT
    # ======================================================

    return render_template(
        "it_assets/reports/index.html",
        summary=summary,
        category_summary=category_summary,
        department_summary=department_summary,
        assets=assets,
    )


# ==========================================================
# IT MANAGEMENT - EXPORT ASSET REPORT
# ==========================================================

@app.route("/it/assets/reports/export")
@permission_required("it_assets.view")
def export_it_asset_report():

    # ======================================================
    # GET REPORT DATA
    # ======================================================

    summary = get_it_asset_summary()

    category_summary = (
        get_it_asset_report_by_category()
    )

    department_summary = (
        get_it_asset_report_by_department()
    )

    assets = get_filtered_it_assets()


    # ======================================================
    # GENERATE EXCEL FILE
    # ======================================================

    excel_file = (
        generate_it_asset_report_excel(
            summary=summary,
            category_summary=category_summary,
            department_summary=department_summary,
            assets=assets,
        )
    )


    # ======================================================
    # DOWNLOAD
    # ======================================================

    return send_file(
        excel_file,
        as_attachment=True,
        download_name=(
            "IT_Asset_Report.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )

# ==========================================================
# IT MANAGEMENT - HELP DESK
# ==========================================================

@app.route("/it/help-desk")
@permission_required("helpdesk.view")
def help_desk():

    # ======================================================
    # FILTER INPUT
    # ======================================================

    search_text = request.args.get(
        "search",
        "",
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip().upper()

    selected_priority = request.args.get(
        "priority",
        "",
    ).strip().upper()

    selected_category = request.args.get(
        "category_id",
        "",
    ).strip()


    # ======================================================
    # VALIDATION
    # ======================================================

    allowed_statuses = {
        "OPEN",
        "IN_PROGRESS",
        "RESOLVED",
        "CLOSED",
        "CANCELLED",
    }

    if (
        selected_status
        and selected_status not in allowed_statuses
    ):
        selected_status = ""

    allowed_priorities = {
        "LOW",
        "MEDIUM",
        "HIGH",
        "URGENT",
    }

    if (
        selected_priority
        and selected_priority not in allowed_priorities
    ):
        selected_priority = ""


    category_id_value = None

    if selected_category:

        try:

            category_id_value = int(
                selected_category
            )

        except ValueError:

            selected_category = ""


    # ======================================================
    # DATA
    # ======================================================

    tickets = get_filtered_helpdesk_tickets(
        search_text=search_text or None,
        status=selected_status or None,
        priority=selected_priority or None,
        category_id=category_id_value,
    )

    summary = get_helpdesk_summary()

    categories = (
        get_active_helpdesk_categories()
    )


    return render_template(
        "help_desk/index.html",
        tickets=tickets,
        summary=summary,
        categories=categories,
        search_text=search_text,
        selected_status=selected_status,
        selected_priority=selected_priority,
        selected_category=selected_category,
    )

# ==========================================================
# IT MANAGEMENT - HELP DESK REPORTS
# ==========================================================

@app.route("/it/help-desk/reports")
@permission_required("helpdesk.view")
def help_desk_reports():

    # ======================================================
    # SUMMARY
    # ======================================================

    summary = get_helpdesk_summary()


    # ======================================================
    # CATEGORY REPORT
    # ======================================================

    category_summary = (
        get_helpdesk_report_by_category()
    )


    # ======================================================
    # TECHNICIAN REPORT
    # ======================================================

    technician_summary = (
        get_helpdesk_report_by_technician()
    )


    # ======================================================
    # TICKET REGISTER
    # ======================================================

    tickets = get_all_helpdesk_tickets()


    # ======================================================
    # SHOW REPORT PAGE
    # ======================================================

    return render_template(
        "help_desk/reports/index.html",
        summary=summary,
        category_summary=category_summary,
        technician_summary=technician_summary,
        tickets=tickets,
    )


# ==========================================================
# IT MANAGEMENT - EXPORT HELP DESK REPORT
# ==========================================================

@app.route("/it/help-desk/reports/export")
@permission_required("helpdesk.view")
def export_help_desk_report():

    # ======================================================
    # REPORT DATA
    # ======================================================

    summary = get_helpdesk_summary()

    category_summary = (
        get_helpdesk_report_by_category()
    )

    technician_summary = (
        get_helpdesk_report_by_technician()
    )

    tickets = get_all_helpdesk_tickets()


    # ======================================================
    # CREATE EXCEL FILE
    # ======================================================

    excel_file = (
        generate_helpdesk_report_excel(
            summary=summary,
            category_summary=category_summary,
            technician_summary=technician_summary,
            tickets=tickets,
        )
    )


    # ======================================================
    # DOWNLOAD
    # ======================================================

    return send_file(
        excel_file,
        as_attachment=True,
        download_name=(
            "Help_Desk_Report.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )


# ==========================================================
# IT MANAGEMENT - CREATE HELP DESK TICKET
# ==========================================================

@app.route(
    "/it/help-desk/add",
    methods=["GET", "POST"],
)
@permission_required("helpdesk.manage")
def add_helpdesk_ticket():

    employees = get_all_employees()

    categories = (
        get_active_helpdesk_categories()
    )


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()

        category_id = request.form.get(
            "category_id",
            "",
        ).strip()

        subject = request.form.get(
            "subject",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        priority = request.form.get(
            "priority",
            "MEDIUM",
        ).strip().upper()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not employee_id
            or not category_id
            or not subject
            or not description
        ):

            flash(
                "Employee, category, subject, "
                "and description are required.",
                "danger",
            )

            return render_template(
                "help_desk/add.html",
                employees=employees,
                categories=categories,
            )


        # ==================================================
        # ID VALIDATION
        # ==========================================================

        try:

            employee_id_value = int(
                employee_id
            )

            category_id_value = int(
                category_id
            )

        except ValueError:

            flash(
                "Invalid employee or category.",
                "danger",
            )

            return redirect(
                url_for("add_helpdesk_ticket")
            )


        # ==================================================
        # PRIORITY VALIDATION
        # ==========================================================

        allowed_priorities = {
            "LOW",
            "MEDIUM",
            "HIGH",
            "URGENT",
        }

        if priority not in allowed_priorities:

            flash(
                "Invalid ticket priority.",
                "danger",
            )

            return redirect(
                url_for("add_helpdesk_ticket")
            )


        # ==================================================
        # EMPLOYEE VALIDATION
        # ==========================================================

        employee = get_employee_by_id(
            employee_id_value
        )

        if not employee:

            flash(
                "Employee not found.",
                "danger",
            )

            return redirect(
                url_for("add_helpdesk_ticket")
            )


        # ==================================================
        # CREATE TICKET
        # ==========================================================

        ticket_id, ticket_number = (
            create_helpdesk_ticket(
                employee_id=employee_id_value,
                department_id=employee[
                    "department_id"
                ],
                category_id=category_id_value,
                subject=subject,
                description=description,
                priority=priority,
                created_by=session["user_id"],
            )
        )


        # ==================================================
        # SUCCESS
        # ==========================================================

        flash(
            (
                f"Ticket {ticket_number} "
                "created successfully."
            ),
            "success",
        )

        return redirect(
            url_for("help_desk")
        )


    # ======================================================
    # SHOW FORM
    # ======================================================

    return render_template(
        "help_desk/add.html",
        employees=employees,
        categories=categories,
    )



# ==========================================================
# IT MANAGEMENT - VIEW HELP DESK TICKET
# ==========================================================

@app.route(
    "/it/help-desk/<int:ticket_id>"
)
@permission_required("helpdesk.view")
def view_helpdesk_ticket(ticket_id):

    # ======================================================
    # GET TICKET
    # ======================================================

    ticket = get_helpdesk_ticket_by_id(
        ticket_id
    )

    if not ticket:

        flash(
            "Help desk ticket not found.",
            "danger",
        )

        return redirect(
            url_for("help_desk")
        )


    # ======================================================
    # GET TECHNICIANS
    # ======================================================

    technicians = (
        get_helpdesk_assignable_users()
    )


    # ======================================================
    # GET TICKET HISTORY
    # ======================================================

    ticket_history = (
        get_helpdesk_ticket_history(
            ticket_id
        )
    )


    # ======================================================
    # SHOW TICKET DETAILS PAGE
    # ======================================================

    return render_template(
        "help_desk/view.html",
        ticket=ticket,
        technicians=technicians,
        ticket_history=ticket_history,
    )

# ==========================================================
# IT MANAGEMENT - ASSIGN TICKET
# ==========================================================

@app.route(
    "/it/help-desk/<int:ticket_id>/assign",
    methods=["POST"],
)
@permission_required("helpdesk.manage")
def assign_helpdesk_ticket_route(ticket_id):

    assigned_to = request.form.get(
        "assigned_to",
        "",
    ).strip()

    if not assigned_to:

        flash(
            "Select a technician.",
            "danger",
        )

        return redirect(
            url_for(
                "view_helpdesk_ticket",
                ticket_id=ticket_id,
            )
        )

    try:

        assigned_to_value = int(
            assigned_to
        )

    except ValueError:

        flash(
            "Invalid technician.",
            "danger",
        )

        return redirect(
            url_for(
                "view_helpdesk_ticket",
                ticket_id=ticket_id,
            )
        )


    # ======================================================
    # VERIFY TECHNICIAN
    # ======================================================

    technicians = (
        get_helpdesk_assignable_users()
    )

    valid_user_ids = {
        technician["user_id"]
        for technician in technicians
    }

    if assigned_to_value not in valid_user_ids:

        flash(
            "Selected technician is invalid.",
            "danger",
        )

        return redirect(
            url_for(
                "view_helpdesk_ticket",
                ticket_id=ticket_id,
            )
        )


    # ======================================================
    # ASSIGN
    # ======================================================

    try:

        assign_helpdesk_ticket(
            ticket_id,
            assigned_to_value,
            session["user_id"],
        )

        flash(
            "Technician assigned successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_helpdesk_ticket",
            ticket_id=ticket_id,
        )
    )

# ==========================================================
# IT MANAGEMENT - START TICKET
# ==========================================================

@app.route(
    "/it/help-desk/<int:ticket_id>/start",
    methods=["POST"],
)
@permission_required("helpdesk.manage")
def start_helpdesk_ticket_route(ticket_id):

    try:

        start_helpdesk_ticket(
            ticket_id,
            session["user_id"],
        )

        flash(
            "Ticket is now in progress.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_helpdesk_ticket",
            ticket_id=ticket_id,
        )
    )

# ==========================================================
# IT MANAGEMENT - RESOLVE TICKET
# ==========================================================

@app.route(
    "/it/help-desk/<int:ticket_id>/resolve",
    methods=["POST"],
)
@permission_required("helpdesk.manage")
def resolve_helpdesk_ticket_route(ticket_id):

    resolution = request.form.get(
        "resolution",
        "",
    ).strip()

    if not resolution:

        flash(
            "Resolution details are required.",
            "danger",
        )

        return redirect(
            url_for(
                "view_helpdesk_ticket",
                ticket_id=ticket_id,
            )
        )

    try:

        resolve_helpdesk_ticket(
            ticket_id,
            resolution,
            session["user_id"],
        )

        flash(
            "Ticket resolved successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_helpdesk_ticket",
            ticket_id=ticket_id,
        )
    )

# ==========================================================
# IT MANAGEMENT - CLOSE TICKET
# ==========================================================

@app.route(
    "/it/help-desk/<int:ticket_id>/close",
    methods=["POST"],
)
@permission_required("helpdesk.manage")
def close_helpdesk_ticket_route(ticket_id):

    try:

        close_helpdesk_ticket(
            ticket_id,
            session["user_id"],
        )

        flash(
            "Ticket closed successfully.",
            "success",
        )

    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

    return redirect(
        url_for(
            "view_helpdesk_ticket",
            ticket_id=ticket_id,
        )
    )

# ==========================================================
# ADMINISTRATION - USERS
# ==========================================================

@app.route("/admin/users")
@permission_required("users.manage")
def admin_users():

    users = get_all_users()

    roles = get_all_roles()

    return render_template(
        "admin/users/index.html",
        users=users,
        roles=roles,
    )


# ==========================================================
# ADMINISTRATION - CREATE USER
# ==========================================================

@app.route(
    "/admin/users/add",
    methods=["GET", "POST"],
)
@permission_required("users.manage")
def add_admin_user():

    roles = get_all_roles()

    employees = (
        get_available_user_employees()
    )


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        username = request.form.get(
            "username",
            "",
        ).strip()

        password = request.form.get(
            "password",
            "",
        )

        confirm_password = request.form.get(
            "confirm_password",
            "",
        )

        role_id = request.form.get(
            "role_id",
            "",
        ).strip()

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not username
            or not password
            or not role_id
        ):

            flash(
                "Username, password, and role are required.",
                "danger",
            )

            return render_template(
                "admin/users/add.html",
                roles=roles,
                employees=employees,
            )


        # ==================================================
        # USERNAME VALIDATION
        # ==========================================================

        if len(username) > 100:

            flash(
                "Username must not exceed 100 characters.",
                "danger",
            )

            return render_template(
                "admin/users/add.html",
                roles=roles,
                employees=employees,
            )


        # ==================================================
        # PASSWORD VALIDATION
        # ==========================================================

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "danger",
            )

            return render_template(
                "admin/users/add.html",
                roles=roles,
                employees=employees,
            )

        if password != confirm_password:

            flash(
                "Password confirmation does not match.",
                "danger",
            )

            return render_template(
                "admin/users/add.html",
                roles=roles,
                employees=employees,
            )


        # ==================================================
        # ROLE VALIDATION
        # ==========================================================

        try:

            role_id_value = int(
                role_id
            )

        except ValueError:

            flash(
                "Invalid role.",
                "danger",
            )

            return redirect(
                url_for("add_admin_user")
            )


        valid_role_ids = {
            role["role_id"]
            for role in roles
        }

        if role_id_value not in valid_role_ids:

            flash(
                "Selected role does not exist.",
                "danger",
            )

            return redirect(
                url_for("add_admin_user")
            )


        # ==================================================
        # EMPLOYEE VALIDATION
        # ==========================================================

        employee_id_value = None

        if employee_id:

            try:

                employee_id_value = int(
                    employee_id
                )

            except ValueError:

                flash(
                    "Invalid employee.",
                    "danger",
                )

                return redirect(
                    url_for("add_admin_user")
                )


            valid_employee_ids = {
                employee["employee_id"]
                for employee in employees
            }

            if (
                employee_id_value
                not in valid_employee_ids
            ):

                flash(
                    (
                        "Selected employee already has "
                        "a user account or does not exist."
                    ),
                    "danger",
                )

                return redirect(
                    url_for("add_admin_user")
                )


        # ==================================================
        # PASSWORD HASH
        # ==========================================================

        password_hash = (
            generate_password_hash(
                password
            )
        )


        # ==================================================
        # CREATE USER
        # ==========================================================

        try:

            create_user(
                username=username,
                password_hash=password_hash,
                role_id=role_id_value,
                employee_id=employee_id_value,
            )

        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "Username already exists or "
                        "the employee already has an account."
                    ),
                    "danger",
                )

                return redirect(
                    url_for("add_admin_user")
                )

            raise


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="ADMINISTRATION",
            action="CREATE",
            entity_type="USER",
            entity_id=username,
            description="User account created.",
        )

        flash(
            "User account created successfully.",
            "success",
        )

        return redirect(
            url_for("admin_users")
        )
    

    return render_template(
        "admin/users/add.html",
        roles=roles,
        employees=employees,
    )

# ==========================================================
# ATTENDANCE MANAGEMENT
# ==========================================================

@app.route("/attendance")
@permission_required("attendance.view")
def attendance():

    # ======================================================
    # FILTER INPUT
    # ==========================================================

    search_text = request.args.get(
        "search",
        "",
    ).strip()

    selected_date = request.args.get(
        "date",
        "",
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip().upper()

    selected_department = request.args.get(
        "department_id",
        "",
    ).strip()


    # ======================================================
    # STATUS VALIDATION
    # ==========================================================

    allowed_statuses = {
        "PRESENT",
        "LATE",
        "ABSENT",
        "ON_LEAVE",
        "HALF_DAY",
    }

    if (
        selected_status
        and selected_status not in allowed_statuses
    ):

        selected_status = ""


    # ======================================================
    # DATE VALIDATION
    # ==========================================================

    selected_date_value = None

    if selected_date:

        try:

            selected_date_value = (
                date.fromisoformat(
                    selected_date
                )
            )

        except ValueError:

            selected_date = ""


    # ======================================================
    # DEPARTMENT VALIDATION
    # ==========================================================

    department_id_value = None

    if selected_department:

        try:

            department_id_value = int(
                selected_department
            )

        except ValueError:

            selected_department = ""


    # ======================================================
    # GET FILTERED RECORDS
    # ==========================================================

    attendance_records = (
        get_filtered_attendance_records(
            search_text=search_text or None,
            attendance_date=selected_date_value,
            status=selected_status or None,
            department_id=department_id_value,
        )
    )


    # ======================================================
    # SUMMARY
    #
    # Summary reflects the current filtered records.
    # ==========================================================

    summary = {
        "total": len(
            attendance_records
        ),

        "present": sum(
            1
            for record in attendance_records
            if record["status"] == "PRESENT"
        ),

        "late": sum(
            1
            for record in attendance_records
            if record["status"] == "LATE"
        ),

        "absent": sum(
            1
            for record in attendance_records
            if record["status"] == "ABSENT"
        ),

        "on_leave": sum(
            1
            for record in attendance_records
            if record["status"] == "ON_LEAVE"
        ),

        "half_day": sum(
            1
            for record in attendance_records
            if record["status"] == "HALF_DAY"
        ),
    }




    # ======================================================
    # DEPARTMENT FILTER OPTIONS
    # ==========================================================

    departments = (
        get_active_departments()
    )


    # ======================================================
    # SHOW PAGE
    # ==========================================================

    return render_template(
        "attendance/index.html",
        attendance_records=attendance_records,
        summary=summary,
        departments=departments,
        search_text=search_text,
        selected_date=selected_date,
        selected_status=selected_status,
        selected_department=selected_department,
    )


# ==========================================================
# ATTENDANCE - ADD RECORD
# ==========================================================

@app.route(
    "/attendance/add",
    methods=["GET", "POST"],
)
@permission_required("attendance.manage")
def add_attendance():

    employees = get_all_employees()

    allowed_statuses = {
        "PRESENT",
        "LATE",
        "ABSENT",
        "ON_LEAVE",
        "HALF_DAY",
    }


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()

        attendance_date = request.form.get(
            "attendance_date",
            "",
        ).strip()

        time_in = request.form.get(
            "time_in",
            "",
        ).strip()

        time_out = request.form.get(
            "time_out",
            "",
        ).strip()

        status = request.form.get(
            "status",
            "",
        ).strip().upper()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not employee_id
            or not attendance_date
            or not status
        ):

            flash(
                (
                    "Employee, attendance date, "
                    "and status are required."
                ),
                "danger",
            )

            return render_template(
                "attendance/add.html",
                employees=employees,
                today=date.today().isoformat(),
                allowed_statuses=allowed_statuses,
            )


        # ==================================================
        # EMPLOYEE VALIDATION
        # ==========================================================

        try:

            employee_id_value = int(
                employee_id
            )

        except ValueError:

            flash(
                "Invalid employee.",
                "danger",
            )

            return redirect(
                url_for("add_attendance")
            )


        employee = get_employee_by_id(
            employee_id_value
        )

        if not employee:

            flash(
                "Employee not found.",
                "danger",
            )

            return redirect(
                url_for("add_attendance")
            )


        # ==================================================
        # DATE VALIDATION
        # ==========================================================

        try:

            attendance_date_value = (
                date.fromisoformat(
                    attendance_date
                )
            )

        except ValueError:

            flash(
                "Invalid attendance date.",
                "danger",
            )

            return redirect(
                url_for("add_attendance")
            )


        # ==================================================
        # STATUS VALIDATION
        # ==========================================================

        if status not in allowed_statuses:

            flash(
                "Invalid attendance status.",
                "danger",
            )

            return redirect(
                url_for("add_attendance")
            )


        # ==================================================
        # TIME VALIDATION
        # ==========================================================

        time_in_value = None

        if time_in:

            try:

                time_in_value = (
                    datetime.strptime(
                        time_in,
                        "%H:%M",
                    ).time()
                )

            except ValueError:

                flash(
                    "Invalid Time In.",
                    "danger",
                )

                return redirect(
                    url_for("add_attendance")
                )


        time_out_value = None

        if time_out:

            try:

                time_out_value = (
                    datetime.strptime(
                        time_out,
                        "%H:%M",
                    ).time()
                )

            except ValueError:

                flash(
                    "Invalid Time Out.",
                    "danger",
                )

                return redirect(
                    url_for("add_attendance")
                )


        # ==================================================
        # NOTES VALIDATION
        # ==========================================================

        if len(notes) > 255:

            flash(
                "Notes must not exceed 255 characters.",
                "danger",
            )

            return redirect(
                url_for("add_attendance")
            )


        # ==================================================
        # CREATE ATTENDANCE RECORD
        # ==========================================================

        try:

            create_attendance_record(
                employee_id=employee_id_value,
                attendance_date=attendance_date_value,
                time_in=time_in_value,
                time_out=time_out_value,
                status=status,
                notes=notes or None,
                created_by=session["user_id"],
            )

        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "This employee already has "
                        "an attendance record for that date."
                    ),
                    "danger",
                )

                return redirect(
                    url_for("add_attendance")
                )

            raise


        flash(
            "Attendance record created successfully.",
            "success",
        )

        return redirect(
            url_for("attendance")
        )


    return render_template(
        "attendance/add.html",
        employees=employees,
        today=date.today().isoformat(),
        allowed_statuses=allowed_statuses,
    )


# ==========================================================
# ATTENDANCE - EDIT RECORD
# ==========================================================

@app.route(
    "/attendance/<int:attendance_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("attendance.manage")
def edit_attendance(attendance_id):

    attendance_record = (
        get_attendance_record_by_id(
            attendance_id
        )
    )

    if not attendance_record:

        flash(
            "Attendance record not found.",
            "danger",
        )

        return redirect(
            url_for("attendance")
        )


    employees = get_all_employees()

    allowed_statuses = {
        "PRESENT",
        "LATE",
        "ABSENT",
        "ON_LEAVE",
        "HALF_DAY",
    }


    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()

        attendance_date = request.form.get(
            "attendance_date",
            "",
        ).strip()

        time_in = request.form.get(
            "time_in",
            "",
        ).strip()

        time_out = request.form.get(
            "time_out",
            "",
        ).strip()

        status = request.form.get(
            "status",
            "",
        ).strip().upper()

        notes = request.form.get(
            "notes",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not employee_id
            or not attendance_date
            or not status
        ):

            flash(
                (
                    "Employee, attendance date, "
                    "and status are required."
                ),
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        try:

            employee_id_value = int(
                employee_id
            )

        except ValueError:

            flash(
                "Invalid employee.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        employee = get_employee_by_id(
            employee_id_value
        )

        if not employee:

            flash(
                "Employee not found.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        try:

            attendance_date_value = (
                date.fromisoformat(
                    attendance_date
                )
            )

        except ValueError:

            flash(
                "Invalid attendance date.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        if status not in allowed_statuses:

            flash(
                "Invalid attendance status.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        time_in_value = None

        if time_in:

            try:

                time_in_value = (
                    datetime.strptime(
                        time_in,
                        "%H:%M",
                    ).time()
                )

            except ValueError:

                flash(
                    "Invalid Time In.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_attendance",
                        attendance_id=attendance_id,
                    )
                )


        time_out_value = None

        if time_out:

            try:

                time_out_value = (
                    datetime.strptime(
                        time_out,
                        "%H:%M",
                    ).time()
                )

            except ValueError:

                flash(
                    "Invalid Time Out.",
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_attendance",
                        attendance_id=attendance_id,
                    )
                )


        if len(notes) > 255:

            flash(
                "Notes must not exceed 255 characters.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_attendance",
                    attendance_id=attendance_id,
                )
            )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        try:

            update_attendance_record(
                attendance_id=attendance_id,
                employee_id=employee_id_value,
                attendance_date=attendance_date_value,
                time_in=time_in_value,
                time_out=time_out_value,
                status=status,
                notes=notes or None,
                updated_by=session["user_id"],
            )

        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "This employee already has "
                        "an attendance record for that date."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_attendance",
                        attendance_id=attendance_id,
                    )
                )

            raise


        flash(
            "Attendance record updated successfully.",
            "success",
        )

        return redirect(
            url_for("attendance")
        )


    return render_template(
        "attendance/edit.html",
        attendance_record=attendance_record,
        employees=employees,
        allowed_statuses=allowed_statuses,
    )

# ==========================================================
# LEAVE MANAGEMENT - LEAVE TYPES
# ==========================================================

@app.route("/leave/types")
@permission_required("leave.view")
def leave_types():

    leave_type_list = (
        get_all_leave_types()
    )

    return render_template(
        "leave/types/index.html",
        leave_types=leave_type_list,
    )

# ==========================================================
# LEAVE MANAGEMENT - BALANCES
# ==========================================================

@app.route("/leave/balances")
@permission_required("leave.view")
def leave_balances():

    employees = get_all_employees()


    # ======================================================
    # FILTER INPUT
    # ==========================================================

    selected_employee = request.args.get(
        "employee_id",
        "",
    ).strip()

    selected_year = request.args.get(
        "year",
        str(date.today().year),
    ).strip()


    # ======================================================
    # YEAR VALIDATION
    # ==========================================================

    try:

        selected_year_value = int(
            selected_year
        )

        if (
            selected_year_value < 2000
            or selected_year_value > 2100
        ):

            raise ValueError


    except ValueError:

        selected_year_value = (
            date.today().year
        )

        selected_year = str(
            selected_year_value
        )


    # ======================================================
    # EMPLOYEE VALIDATION
    # ==========================================================

    employee = None

    balances = []


    if selected_employee:

        try:

            employee_id_value = int(
                selected_employee
            )

        except ValueError:

            selected_employee = ""

        else:

            employee = get_employee_by_id(
                employee_id_value
            )


            if employee:

                balances = (
                    get_employee_leave_balances(
                        employee_id=employee_id_value,
                        year=selected_year_value,
                    )
                )

            else:

                selected_employee = ""


    # ======================================================
    # SHOW PAGE
    # ==========================================================

    return render_template(
        "leave/balances/index.html",
        employees=employees,
        employee=employee,
        balances=balances,
        selected_employee=selected_employee,
        selected_year=selected_year,
    )


# ==========================================================
# LEAVE MANAGEMENT - ADD LEAVE TYPE
# ==========================================================

@app.route(
    "/leave/types/add",
    methods=["GET", "POST"],
)
@permission_required("leave.manage")
def add_leave_type():

    if request.method == "POST":

        leave_code = request.form.get(
            "leave_code",
            "",
        ).strip().upper()

        leave_name = request.form.get(
            "leave_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        entitlement = request.form.get(
            "annual_entitlement",
            "",
        ).strip()

        is_paid = (
            request.form.get("is_paid")
            == "1"
        )


        if not leave_code or not leave_name:

            flash(
                "Leave code and name are required.",
                "danger",
            )

            return render_template(
                "leave/types/add.html"
            )


        if len(leave_code) > 30:

            flash(
                "Leave code must not exceed 30 characters.",
                "danger",
            )

            return redirect(
                url_for("add_leave_type")
            )


        if len(leave_name) > 100:

            flash(
                "Leave name must not exceed 100 characters.",
                "danger",
            )

            return redirect(
                url_for("add_leave_type")
            )


        if len(description) > 255:

            flash(
                "Description must not exceed 255 characters.",
                "danger",
            )

            return redirect(
                url_for("add_leave_type")
            )


        entitlement_value = None

        if entitlement:

            try:

                entitlement_value = Decimal(
                    entitlement
                )

                if entitlement_value < 0:

                    raise ValueError

            except (
                InvalidOperation,
                ValueError,
            ):

                flash(
                    (
                        "Annual entitlement must "
                        "be zero or greater."
                    ),
                    "danger",
                )

                return redirect(
                    url_for("add_leave_type")
                )


        try:

            create_leave_type(
                leave_code=leave_code,
                leave_name=leave_name,
                description=description or None,
                annual_entitlement=entitlement_value,
                is_paid=is_paid,
            )

        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "Leave code or leave name "
                        "already exists."
                    ),
                    "danger",
                )

                return redirect(
                    url_for("add_leave_type")
                )

            raise


        flash(
            "Leave type created successfully.",
            "success",
        )

        return redirect(
            url_for("leave_types")
        )


    return render_template(
        "leave/types/add.html"
    )


# ==========================================================
# LEAVE MANAGEMENT - EDIT LEAVE TYPE
# ==========================================================

@app.route(
    "/leave/types/<int:leave_type_id>/edit",
    methods=["GET", "POST"],
)
@permission_required("leave.manage")
def edit_leave_type(
    leave_type_id,
):

    leave_type = (
        get_leave_type_by_id(
            leave_type_id
        )
    )

    if not leave_type:

        flash(
            "Leave type not found.",
            "danger",
        )

        return redirect(
            url_for("leave_types")
        )


    if request.method == "POST":

        leave_code = request.form.get(
            "leave_code",
            "",
        ).strip().upper()

        leave_name = request.form.get(
            "leave_name",
            "",
        ).strip()

        description = request.form.get(
            "description",
            "",
        ).strip()

        entitlement = request.form.get(
            "annual_entitlement",
            "",
        ).strip()

        is_paid = (
            request.form.get("is_paid")
            == "1"
        )


        if not leave_code or not leave_name:

            flash(
                "Leave code and name are required.",
                "danger",
            )

            return redirect(
                url_for(
                    "edit_leave_type",
                    leave_type_id=leave_type_id,
                )
            )


        entitlement_value = None

        if entitlement:

            try:

                entitlement_value = Decimal(
                    entitlement
                )

                if entitlement_value < 0:

                    raise ValueError

            except (
                InvalidOperation,
                ValueError,
            ):

                flash(
                    (
                        "Annual entitlement must "
                        "be zero or greater."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_leave_type",
                        leave_type_id=leave_type_id,
                    )
                )


        try:

            update_leave_type(
                leave_type_id=leave_type_id,
                leave_code=leave_code,
                leave_name=leave_name,
                description=description or None,
                annual_entitlement=entitlement_value,
                is_paid=is_paid,
            )

        except Exception as error:

            if getattr(
                error,
                "errno",
                None,
            ) == 1062:

                flash(
                    (
                        "Leave code or leave name "
                        "already exists."
                    ),
                    "danger",
                )

                return redirect(
                    url_for(
                        "edit_leave_type",
                        leave_type_id=leave_type_id,
                    )
                )

            raise


        flash(
            "Leave type updated successfully.",
            "success",
        )

        return redirect(
            url_for("leave_types")
        )


    return render_template(
        "leave/types/edit.html",
        leave_type=leave_type,
    )


# ==========================================================
# LEAVE MANAGEMENT - LEAVE TYPE STATUS
# ==========================================================

@app.route(
    "/leave/types/<int:leave_type_id>/status",
    methods=["POST"],
)
@permission_required("leave.manage")
def change_leave_type_status(
    leave_type_id,
):

    leave_type = (
        get_leave_type_by_id(
            leave_type_id
        )
    )

    if not leave_type:

        flash(
            "Leave type not found.",
            "danger",
        )

        return redirect(
            url_for("leave_types")
        )


    new_status = not bool(
        leave_type["is_active"]
    )


    set_leave_type_active_status(
        leave_type_id,
        new_status,
    )


    if new_status:

        flash(
            "Leave type activated successfully.",
            "success",
        )

    else:

        flash(
            "Leave type deactivated successfully.",
            "success",
        )


    return redirect(
        url_for("leave_types")
    )


# ==========================================================
# LEAVE MANAGEMENT - REQUESTS
# ==========================================================

@app.route("/leave/requests")
@permission_required("leave.view")
def leave_requests():

    requests_list = (
        get_all_leave_requests()
    )

    return render_template(
        "leave/requests/index.html",
        leave_requests=requests_list,
    )


# ==========================================================
# LEAVE MANAGEMENT - ADD REQUEST
# ==========================================================

@app.route(
    "/leave/requests/add",
    methods=["GET", "POST"],
)
@permission_required("leave.manage")
def add_leave_request():

    employees = get_all_employees()

    leave_types = (
        get_active_leave_types()
    )


    if request.method == "POST":

        employee_id = request.form.get(
            "employee_id",
            "",
        ).strip()

        leave_type_id = request.form.get(
            "leave_type_id",
            "",
        ).strip()

        start_date = request.form.get(
            "start_date",
            "",
        ).strip()

        end_date = request.form.get(
            "end_date",
            "",
        ).strip()

        reason = request.form.get(
            "reason",
            "",
        ).strip()


        # ==================================================
        # REQUIRED FIELDS
        # ==========================================================

        if (
            not employee_id
            or not leave_type_id
            or not start_date
            or not end_date
            or not reason
        ):

            flash(
                "All leave request fields are required.",
                "danger",
            )

            return render_template(
                "leave/requests/add.html",
                employees=employees,
                leave_types=leave_types,
            )


        # ==================================================
        # EMPLOYEE
        # ==========================================================

        try:

            employee_id_value = int(
                employee_id
            )

        except ValueError:

            flash(
                "Invalid employee.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        employee = get_employee_by_id(
            employee_id_value
        )

        if not employee:

            flash(
                "Employee not found.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        # ==================================================
        # LEAVE TYPE
        # ==========================================================

        try:

            leave_type_id_value = int(
                leave_type_id
            )

        except ValueError:

            flash(
                "Invalid leave type.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        leave_type = (
            get_leave_type_by_id(
                leave_type_id_value
            )
        )

        if (
            not leave_type
            or not leave_type["is_active"]
        ):

            flash(
                "Selected leave type is invalid or inactive.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        # ==================================================
        # DATE VALIDATION
        # ==========================================================

        try:

            start_date_value = (
                date.fromisoformat(
                    start_date
                )
            )

            end_date_value = (
                date.fromisoformat(
                    end_date
                )
            )

        except ValueError:

            flash(
                "Invalid leave date.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        if end_date_value < start_date_value:

            flash(
                (
                    "End date cannot be earlier "
                    "than start date."
                ),
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        # ==================================================
        # TOTAL DAYS
        # ==========================================================

        total_days = (
            end_date_value
            - start_date_value
        ).days + 1


        # ==================================================
        # OVERLAPPING REQUEST
        # ==========================================================

        if has_overlapping_leave_request(
            employee_id=employee_id_value,
            start_date=start_date_value,
            end_date=end_date_value,
        ):

            flash(
                (
                    "This employee already has a pending "
                    "or approved leave request that overlaps "
                    "the selected dates."
                ),
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        # ==================================================
        # REASON VALIDATION
        # ==========================================================

        if len(reason) > 500:

            flash(
                "Reason must not exceed 500 characters.",
                "danger",
            )

            return redirect(
                url_for("add_leave_request")
            )


        # ==================================================
        # CREATE REQUEST
        # ==========================================================

        (
            leave_request_id,
            request_number,
        ) = create_leave_request(
            employee_id=employee_id_value,
            leave_type_id=leave_type_id_value,
            start_date=start_date_value,
            end_date=end_date_value,
            total_days=total_days,
            reason=reason,
            requested_by=session["user_id"],
        )


        flash(
            (
                f"Leave request {request_number} "
                "created successfully."
            ),
            "success",
        )


        return redirect(
            url_for(
                "view_leave_request",
                leave_request_id=leave_request_id,
            )
        )


    return render_template(
        "leave/requests/add.html",
        employees=employees,
        leave_types=leave_types,
    )


# ==========================================================
# LEAVE MANAGEMENT - VIEW REQUEST
# ==========================================================

@app.route(
    "/leave/requests/<int:leave_request_id>"
)
@permission_required("leave.view")
def view_leave_request(
    leave_request_id,
):

    leave_request = (
        get_leave_request_by_id(
            leave_request_id
        )
    )


    if not leave_request:

        flash(
            "Leave request not found.",
            "danger",
        )

        return redirect(
            url_for("leave_requests")
        )


    return render_template(
        "leave/requests/view.html",
        leave_request=leave_request,
    )


# ==========================================================
# LEAVE MANAGEMENT - APPROVE REQUEST
# ==========================================================

@app.route(
    "/leave/requests/<int:leave_request_id>/approve",
    methods=["POST"],
)
@permission_required("leave.approve")
def approve_leave_request_route(
    leave_request_id,
):

    try:

        approve_leave_request(
            leave_request_id=leave_request_id,
            reviewed_by=session["user_id"],
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="LEAVE",
            action="APPROVE",
            entity_type="LEAVE_REQUEST",
            entity_id=leave_request_id,
            description="Leave request approved.",
            entity_lookup=get_leave_request_by_id,
            identifier_key="request_number",
        )

        flash(
            (
                "Leave request approved successfully. "
                "Attendance records were updated to On Leave."
            ),
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_leave_request",
            leave_request_id=leave_request_id,
        )
    )



# ==========================================================
# LEAVE MANAGEMENT - REJECT REQUEST
# ==========================================================

@app.route(
    "/leave/requests/<int:leave_request_id>/reject",
    methods=["POST"],
)
@permission_required("leave.approve")
def reject_leave_request_route(
    leave_request_id,
):

    # ======================================================
    # REJECTION REASON
    # ==========================================================

    rejection_reason = request.form.get(
        "rejection_reason",
        "",
    ).strip()


    if not rejection_reason:

        flash(
            "Rejection reason is required.",
            "danger",
        )

        return redirect(
            url_for(
                "view_leave_request",
                leave_request_id=leave_request_id,
            )
        )


    if len(rejection_reason) > 500:

        flash(
            (
                "Rejection reason must not "
                "exceed 500 characters."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_leave_request",
                leave_request_id=leave_request_id,
            )
        )


    try:

        reject_leave_request(
            leave_request_id=leave_request_id,
            reviewed_by=session["user_id"],
            rejection_reason=rejection_reason,
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="LEAVE",
            action="REJECT",
            entity_type="LEAVE_REQUEST",
            entity_id=leave_request_id,
            description="Leave request rejected.",
            entity_lookup=get_leave_request_by_id,
            identifier_key="request_number",
        )

        flash(
            "Leave request rejected.",
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_leave_request",
            leave_request_id=leave_request_id,
        )
    )

    # ==========================================================
# LEAVE MANAGEMENT - CANCEL REQUEST
# ==========================================================

@app.route(
    "/leave/requests/<int:leave_request_id>/cancel",
    methods=["POST"],
)
@permission_required("leave.manage")
def cancel_leave_request_route(
    leave_request_id,
):

    try:

        cancel_leave_request(
            leave_request_id
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="LEAVE",
            action="CANCEL",
            entity_type="LEAVE_REQUEST",
            entity_id=leave_request_id,
            description="Leave request cancelled.",
            entity_lookup=get_leave_request_by_id,
            identifier_key="request_number",
        )

        flash(
            "Leave request cancelled successfully.",
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_leave_request",
            leave_request_id=leave_request_id,
        )
    )

# ==========================================================
# LEAVE MANAGEMENT - REPORTS
# ==========================================================

@app.route("/leave/reports")
@permission_required("leave.view")
def leave_reports():

    # ======================================================
    # FILTER INPUT
    # ==========================================================

    selected_year = request.args.get(
        "year",
        str(date.today().year),
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip().upper()

    selected_employee = request.args.get(
        "employee_id",
        "",
    ).strip()

    selected_leave_type = request.args.get(
        "leave_type_id",
        "",
    ).strip()


    # ======================================================
    # YEAR VALIDATION
    # ==========================================================

    try:

        selected_year_value = int(
            selected_year
        )

        if (
            selected_year_value < 2000
            or selected_year_value > 2100
        ):

            raise ValueError

    except ValueError:

        selected_year_value = (
            date.today().year
        )

        selected_year = str(
            selected_year_value
        )


    # ======================================================
    # STATUS VALIDATION
    # ==========================================================

    allowed_statuses = {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "CANCELLED",
    }


    if (
        selected_status
        and selected_status
        not in allowed_statuses
    ):

        selected_status = ""


    # ======================================================
    # EMPLOYEE VALIDATION
    # ==========================================================

    employee_id_value = None


    if selected_employee:

        try:

            employee_id_value = int(
                selected_employee
            )

        except ValueError:

            selected_employee = ""


    # ======================================================
    # LEAVE TYPE VALIDATION
    # ==========================================================

    leave_type_id_value = None


    if selected_leave_type:

        try:

            leave_type_id_value = int(
                selected_leave_type
            )

        except ValueError:

            selected_leave_type = ""


    # ======================================================
    # REPORT DATA
    # ==========================================================

    summary = get_leave_report_summary(
        year=selected_year_value,
        status=selected_status or None,
        employee_id=employee_id_value,
        leave_type_id=leave_type_id_value,
    )


    type_summary = (
        get_leave_report_by_type(
            year=selected_year_value,
            status=selected_status or None,
            employee_id=employee_id_value,
            leave_type_id=leave_type_id_value,
        )
    )


    records = (
        get_leave_report_records(
            year=selected_year_value,
            status=selected_status or None,
            employee_id=employee_id_value,
            leave_type_id=leave_type_id_value,
        )
    )


    employees = get_all_employees()

    leave_types = get_all_leave_types()


    return render_template(
        "leave/reports/index.html",
        summary=summary,
        type_summary=type_summary,
        records=records,
        employees=employees,
        leave_types=leave_types,
        selected_year=selected_year,
        selected_status=selected_status,
        selected_employee=selected_employee,
        selected_leave_type=selected_leave_type,
    )

    # ==========================================================
# LEAVE MANAGEMENT - EXPORT REPORT
# ==========================================================

@app.route("/leave/reports/export")
@permission_required("leave.view")
def export_leave_report():

    # ======================================================
    # FILTER INPUT
    # ==========================================================

    selected_year = request.args.get(
        "year",
        str(date.today().year),
    ).strip()

    selected_status = request.args.get(
        "status",
        "",
    ).strip().upper()

    selected_employee = request.args.get(
        "employee_id",
        "",
    ).strip()

    selected_leave_type = request.args.get(
        "leave_type_id",
        "",
    ).strip()


    # ======================================================
    # YEAR
    # ==========================================================

    try:

        selected_year_value = int(
            selected_year
        )

        if (
            selected_year_value < 2000
            or selected_year_value > 2100
        ):

            raise ValueError

    except ValueError:

        selected_year_value = (
            date.today().year
        )


    # ======================================================
    # STATUS
    # ==========================================================

    allowed_statuses = {
        "PENDING",
        "APPROVED",
        "REJECTED",
        "CANCELLED",
    }


    if (
        selected_status
        not in allowed_statuses
    ):

        selected_status = ""


    # ======================================================
    # EMPLOYEE
    # ==========================================================

    employee_id_value = None


    if selected_employee:

        try:

            employee_id_value = int(
                selected_employee
            )

        except ValueError:

            selected_employee = ""


    # ======================================================
    # LEAVE TYPE
    # ==========================================================

    leave_type_id_value = None


    if selected_leave_type:

        try:

            leave_type_id_value = int(
                selected_leave_type
            )

        except ValueError:

            selected_leave_type = ""


    # ======================================================
    # REPORT DATA
    # ==========================================================

    summary = get_leave_report_summary(
        year=selected_year_value,
        status=selected_status or None,
        employee_id=employee_id_value,
        leave_type_id=leave_type_id_value,
    )


    type_summary = (
        get_leave_report_by_type(
            year=selected_year_value,
            status=selected_status or None,
            employee_id=employee_id_value,
            leave_type_id=leave_type_id_value,
        )
    )


    records = (
        get_leave_report_records(
            year=selected_year_value,
            status=selected_status or None,
            employee_id=employee_id_value,
            leave_type_id=leave_type_id_value,
        )
    )


    # ======================================================
    # READABLE FILTER LABELS
    # ==========================================================

    employees = get_all_employees()

    leave_types = get_all_leave_types()


    employee_label = "All Employees"


    if employee_id_value:

        employee = next(
            (
                item
                for item in employees
                if item["employee_id"]
                == employee_id_value
            ),
            None,
        )

        if employee:

            employee_label = (
                f"{employee['employee_number']} - "
                f"{employee['first_name']} "
                f"{employee['last_name']}"
            )


    leave_type_label = (
        "All Leave Types"
    )


    if leave_type_id_value:

        leave_type = next(
            (
                item
                for item in leave_types
                if item["leave_type_id"]
                == leave_type_id_value
            ),
            None,
        )

        if leave_type:

            leave_type_label = (
                leave_type[
                    "leave_name"
                ]
            )


    filter_labels = {
        "status": (
            selected_status
            or "All Statuses"
        ),

        "employee": (
            employee_label
        ),

        "leave_type": (
            leave_type_label
        ),
    }


    # ======================================================
    # CREATE EXCEL
    # ==========================================================

    excel_file = (
        generate_leave_report_excel(
            selected_year=selected_year_value,
            summary=summary,
            type_summary=type_summary,
            records=records,
            filter_labels=filter_labels,
        )
    )


    # ======================================================
    # DOWNLOAD
    # ==========================================================

    return send_file(
        excel_file,
        as_attachment=True,
        download_name=(
            f"Leave_Report_"
            f"{selected_year_value}.xlsx"
        ),
        mimetype=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )

# ==========================================================
# ADMINISTRATION - CHANGE USER ROLE
# ==========================================================

@app.route(
    "/admin/users/<int:user_id>/role",
    methods=["POST"],
)
@permission_required("users.manage")
def change_admin_user_role(user_id):

    user = get_user_by_id(
        user_id
    )

    if not user:

        flash(
            "User account not found.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    # ======================================================
    # DO NOT CHANGE YOUR OWN ROLE
    # ======================================================

    if user_id == session["user_id"]:

        flash(
            "You cannot change your own role.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    role_id = request.form.get(
        "role_id",
        "",
    ).strip()

    try:

        role_id_value = int(
            role_id
        )

    except ValueError:

        flash(
            "Invalid role.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    roles = get_all_roles()

    selected_role = next(
        (
            role
            for role in roles
            if role["role_id"]
            == role_id_value
        ),
        None,
    )

    if not selected_role:

        flash(
            "Selected role does not exist.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    # ======================================================
    # PROTECT LAST ACTIVE SUPER ADMIN
    # ======================================================

    if (
        user["role_name"] == "Super Admin"
        and selected_role["role_name"]
        != "Super Admin"
        and user["is_active"]
        and count_active_super_admins() <= 1
    ):

        flash(
            (
                "You cannot remove the role from "
                "the last active Super Admin."
            ),
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    update_user_role(
        user_id,
        role_id_value,
    )

    flash(
        "User role updated successfully.",
        "success",
    )

    return redirect(
        url_for("admin_users")
    )


# ==========================================================
# ADMINISTRATION - CHANGE USER STATUS
# ==========================================================

@app.route(
    "/admin/users/<int:user_id>/status",
    methods=["POST"],
)
@permission_required("users.manage")
def change_admin_user_status(user_id):

    # ======================================================
    # GET USER
    # ======================================================

    user = get_user_by_id(
        user_id
    )

    if not user:

        flash(
            "User account not found.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    # ======================================================
    # DO NOT DEACTIVATE YOUR OWN ACCOUNT
    # ======================================================

    if user_id == session["user_id"]:

        flash(
            "You cannot deactivate your own account.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    # ======================================================
    # NEW STATUS
    # ======================================================

    new_status = not bool(
        user["is_active"]
    )


    # ======================================================
    # PROTECT LAST ACTIVE SUPER ADMIN
    # ======================================================

    if (
        not new_status
        and user["role_name"] == "Super Admin"
        and count_active_super_admins() <= 1
    ):

        flash(
            (
                "You cannot deactivate the "
                "last active Super Admin."
            ),
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    # ======================================================
    # DATABASE UPDATE
    # ======================================================

    set_user_active_status(
        user_id,
        new_status,
    )


    # AUDIT LOG: The business action has committed successfully.
    record_audit_event(
        module="ADMINISTRATION",
        action="ACTIVATE" if new_status else "DEACTIVATE",
        entity_type="USER",
        entity_id=user["username"],
        description="User account status updated.",
    )

    # ======================================================
    # SUCCESS MESSAGE
    # ======================================================

    if new_status:

        flash(
            "User account activated successfully.",
            "success",
        )

    else:

        flash(
            "User account deactivated successfully.",
            "success",
        )


    # ======================================================
    # RETURN TO USER ADMINISTRATION
    # ======================================================

    return redirect(
        url_for("admin_users")
    )


# ==========================================================
# ADMINISTRATION - RESET USER PASSWORD
# ==========================================================

@app.route(
    "/admin/users/<int:user_id>/reset-password",
    methods=["GET", "POST"],
)
@permission_required("users.manage")
def reset_admin_user_password(user_id):

    user = get_user_by_id(
        user_id
    )

    if not user:

        flash(
            "User account not found.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    if request.method == "POST":

        # ==================================================
        # FORM INPUT
        # ==========================================================

        password = request.form.get(
            "password",
            "",
        )

        confirm_password = request.form.get(
            "confirm_password",
            "",
        )


        # ==================================================
        # VALIDATION
        # ==========================================================

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "danger",
            )

            return render_template(
                "admin/users/reset_password.html",
                user=user,
            )


        if password != confirm_password:

            flash(
                "Password confirmation does not match.",
                "danger",
            )

            return render_template(
                "admin/users/reset_password.html",
                user=user,
            )


        # ==================================================
        # HASH NEW PASSWORD
        # ==========================================================

        password_hash = (
            generate_password_hash(
                password
            )
        )


        # ==================================================
        # DATABASE UPDATE
        # ==========================================================

        update_user_password(
            user_id,
            password_hash,
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="ADMINISTRATION",
            action="RESET_PASSWORD",
            entity_type="USER",
            entity_id=user["username"],
            description="User password reset.",
        )

        flash(
            (
                f"Password for {user['username']} "
                "was reset successfully."
            ),
            "success",
        )


        return redirect(
            url_for("admin_users")
        )


    return render_template(
        "admin/users/reset_password.html",
        user=user,
    )

    # ==========================================================
# ADMINISTRATION - ROLES
# ==========================================================

@app.route("/admin/roles")
@permission_required("roles.manage")
def admin_roles():

    roles = get_all_roles()

    return render_template(
        "admin/roles/index.html",
        roles=roles,
    )


# ==========================================================
# ADMINISTRATION - MANAGE ROLE PERMISSIONS
# ==========================================================

@app.route(
    "/admin/roles/<int:role_id>/permissions",
    methods=["GET", "POST"],
)
@permission_required("roles.manage")
def admin_role_permissions(role_id):

    role = get_role_by_id(
        role_id
    )

    if not role:

        flash(
            "Role not found.",
            "danger",
        )

        return redirect(
            url_for("admin_roles")
        )


    # ======================================================
    # SUPER ADMIN PROTECTION
    # ======================================================

    if role["role_name"] == "Super Admin":

        flash(
            (
                "Super Admin permissions are protected "
                "and cannot be changed here."
            ),
            "warning",
        )

        return redirect(
            url_for("admin_roles")
        )


    permissions = (
        get_all_permissions()
    )


    if request.method == "POST":

        # ==================================================
        # SELECTED PERMISSIONS
        # ==========================================================

        selected_values = (
            request.form.getlist(
                "permission_ids"
            )
        )


        selected_permission_ids = set()

        try:

            for permission_id in selected_values:

                selected_permission_ids.add(
                    int(permission_id)
                )

        except ValueError:

            flash(
                "Invalid permission selection.",
                "danger",
            )

            return redirect(
                url_for(
                    "admin_role_permissions",
                    role_id=role_id,
                )
            )


        # ==================================================
        # VERIFY PERMISSIONS
        # ==========================================================

        valid_permission_ids = {
            permission["permission_id"]
            for permission in permissions
        }


        if not selected_permission_ids.issubset(
            valid_permission_ids
        ):

            flash(
                "One or more selected permissions are invalid.",
                "danger",
            )

            return redirect(
                url_for(
                    "admin_role_permissions",
                    role_id=role_id,
                )
            )


        # ==================================================
        # UPDATE DATABASE
        # ==========================================================

        update_role_permissions(
            role_id,
            selected_permission_ids,
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="ADMINISTRATION",
            action="UPDATE_PERMISSIONS",
            entity_type="ROLE",
            entity_id=role["role_name"],
            description="Role permissions updated.",
        )

        flash(
            (
                f"Permissions for "
                f"{role['role_name']} updated successfully."
            ),
            "success",
        )


        return redirect(
            url_for("admin_roles")
        )


    selected_permission_ids = (
        get_role_permission_ids(
            role_id
        )
    )


    return render_template(
        "admin/roles/permissions.html",
        role=role,
        permissions=permissions,
        selected_permission_ids=selected_permission_ids,
    )

    # ======================================================
    # DO NOT DEACTIVATE YOUR OWN ACCOUNT
    # ======================================================

    if user_id == session["user_id"]:

        flash(
            "You cannot deactivate your own account.",
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    new_status = not bool(
        user["is_active"]
    )


    # ======================================================
    # PROTECT LAST ACTIVE SUPER ADMIN
    # ======================================================

    if (
        not new_status
        and user["role_name"] == "Super Admin"
        and count_active_super_admins() <= 1
    ):

        flash(
            (
                "You cannot deactivate the "
                "last active Super Admin."
            ),
            "danger",
        )

        return redirect(
            url_for("admin_users")
        )


    set_user_active_status(
        user_id,
        new_status,
    )


    if new_status:

        flash(
            "User account activated successfully.",
            "success",
        )

    else:

        flash(
            "User account deactivated successfully.",
            "success",
        )


    return redirect(
        url_for("admin_users")
    )
# ==========================================================
# PAYROLL - CALCULATE MONTHLY PAYROLL
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/calculate-monthly",
    methods=["POST"],
)
@permission_required("payroll.process")
def calculate_monthly_payroll_route(
    payroll_period_id,
):

    period = get_payroll_period_by_id(
        payroll_period_id
    )


    if not period:

        flash(
            "Payroll period not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    if period["status"] != "DRAFT":

        flash(
            (
                "Payroll can only be calculated "
                "while the period is in Draft status."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_period",
                payroll_period_id=payroll_period_id,
            )
        )


    try:

        result = (
            calculate_monthly_payroll_period(
                payroll_period_id=payroll_period_id,
                calculated_by=session["user_id"],
            )
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_period",
                payroll_period_id=payroll_period_id,
            )
        )


    # ======================================================
    # RESULT MESSAGE
    # ==========================================================

    if result["unrecorded_days"] > 0:

        flash(
            (
                f"{result['calculated_count']} monthly "
                "payroll entries calculated. "
                f"{result['unrecorded_days']} scheduled "
                "attendance day(s) are still unrecorded. "
                "No deduction was assumed for those dates."
            ),
            "warning",
        )

    else:

        flash(
            (
                f"{result['calculated_count']} monthly "
                "payroll entries calculated successfully."
            ),
            "success",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )

# ==========================================================
# PAYROLL - MARK AS PAID
# ==========================================================

@app.route(
    "/payroll/periods/<int:payroll_period_id>/paid",
    methods=["POST"],
)
@permission_required("payroll.pay")
def mark_payroll_period_as_paid_route(
    payroll_period_id,
):

    try:

        result = (
            mark_payroll_period_as_paid(
                payroll_period_id=payroll_period_id,
                paid_by=session["user_id"],
            )
        )


        # AUDIT LOG: The business action has committed successfully.
        record_audit_event(
            module="PAYROLL",
            action="MARK_PAID",
            entity_type="PAYROLL_PERIOD",
            entity_id=payroll_period_id,
            description="Payroll period marked as paid.",
            entity_lookup=get_payroll_period_by_id,
            identifier_key="period_number",
        )

        flash(
            (
                "Payroll marked as paid successfully. "
                f"{result['total_entries']} payroll "
                "entry/entries are now paid."
            ),
            "success",
        )


    except ValueError as error:

        flash(
            str(error),
            "danger",
        )


    return redirect(
        url_for(
            "view_payroll_period",
            payroll_period_id=payroll_period_id,
        )
    )

# ==========================================================
# PAYROLL - PAYSLIP
# ==========================================================

@app.route(
    "/payroll/entries/<int:payroll_entry_id>/payslip"
)
@permission_required("payroll.view")
def payroll_payslip(
    payroll_entry_id,
):

    entry = get_payroll_entry_by_id(
        payroll_entry_id
    )


    if not entry:

        flash(
            "Payroll entry not found.",
            "danger",
        )

        return redirect(
            url_for(
                "payroll_periods"
            )
        )


    # ======================================================
    # PAYSLIP ONLY AFTER PAYMENT
    # ==========================================================

    if entry["period_status"] != "PAID":

        flash(
            (
                "Payslip is available only after "
                "the payroll period has been marked as paid."
            ),
            "danger",
        )

        return redirect(
            url_for(
                "view_payroll_entry",
                payroll_entry_id=payroll_entry_id,
            )
        )


    adjustments = (
        get_payroll_adjustments(
            payroll_entry_id
        )
    )


    adjustment_totals = (
        get_payroll_adjustment_totals(
            payroll_entry_id
        )
    )


    return render_template(
        "payroll/payslips/view.html",
        entry=entry,
        adjustments=adjustments,
        adjustment_totals=adjustment_totals,
    )

# ==========================================================
# ADMIN - AUDIT LOGS
# ==========================================================

@app.route("/admin/audit-logs")
@permission_required("audit_logs.view")
def audit_logs():

    # ======================================================
    # FILTER INPUT
    # ==========================================================

    search_text = request.args.get(
        "search",
        "",
    ).strip()


    selected_module = request.args.get(
        "module",
        "",
    ).strip().upper()


    selected_action = request.args.get(
        "action",
        "",
    ).strip().upper()


    start_date_text = request.args.get(
        "start_date",
        "",
    ).strip()


    end_date_text = request.args.get(
        "end_date",
        "",
    ).strip()


    # ======================================================
    # DATE VALIDATION
    # ==========================================================

    start_date_value = None

    end_date_value = None


    if start_date_text:

        try:

            start_date_value = (
                date.fromisoformat(
                    start_date_text
                )
            )

        except ValueError:

            start_date_text = ""


    if end_date_text:

        try:

            end_date_value = (
                date.fromisoformat(
                    end_date_text
                )
            )

        except ValueError:

            end_date_text = ""


    if (
        start_date_value
        and end_date_value
        and start_date_value
        > end_date_value
    ):

        flash(
            (
                "Audit log start date cannot "
                "be later than end date."
            ),
            "danger",
        )

        start_date_value = None
        end_date_value = None

        start_date_text = ""
        end_date_text = ""


    # ======================================================
    # DATA
    # ==========================================================

    logs = get_filtered_audit_logs(
        search_text=search_text or None,
        module=selected_module or None,
        action=selected_action or None,
        start_date=start_date_value,
        end_date=end_date_value,
    )


    filter_options = (
        get_audit_log_filter_options()
    )


    return render_template(
        "admin/audit_logs/index.html",
        logs=logs,
        modules=filter_options["modules"],
        actions=filter_options["actions"],
        search_text=search_text,
        selected_module=selected_module,
        selected_action=selected_action,
        start_date=start_date_text,
        end_date=end_date_text,
    )

# ==========================================================
# LOGOUT
# ==========================================================

@app.route("/logout", methods=["GET", "POST"])
def logout():
    if request.method == "GET":
        return render_template("security/logout.html")
    if not authenticated():
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    # ======================================================
    # AUDIT BEFORE CLEARING SESSION
    # ==========================================================

    record_audit_event(
        module="AUTH",
        action="LOGOUT",
        entity_type="USER",
        entity_id=session.get("user_id"),
        description=(
            "User logged out."
        ),
    )


    session.clear()


    flash(
        "You have been logged out.",
        "success",
    )


    return redirect(
        url_for("login")
    )



if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"])