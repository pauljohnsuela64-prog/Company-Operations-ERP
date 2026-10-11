import os
from functools import wraps

from dotenv import load_dotenv

from dashboard_repository import get_dashboard_summary

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

@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)