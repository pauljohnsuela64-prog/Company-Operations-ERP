import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from user_repository import get_user_by_username, update_last_login


load_dotenv()

app = Flask(__name__)

secret_key = os.getenv("SECRET_KEY")

if not secret_key:
    raise RuntimeError("SECRET_KEY is missing from the environment.")

app.secret_key = secret_key


@app.route("/", methods=["GET"])
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

        session.clear()

        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role_id"] = user["role_id"]
        session["role_name"] = user["role_name"]

        update_last_login(user["user_id"])

        flash("Login successful.", "success")

        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    return render_template("dashboard.html")


@app.route("/logout")
def logout():
    session.clear()

    flash("You have been logged out.", "success")

    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)