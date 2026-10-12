import os
from functools import wraps

from dotenv import load_dotenv

from dashboard_repository import get_dashboard_summary

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


@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)