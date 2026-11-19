import re
import secrets

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query
from utils import login_required

bp = Blueprint("auth", __name__)

ROLE_HOME = {"seeker": "seeker.dashboard", "recruiter": "recruiter.dashboard", "admin": "admin.dashboard"}
# role -> (table, id column, login column, display-name column)
LOGIN = {
    "seeker": ("job_seekers", "seeker_id", "email", "full_name"),
    "recruiter": ("recruiters", "recruiter_id", "email", "full_name"),
    "admin": ("admin", "admin_id", "username", "username"),
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/")
def index():
    jobs = query("""SELECT j.*, c.name AS company FROM jobs j JOIN companies c ON c.company_id = j.company_id
                    WHERE j.status='Open' AND (j.deadline IS NULL OR j.deadline >= CURDATE())
                    ORDER BY j.created_at DESC LIMIT 6""")
    stats = {
        "jobs": query("SELECT COUNT(*) c FROM jobs WHERE status='Open'", one=True)["c"],
        "companies": query("SELECT COUNT(*) c FROM companies", one=True)["c"],
        "seekers": query("SELECT COUNT(*) c FROM job_seekers", one=True)["c"],
    }
    return render_template("index.html", jobs=jobs, stats=stats)


@bp.route("/register/admin", methods=["GET", "POST"])
def register_admin():
    """Create an admin account. Needs the secret admin key so strangers can't make admins."""
    if request.method == "POST":
        f = request.form
        username = f.get("username", "").strip()
        email = f.get("email", "").strip().lower()
        pw = f.get("password", "")
        key = f.get("admin_key", "")
        error = None
        if not secrets.compare_digest(key.encode(), current_app.config["ADMIN_SECRET_KEY"].encode()):
            error = "Wrong admin key."
        elif len(username) < 3:
            error = "Username must be at least 3 characters."
        elif not EMAIL_RE.match(email):
            error = "Enter a valid email address."
        elif len(pw) < 6:
            error = "Password must be at least 6 characters."
        elif pw != f.get("confirm", ""):
            error = "Passwords do not match."
        elif query("SELECT 1 FROM admin WHERE username=%s OR email=%s", (username, email), one=True):
            error = "An admin with this username or email already exists."
        if error:
            flash(error, "danger")
        else:
            execute("INSERT INTO admin (username, email, password_hash) VALUES (%s,%s,%s)",
                    (username, email, generate_password_hash(pw)))
            flash("Admin account created. Log in with the Admin tab.", "success")
            return redirect(url_for("auth.login", role="admin"))
    return render_template("register_admin.html")


@bp.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("seeker", "recruiter"):
        abort(404)
    table = "job_seekers" if role == "seeker" else "recruiters"
    if request.method == "POST":
        f = request.form
        name = f.get("full_name", "").strip()
        email = f.get("email", "").strip().lower()
        phone = f.get("phone", "").strip()
        pw = f.get("password", "")
        error = None
        if not name:
            error = "Enter your full name."
        elif not EMAIL_RE.match(email):
            error = "Enter a valid email address."
        elif len(pw) < 6:
            error = "Password must be at least 6 characters."
        elif pw != f.get("confirm", ""):
            error = "Passwords do not match."
        elif query(f"SELECT 1 FROM {table} WHERE email=%s", (email,), one=True):
            error = "An account with this email already exists. Try logging in."
        if error:
            flash(error, "danger")
        else:
            execute(f"INSERT INTO {table} (full_name, email, password_hash, phone) VALUES (%s,%s,%s,%s)",
                    (name, email, generate_password_hash(pw), phone))
            flash("Account created. Log in to continue.", "success")
            return redirect(url_for("auth.login", role=role))
    return render_template("register.html", role=role)


@bp.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role", "seeker")
    if role not in LOGIN:
        role = "seeker"
    if request.method == "POST":
        role = request.form.get("role", "")
        if role not in LOGIN:
            abort(400)
        table, id_col, login_col, name_col = LOGIN[role]
        ident = request.form.get("identifier", "").strip()
        if login_col == "email":
            ident = ident.lower()
        if role == "admin":
            user = query("SELECT * FROM admin WHERE username=%s OR email=%s", (ident, ident.lower()), one=True)
        else:
            user = query(f"SELECT * FROM {table} WHERE {login_col}=%s", (ident,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            if not user.get("is_active", 1):
                flash("This account has been deactivated. Contact the administrator.", "danger")
            else:
                session.clear()
                session.update(role=role, user_id=user[id_col], name=user[name_col])
                return redirect(url_for(ROLE_HOME[role]))
        else:
            flash("Incorrect email/username or password.", "danger")
    return render_template("login.html", role=role)


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.index"))


@bp.route("/notifications")
def notifications():
    role = session.get("role")
    if role not in ("seeker", "recruiter"):
        return redirect(url_for("auth.login"))
    rows = query("""SELECT * FROM notifications WHERE user_type=%s AND user_id=%s
                    ORDER BY created_at DESC, notification_id DESC LIMIT 100""", (role, session["user_id"]))
    execute("UPDATE notifications SET is_read=1 WHERE user_type=%s AND user_id=%s", (role, session["user_id"]))
    return render_template("notifications.html", rows=rows)
