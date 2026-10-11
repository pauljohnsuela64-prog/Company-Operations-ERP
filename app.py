import os
from functools import wraps

from dotenv import load_dotenv
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

from department_repository import get_all_departments


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
    return render_template("dashboard.html")


@app.route("/departments")
@permission_required("departments.view")
def departments():
    department_list = get_all_departments()

    return render_template(
        "departments/index.html",
        departments=department_list,
    )


@app.route("/logout")
@login_required
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)