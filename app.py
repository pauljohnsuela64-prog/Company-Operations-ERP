import os
from functools import wraps

from datetime import (
    date,
    datetime,
)

from dotenv import load_dotenv
from dashboard_repository import get_dashboard_summary

from decimal import Decimal, InvalidOperation


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
    get_stock_movements,
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

secret_key = os.getenv("SECRET_KEY")

if not secret_key:
    raise RuntimeError("SECRET_KEY is missing from the environment.")

app.secret_key = secret_key


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view

def permission_required(permission_code):
    def decorator(view_function):
        @wraps(view_function)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))

            if permission_code not in session.get("permissions", []):
                flash(
                    "You do not have permission to access that page.",
                    "danger",
                )
                return redirect(url_for("dashboard"))

            return view_function(*args, **kwargs)

        return wrapped_view

    return decorator


def has_permission(permission_code):
    return permission_code in session.get("permissions", [])


@app.context_processor
def inject_permission_helper():
    return {
        "has_permission": has_permission,
    }


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
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

        permissions = get_permissions_by_role_id(user["role_id"])

        session.clear()

        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role_id"] = user["role_id"]
        session["role_name"] = user["role_name"]
        session["permissions"] = permissions

        update_last_login(user["user_id"])

        flash("Login successful.", "success")

        return redirect(url_for("dashboard"))

    return render_template("login.html")


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
            create_inventory_category(
                category_code,
                category_name,
                description or None,
            )

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

    set_inventory_category_active_status(
        category_id,
        new_status,
    )

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
            create_warehouse(
                warehouse_code,
                warehouse_name,
                location or None,
            )

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

    set_warehouse_active_status(
        warehouse_id,
        new_status,
    )

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
            reorder_level_value = float(reorder_level)

            if reorder_level_value < 0:
                raise ValueError

        except ValueError:
            flash(
                "Reorder level must be zero or greater.",
                "danger",
            )

            return render_template(
                "inventory/items/add.html",
                categories=categories,
            )

        try:
            create_inventory_item(
                item_code,
                item_name,
                int(category_id) if category_id else None,
                description or None,
                unit_of_measure,
                reorder_level_value,
            )

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

    categories = get_all_inventory_categories()

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
            reorder_level_value = float(reorder_level)

            if reorder_level_value < 0:
                raise ValueError

        except ValueError:
            flash(
                "Reorder level must be zero or greater.",
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
                int(category_id) if category_id else None,
                description or None,
                unit_of_measure,
                reorder_level_value,
            )

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

    set_inventory_item_active_status(
        item_id,
        new_status,
    )

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

@app.route(
    "/inventory/stock/in",
    methods=["GET", "POST"],
)
@permission_required("inventory.stock.manage")
def inventory_stock_in():
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
            )

        try:
            item_id_value = int(item_id)
            warehouse_id_value = int(warehouse_id)
            quantity_value = float(quantity)

            if quantity_value <= 0:
                raise ValueError

        except ValueError:
            flash(
                "Quantity must be greater than zero.",
                "danger",
            )

            return render_template(
                "inventory/stock/in.html",
                items=active_items,
                warehouses=active_warehouses,
            )

        item = get_inventory_item_by_id(
            item_id_value
        )

        warehouse = get_warehouse_by_id(
            warehouse_id_value
        )

        if not item or not item["is_active"]:
            flash(
                "Selected inventory item is invalid or inactive.",
                "danger",
            )
            return redirect(url_for("inventory_stock_in"))

        if not warehouse or not warehouse["is_active"]:
            flash(
                "Selected warehouse is invalid or inactive.",
                "danger",
            )
            return redirect(url_for("inventory_stock_in"))

        stock_in(
            item_id_value,
            warehouse_id_value,
            quantity_value,
            notes or None,
            session["user_id"],
        )

        flash(
            "Stock added successfully.",
            "success",
        )

        return redirect(url_for("inventory_stock"))

    return render_template(
        "inventory/stock/in.html",
        items=active_items,
        warehouses=active_warehouses,
    )


@app.route(
    "/inventory/stock/out",
    methods=["GET", "POST"],
)
@permission_required("inventory.stock.manage")
def inventory_stock_out():
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
            item_id_value = int(item_id)
            warehouse_id_value = int(warehouse_id)
            quantity_value = float(quantity)

            if quantity_value <= 0:
                raise ValueError

        except ValueError:
            flash(
                "Item, warehouse, and a quantity greater than zero are required.",
                "danger",
            )

            return render_template(
                "inventory/stock/out.html",
                items=active_items,
                warehouses=active_warehouses,
            )

        try:
            stock_out(
                item_id_value,
                warehouse_id_value,
                quantity_value,
                notes or None,
                session["user_id"],
            )

        except ValueError as error:
            flash(str(error), "danger")

            return render_template(
                "inventory/stock/out.html",
                items=active_items,
                warehouses=active_warehouses,
            )

        flash(
            "Stock removed successfully.",
            "success",
        )

        return redirect(url_for("inventory_stock"))

    return render_template(
        "inventory/stock/out.html",
        items=active_items,
        warehouses=active_warehouses,
    )


