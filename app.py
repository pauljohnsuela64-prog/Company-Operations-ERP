import os
from functools import wraps

from dotenv import load_dotenv
from datetime import date
from dashboard_repository import get_dashboard_summary

from decimal import Decimal, InvalidOperation


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
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from user_repository import (
    get_permissions_by_role_id,
    get_user_by_username,
    update_last_login,
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
    # GET EXPENSE RECORDS
    # ======================================================

    expense_list = get_all_expenses()

    return render_template(
        "finance/expenses/index.html",
        expenses=expense_list,
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
    # SHOW EXPENSE DETAILS
    # ======================================================

    return render_template(
        "finance/expenses/view.html",
        expense=expense,
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




@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))



if __name__ == "__main__":
    app.run(debug=True)