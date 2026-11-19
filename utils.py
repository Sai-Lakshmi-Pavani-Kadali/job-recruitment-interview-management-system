import smtplib
import threading
from datetime import timedelta
from email.message import EmailMessage
from functools import wraps

from flask import abort, current_app, flash, redirect, request, session, url_for

from db import execute, query

STATUSES = ["Applied", "Shortlisted", "Rejected", "Selected"]
JOB_TYPES = ["Full-time", "Part-time", "Internship", "Contract", "Remote"]
INTERVIEW_STATUSES = ["Scheduled", "Rescheduled", "Completed", "Cancelled"]
INTERVIEW_MODES = ["Online", "In-person", "Phone"]
USER_TABLES = {"seeker": ("job_seekers", "seeker_id"), "recruiter": ("recruiters", "recruiter_id")}


def login_required(role):
    """Role-based access control for a route."""
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login", role=role))
            return f(*args, **kwargs)
        return wrapper
    return deco


def paginate(select_sql, count_sql, args, page):
    per = current_app.config["PER_PAGE"]
    total = query(count_sql, args, one=True)["c"]
    pages = max(1, -(-total // per))
    page = min(max(page, 1), pages)
    rows = query(f"{select_sql} LIMIT %s OFFSET %s", list(args) + [per, (page - 1) * per])
    return rows, {"page": page, "pages": pages, "total": total}


def safe_redirect(default_endpoint, **values):
    nxt = request.form.get("next", "")
    if nxt.startswith("/") and not nxt.startswith("//"):
        return redirect(nxt)
    return redirect(url_for(default_endpoint, **values))


def valid_pdf(file_storage):
    if not file_storage.filename.lower().endswith(".pdf"):
        return False
    head = file_storage.stream.read(4)
    file_storage.stream.seek(0)
    return head == b"%PDF"


# ---------- notifications & email ----------
def _send(app, to, subject, body):
    cfg = app.config
    if not cfg["MAIL_USERNAME"]:
        app.logger.info("[email not configured] to=%s | %s | %s", to, subject, body)
        return
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = cfg["MAIL_SENDER"], to, subject
        msg.set_content(body)
        with smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=10) as s:
            s.starttls()
            s.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            s.send_message(msg)
    except Exception as exc:  # never break a request because email failed
        app.logger.warning("Email to %s failed: %s", to, exc)


def notify_user(user_type, user_id, subject, message):
    """Create an in-app notification and send an email in the background."""
    execute("INSERT INTO notifications (user_type, user_id, message) VALUES (%s,%s,%s)",
            (user_type, user_id, message[:400]))
    table, id_col = USER_TABLES[user_type]
    user = query(f"SELECT email FROM {table} WHERE {id_col}=%s", (user_id,), one=True)
    if user:
        app = current_app._get_current_object()
        threading.Thread(target=_send, args=(app, user["email"], subject, message), daemon=True).start()


# ---------- template filters ----------
def fmt_time(v):
    if isinstance(v, timedelta):
        s = int(v.total_seconds())
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}"
    return str(v)[:5] if v is not None else ""


def fmt_date(v):
    return v.strftime("%d %b %Y") if v else ""


def fmt_dt(v):
    return v.strftime("%d %b %Y, %H:%M") if v else ""


def salary_text(job):
    lo, hi = job.get("salary_min"), job.get("salary_max")
    if lo and hi:
        return f"₹{lo:g}–{hi:g} LPA"
    if lo or hi:
        return f"₹{(lo or hi):g} LPA"
    return "Not disclosed"