@app.route("/inventory/stock/movements")
@permission_required("inventory.view")
def stock_movement_history():
    movements = get_stock_movements()

    return render_template(
        "inventory/stock/movements.html",
        movements=movements,
    )


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
            create_supplier(
                supplier_code,
                supplier_name,
                contact_person or None,
                email or None,
                phone or None,
                address or None,
            )

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

        request_id, request_number = (
            create_purchase_request(
                session["user_id"],
                department_id_value,
                purpose,
            )
        )

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

    return render_template(
        "procurement/requests/view.html",
        purchase_request=purchase_request,
        items=items,
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
            quantity_value = float(quantity)

            if quantity_value <= 0:
                raise ValueError

        except ValueError:
            flash(
                "Quantity must be greater than zero.",
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
                cost_value = float(estimated_unit_cost)

                if cost_value < 0:
                    raise ValueError

            except ValueError:
                flash(
                    "Estimated unit cost must be zero or greater.",
                    "danger",
                )

                return render_template(
                    "procurement/requests/add_item.html",
                    purchase_request=purchase_request,
                    inventory_items=inventory_items,
                )

        add_purchase_request_item(
            request_id,
            item_id_value,
            quantity_value,
            cost_value,
            notes or None,
        )

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
            quantity_value = float(quantity)

            if quantity_value <= 0:
                raise ValueError

        except ValueError:
            flash(
                "Quantity must be greater than zero.",
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
                cost_value = float(
                    estimated_unit_cost
                )

                if cost_value < 0:
                    raise ValueError

            except ValueError:
                flash(
                    "Estimated unit cost must be zero or greater.",
                    "danger",
                )

                return render_template(
                    "procurement/requests/edit_item.html",
                    purchase_request=purchase_request,
                    request_item=request_item,
                    inventory_items=inventory_items,
                )

        update_purchase_request_item(
            request_item_id,
            item_id_value,
            quantity_value,
            cost_value,
            notes or None,
        )

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

    delete_purchase_request_item(
        request_item_id
    )

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

        rejected = reject_purchase_request(
            request_id,
            rejection_reason,
        )

        if rejected:
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

    receipts = get_goods_receipts_by_purchase_order(
    purchase_order_id
)

    return render_template(
        "procurement/orders/view.html",
        purchase_order=purchase_order,
        items=items,
        receipts=receipts,
    )


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
            unit_cost_value = float(unit_cost)

            if unit_cost_value < 0:
                raise ValueError

        except ValueError:
            flash(
                "Unit cost must be zero or greater.",
                "danger",
            )

            return render_template(
                "procurement/orders/edit_cost.html",
                purchase_order=purchase_order,
                purchase_order_item=purchase_order_item,
            )

        update_purchase_order_item_cost(
            purchase_order_item_id,
            unit_cost_value,
        )

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
        flash(
            "Purchase order sent successfully.",
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

    purchase_order = get_receivable_purchase_order_by_id(
        purchase_order_id
    )

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

        for item in items:

            purchase_order_item_id = item[
                "purchase_order_item_id"
            ]

            field_name = (
                f"quantity_received_"
                f"{purchase_order_item_id}"
            )

            quantity = request.form.get(
                field_name,
                "0",
            ).strip()

            received_items[
                purchase_order_item_id
            ] = quantity


        # ==================================================
        # CREATE GOODS RECEIPT
        #
        # This function also:
        # - updates Inventory stock
        # - creates Stock Movement history
        # - updates PO status
        # ==================================================

        try:

            (
                receipt_id,
                receipt_number,
                new_status,
            ) = create_goods_receipt(
                purchase_order_id=purchase_order_id,
                warehouse_id=warehouse_id_value,
                received_by=session["user_id"],
                received_items=received_items,
                notes=notes or None,
            )

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
            )


        # ==================================================
        # SUCCESS
        # ==================================================

        flash(
            f"Goods receipt {receipt_number} saved successfully.",
            "success",
        )

        return redirect(
            url_for("goods_receipts")
        )


    # ======================================================
    # DISPLAY FORM
    # ======================================================

    return render_template(
        "procurement/receipts/receive.html",
        purchase_order=purchase_order,
        items=items,
        warehouses=warehouses,
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
# IT MANAGEMENT - ADD ASSET
# ==========================================================

@app.route(
    "/it/assets/add",
    methods=["GET", "POST"],
)
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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
@permission_required("it_assets.view")
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

@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))




if __name__ == "__main__":
    app.run(debug=True)