import os

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for

from db import execute, query
from utils import STATUSES, login_required, paginate, safe_redirect

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/dashboard")
@login_required("admin")
def dashboard():
    count = lambda sql: query(sql, one=True)["c"]
    stats = {
        "seekers": count("SELECT COUNT(*) c FROM job_seekers"),
        "recruiters": count("SELECT COUNT(*) c FROM recruiters"),
        "companies": count("SELECT COUNT(*) c FROM companies"),
        "jobs": count("SELECT COUNT(*) c FROM jobs"),
        "open_jobs": count("SELECT COUNT(*) c FROM jobs WHERE status='Open'"),
        "applications": count("SELECT COUNT(*) c FROM applications"),
        "interviews": count("SELECT COUNT(*) c FROM interviews WHERE status IN ('Scheduled','Rescheduled')"),
        "selected": count("SELECT COUNT(*) c FROM applications WHERE status='Selected'"),
    }
    by_status = {r["status"]: r["c"] for r in query("SELECT status, COUNT(*) c FROM applications GROUP BY status")}
    by_type = query("SELECT job_type, COUNT(*) c FROM jobs GROUP BY job_type ORDER BY c DESC")
    recent_apps = query("""SELECT a.*, j.title, s.full_name, c.name AS company FROM applications a
                           JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
                           JOIN companies c ON c.company_id=j.company_id ORDER BY a.applied_at DESC LIMIT 6""")
    recent_jobs = query("""SELECT j.*, c.name AS company FROM jobs j JOIN companies c ON c.company_id=j.company_id
                           ORDER BY j.created_at DESC LIMIT 6""")
    recent_interviews = query("""SELECT i.*, j.title, s.full_name FROM interviews i
                                 JOIN applications a ON a.application_id=i.application_id
                                 JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
                                 ORDER BY i.created_at DESC LIMIT 6""")
    chart = {"status_labels": STATUSES, "status_values": [by_status.get(s, 0) for s in STATUSES],
             "type_labels": [r["job_type"] for r in by_type], "type_values": [r["c"] for r in by_type]}
    return render_template("admin/dashboard.html", stats=stats, chart=chart, recent_apps=recent_apps,
                           recent_jobs=recent_jobs, recent_interviews=recent_interviews)


# ---------- users ----------
KINDS = {
    "seekers": ("job_seekers", "seeker_id", "Job seekers"),
    "recruiters": ("recruiters", "recruiter_id", "Recruiters"),
}


@bp.route("/users/<kind>")
@login_required("admin")
def users(kind):
    if kind not in KINDS:
        abort(404)
    table, id_col, title = KINDS[kind]
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    where, args = "1=1", []
    if q:
        where = "(u.full_name LIKE %s OR u.email LIKE %s)"
        args = [f"%{q}%"] * 2
    if kind == "recruiters":
        base = f"FROM recruiters u LEFT JOIN companies c ON c.company_id=u.company_id WHERE {where}"
        select = f"SELECT u.*, u.recruiter_id AS uid, c.name AS company {base} ORDER BY u.created_at DESC"
    else:
        base = f"FROM job_seekers u WHERE {where}"
        select = f"SELECT u.*, u.seeker_id AS uid {base} ORDER BY u.created_at DESC"
    rows, pager = paginate(select, f"SELECT COUNT(*) c {base}", args, page)
    return render_template("admin/users.html", rows=rows, pager=pager, kind=kind, title=title, q=q)


@bp.route("/users/<kind>/<int:uid>/toggle", methods=["POST"])
@login_required("admin")
def toggle_user(kind, uid):
    if kind not in KINDS:
        abort(404)
    table, id_col, _ = KINDS[kind]
    execute(f"UPDATE {table} SET is_active = 1 - is_active WHERE {id_col}=%s", (uid,))
    flash("Account status updated.", "success")
    return safe_redirect("admin.users", kind=kind)


@bp.route("/users/<kind>/<int:uid>/delete", methods=["POST"])
@login_required("admin")
def delete_user(kind, uid):
    if kind not in KINDS:
        abort(404)
    table, id_col, _ = KINDS[kind]
    if kind == "seekers":
        files = [r["filename"] for r in query("SELECT filename FROM resumes WHERE seeker_id=%s", (uid,))]
        execute(f"DELETE FROM {table} WHERE {id_col}=%s", (uid,))
        for fn in files:
            try:
                os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], fn))
            except OSError:
                pass
    else:
        r = query("SELECT company_id FROM recruiters WHERE recruiter_id=%s", (uid,), one=True)
        execute(f"DELETE FROM {table} WHERE {id_col}=%s", (uid,))
        if r and r["company_id"]:
            execute("""DELETE FROM companies WHERE company_id=%s
                       AND NOT EXISTS (SELECT 1 FROM recruiters WHERE company_id=%s)""",
                    (r["company_id"], r["company_id"]))
    flash("User deleted along with their related records.", "success")
    return safe_redirect("admin.users", kind=kind)


# ---------- jobs ----------
@bp.route("/jobs")
@login_required("admin")
def jobs():
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    where, args = "1=1", []
    if q:
        where = "(j.title LIKE %s OR c.name LIKE %s)"
        args = [f"%{q}%"] * 2
    base = f"FROM jobs j JOIN companies c ON c.company_id=j.company_id JOIN recruiters r ON r.recruiter_id=j.recruiter_id WHERE {where}"
    rows, pager = paginate(f"""SELECT j.*, c.name AS company, r.full_name AS recruiter,
                               (SELECT COUNT(*) FROM applications a WHERE a.job_id=j.job_id) AS applicants
                               {base} ORDER BY j.created_at DESC""", f"SELECT COUNT(*) c {base}", args, page)
    return render_template("admin/jobs.html", rows=rows, pager=pager, q=q)


@bp.route("/jobs/<int:job_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_job(job_id):
    execute("UPDATE jobs SET status = IF(status='Open','Closed','Open') WHERE job_id=%s", (job_id,))
    flash("Job status updated.", "success")
    return safe_redirect("admin.jobs")


@bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required("admin")
def delete_job(job_id):
    execute("DELETE FROM jobs WHERE job_id=%s", (job_id,))
    flash("Job deleted.", "success")
    return safe_redirect("admin.jobs")


# ---------- applications ----------
@bp.route("/applications")
@login_required("admin")
def applications():
    status = request.args.get("status", "")
    page = request.args.get("page", 1, type=int)
    where, args = "1=1", []
    if status in STATUSES:
        where, args = "a.status=%s", [status]
    base = f"""FROM applications a JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
               JOIN companies c ON c.company_id=j.company_id WHERE {where}"""
    rows, pager = paginate(f"""SELECT a.*, j.title, s.full_name, c.name AS company {base}
                               ORDER BY a.applied_at DESC""", f"SELECT COUNT(*) c {base}", args, page)
    return render_template("admin/applications.html", rows=rows, pager=pager, status=status)


@bp.route("/applications/<int:app_id>/status", methods=["POST"])
@login_required("admin")
def application_status(app_id):
    status = request.form.get("status")
    if status not in STATUSES:
        abort(400)
    execute("UPDATE applications SET status=%s WHERE application_id=%s", (status, app_id))
    flash("Application status updated.", "success")
    return safe_redirect("admin.applications")


@bp.route("/applications/<int:app_id>/delete", methods=["POST"])
@login_required("admin")
def delete_application(app_id):
    execute("DELETE FROM applications WHERE application_id=%s", (app_id,))
    flash("Application deleted.", "success")
    return safe_redirect("admin.applications")
