import os
from datetime import datetime

from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)

from db import execute, query
from utils import (INTERVIEW_MODES, INTERVIEW_STATUSES, JOB_TYPES, STATUSES, login_required,
                   notify_user, paginate, safe_redirect)

bp = Blueprint("recruiter", __name__, url_prefix="/recruiter")


# ---------- helpers ----------
def company_id():
    r = query("SELECT company_id FROM recruiters WHERE recruiter_id=%s", (session["user_id"],), one=True)
    return r["company_id"] if r else None


def own_job(job_id):
    job = query("SELECT * FROM jobs WHERE job_id=%s AND recruiter_id=%s", (job_id, session["user_id"]), one=True)
    if not job:
        abort(404)
    return job


def own_application(app_id):
    a = query("""SELECT a.*, j.title, j.recruiter_id, s.full_name, s.email, s.phone, s.location, s.skills,
                        s.education, s.experience_years, s.about, r.filename, r.original_name
                 FROM applications a JOIN jobs j ON j.job_id=a.job_id
                 JOIN job_seekers s ON s.seeker_id=a.seeker_id
                 LEFT JOIN resumes r ON r.resume_id=a.resume_id
                 WHERE a.application_id=%s AND j.recruiter_id=%s""", (app_id, session["user_id"]), one=True)
    if not a:
        abort(404)
    return a


def own_interview(iid):
    i = query("""SELECT i.*, a.application_id, a.seeker_id, j.title, s.full_name
                 FROM interviews i JOIN applications a ON a.application_id=i.application_id
                 JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
                 WHERE i.interview_id=%s AND j.recruiter_id=%s""", (iid, session["user_id"]), one=True)
    if not i:
        abort(404)
    return i


def require_company():
    if not company_id():
        flash("Create your company profile before posting jobs.", "warning")
        return redirect(url_for("recruiter.company"))
    return None


# ---------- dashboard & analytics ----------
@bp.route("/dashboard")
@login_required("recruiter")
def dashboard():
    rid = session["user_id"]
    if not company_id():
        flash("Start by creating your company profile.", "info")
        return redirect(url_for("recruiter.company"))
    jobs = query("SELECT COUNT(*) total, COALESCE(SUM(status='Open'),0) open_jobs FROM jobs WHERE recruiter_id=%s",
                 (rid,), one=True)
    by_status = {r["status"]: r["c"] for r in query(
        """SELECT a.status, COUNT(*) c FROM applications a JOIN jobs j ON j.job_id=a.job_id
           WHERE j.recruiter_id=%s GROUP BY a.status""", (rid,))}
    per_job = query("""SELECT j.title, COUNT(a.application_id) c FROM jobs j
                       LEFT JOIN applications a ON a.job_id=j.job_id WHERE j.recruiter_id=%s
                       GROUP BY j.job_id, j.title ORDER BY c DESC LIMIT 6""", (rid,))
    upcoming = query("""SELECT i.*, j.title, s.full_name FROM interviews i
                        JOIN applications a ON a.application_id=i.application_id
                        JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
                        WHERE j.recruiter_id=%s AND i.status IN ('Scheduled','Rescheduled')
                          AND TIMESTAMP(i.interview_date, i.interview_time) >= NOW()
                        ORDER BY i.interview_date, i.interview_time LIMIT 5""", (rid,))
    recent = query("""SELECT a.*, j.title, s.full_name FROM applications a JOIN jobs j ON j.job_id=a.job_id
                      JOIN job_seekers s ON s.seeker_id=a.seeker_id WHERE j.recruiter_id=%s
                      ORDER BY a.applied_at DESC LIMIT 6""", (rid,))
    stats = {"jobs": int(jobs["total"]), "open": int(jobs["open_jobs"]),
             "applications": sum(by_status.values()), "shortlisted": by_status.get("Shortlisted", 0),
             "selected": by_status.get("Selected", 0), "interviews": len(upcoming)}
    chart = {"status_labels": STATUSES, "status_values": [by_status.get(s, 0) for s in STATUSES],
             "job_labels": [r["title"] for r in per_job], "job_values": [r["c"] for r in per_job]}
    return render_template("recruiter/dashboard.html", stats=stats, chart=chart, upcoming=upcoming, recent=recent)


# ---------- company profile ----------
@bp.route("/company", methods=["GET", "POST"])
@login_required("recruiter")
def company():
    cid = company_id()
    if request.method == "POST":
        f = request.form
        name = f.get("name", "").strip()
        if not name:
            flash("Company name is required.", "danger")
        else:
            vals = (name, f.get("industry", "").strip(), f.get("website", "").strip(),
                    f.get("location", "").strip(), f.get("description", "").strip())
            if cid:
                execute("UPDATE companies SET name=%s, industry=%s, website=%s, location=%s, description=%s "
                        "WHERE company_id=%s", vals + (cid,))
            else:
                new_id = execute("INSERT INTO companies (name, industry, website, location, description) "
                                 "VALUES (%s,%s,%s,%s,%s)", vals)
                execute("UPDATE recruiters SET company_id=%s WHERE recruiter_id=%s", (new_id, session["user_id"]))
            flash("Company profile saved.", "success")
            return redirect(url_for("recruiter.dashboard") if not cid else url_for("recruiter.company"))
    comp = query("SELECT * FROM companies WHERE company_id=%s", (cid,), one=True) if cid else None
    return render_template("recruiter/company.html", comp=comp)


# ---------- job postings ----------
@bp.route("/jobs")
@login_required("recruiter")
def jobs():
    resp = require_company()
    if resp:
        return resp
    page = request.args.get("page", 1, type=int)
    rows, pager = paginate("""SELECT j.*, (SELECT COUNT(*) FROM applications a WHERE a.job_id=j.job_id) AS applicants
                              FROM jobs j WHERE j.recruiter_id=%s ORDER BY j.created_at DESC""",
                           "SELECT COUNT(*) c FROM jobs WHERE recruiter_id=%s", [session["user_id"]], page)
    return render_template("recruiter/jobs.html", rows=rows, pager=pager)


def _read_job_form(f):
    def num(key):
        try:
            v = float(f.get(key, "") or 0)
            return v if v > 0 else None
        except ValueError:
            return None
    title, desc, loc = f.get("title", "").strip(), f.get("description", "").strip(), f.get("location", "").strip()
    if not (title and desc and loc):
        return None, "Title, location and description are required."
    jt = f.get("job_type") if f.get("job_type") in JOB_TYPES else "Full-time"
    lo, hi = num("salary_min"), num("salary_max")
    if lo and hi and lo > hi:
        return None, "Minimum salary can't be higher than maximum salary."
    deadline = f.get("deadline") or None
    if deadline:
        try:
            datetime.strptime(deadline, "%Y-%m-%d")
        except ValueError:
            return None, "Enter a valid deadline date."
    vac = min(max(f.get("vacancies", 1, type=int), 1), 1000)
    status = "Closed" if f.get("status") == "Closed" else "Open"
    return (title, desc, f.get("skills_required", "").strip(), loc, jt, lo, hi, vac, deadline, status), None


@bp.route("/jobs/new", methods=["GET", "POST"])
@login_required("recruiter")
def job_new():
    resp = require_company()
    if resp:
        return resp
    if request.method == "POST":
        vals, err = _read_job_form(request.form)
        if err:
            flash(err, "danger")
        else:
            execute("""INSERT INTO jobs (recruiter_id, company_id, title, description, skills_required, location,
                       job_type, salary_min, salary_max, vacancies, deadline, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (session["user_id"], company_id()) + vals)
            flash("Job posted.", "success")
            return redirect(url_for("recruiter.jobs"))
    return render_template("recruiter/job_form.html", job=request.form if request.method == "POST" else None)


@bp.route("/jobs/<int:job_id>/edit", methods=["GET", "POST"])
@login_required("recruiter")
def job_edit(job_id):
    job = own_job(job_id)
    if request.method == "POST":
        vals, err = _read_job_form(request.form)
        if err:
            flash(err, "danger")
            job = request.form
        else:
            execute("""UPDATE jobs SET title=%s, description=%s, skills_required=%s, location=%s, job_type=%s,
                       salary_min=%s, salary_max=%s, vacancies=%s, deadline=%s, status=%s WHERE job_id=%s""",
                    vals + (job_id,))
            flash("Job updated.", "success")
            return redirect(url_for("recruiter.jobs"))
    return render_template("recruiter/job_form.html", job=job, editing=True, job_id=job_id)


@bp.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required("recruiter")
def job_delete(job_id):
    own_job(job_id)
    execute("DELETE FROM jobs WHERE job_id=%s", (job_id,))
    flash("Job and its applications were deleted.", "success")
    return redirect(url_for("recruiter.jobs"))


# ---------- applications ----------
@bp.route("/applications")
@login_required("recruiter")
def applications():
    page = request.args.get("page", 1, type=int)
    job_id = request.args.get("job_id", type=int)
    status = request.args.get("status", "")
    where, args = ["j.recruiter_id=%s"], [session["user_id"]]
    if job_id:
        where.append("j.job_id=%s")
        args.append(job_id)
    if status in STATUSES:
        where.append("a.status=%s")
        args.append(status)
    base = f"""FROM applications a JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
               WHERE {' AND '.join(where)}"""
    rows, pager = paginate(f"""SELECT a.*, j.title, s.full_name, s.email, s.skills, s.experience_years
                               {base} ORDER BY a.applied_at DESC""", f"SELECT COUNT(*) c {base}", args, page)
    my_jobs = query("SELECT job_id, title FROM jobs WHERE recruiter_id=%s ORDER BY title", (session["user_id"],))
    return render_template("recruiter/applications.html", rows=rows, pager=pager, my_jobs=my_jobs,
                           job_id=job_id, status=status)


@bp.route("/applications/<int:app_id>")
@login_required("recruiter")
def application_detail(app_id):
    a = own_application(app_id)
    interviews = query("SELECT * FROM interviews WHERE application_id=%s ORDER BY interview_date DESC, interview_time DESC",
                       (app_id,))
    return render_template("recruiter/application_detail.html", a=a, interviews=interviews)


@bp.route("/applications/<int:app_id>/status", methods=["POST"])
@login_required("recruiter")
def update_status(app_id):
    a = own_application(app_id)
    status = request.form.get("status")
    if status not in STATUSES:
        abort(400)
    execute("UPDATE applications SET status=%s WHERE application_id=%s", (status, app_id))
    notify_user("seeker", a["seeker_id"], f"Application update: {a['title']}",
                f"Your application for {a['title']} is now marked {status}.")
    flash(f"{a['full_name']} marked as {status}.", "success")
    return safe_redirect("recruiter.application_detail", app_id=app_id)


@bp.route("/applications/<int:app_id>/resume")
@login_required("recruiter")
def download_resume(app_id):
    a = own_application(app_id)
    if not a["filename"]:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], a["filename"],
                               as_attachment=True, download_name=a["original_name"])


# ---------- interviews ----------
def _read_interview_form(f):
    d, t = f.get("interview_date", ""), f.get("interview_time", "")
    try:
        when = datetime.strptime(f"{d} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None, "Choose a valid interview date and time."
    if when < datetime.now():
        return None, "Interview date and time must be in the future."
    mode = f.get("mode") if f.get("mode") in INTERVIEW_MODES else "Online"
    return (d, t, mode, f.get("location_link", "").strip()[:255], f.get("details", "").strip()), None


@bp.route("/interviews/new")
@login_required("recruiter")
def interview_pick():
    """Choose which candidate to schedule an interview for."""
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    where, args = ["j.recruiter_id=%s", "a.status <> 'Rejected'"], [session["user_id"]]
    if q:
        where.append("(s.full_name LIKE %s OR j.title LIKE %s)")
        args += [f"%{q}%"] * 2
    base = f"""FROM applications a JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
               WHERE {' AND '.join(where)}"""
    rows, pager = paginate(f"""SELECT a.application_id, a.status, a.applied_at, j.title, s.full_name, s.email,
                               (SELECT COUNT(*) FROM interviews i WHERE i.application_id=a.application_id
                                  AND i.status IN ('Scheduled','Rescheduled')) AS pending
                               {base} ORDER BY (a.status='Shortlisted') DESC, a.applied_at DESC""",
                           f"SELECT COUNT(*) c {base}", args, page)
    return render_template("recruiter/interview_pick.html", rows=rows, pager=pager, q=q)


@bp.route("/applications/<int:app_id>/interview", methods=["GET", "POST"])
@login_required("recruiter")
def schedule_interview(app_id):
    a = own_application(app_id)
    if request.method == "POST":
        vals, err = _read_interview_form(request.form)
        if err:
            flash(err, "danger")
        else:
            execute("""INSERT INTO interviews (application_id, interview_date, interview_time, mode, location_link, details)
                       VALUES (%s,%s,%s,%s,%s,%s)""", (app_id,) + vals)
            if a["status"] == "Applied":
                execute("UPDATE applications SET status='Shortlisted' WHERE application_id=%s", (app_id,))
            notify_user("seeker", a["seeker_id"], f"Interview scheduled: {a['title']}",
                        f"Your interview for {a['title']} is on {vals[0]} at {vals[1]} ({vals[2]}). "
                        f"{vals[3]}".strip())
            flash("Interview scheduled and candidate notified.", "success")
            return redirect(url_for("recruiter.interviews"))
    return render_template("recruiter/interview_form.html", a=a, interview=request.form if request.method == "POST" else None)


@bp.route("/interviews/<int:iid>/reschedule", methods=["GET", "POST"])
@login_required("recruiter")
def reschedule_interview(iid):
    i = own_interview(iid)
    if request.method == "POST":
        vals, err = _read_interview_form(request.form)
        if err:
            flash(err, "danger")
        else:
            execute("""UPDATE interviews SET interview_date=%s, interview_time=%s, mode=%s, location_link=%s,
                       details=%s, status='Rescheduled' WHERE interview_id=%s""", vals + (iid,))
            notify_user("seeker", i["seeker_id"], f"Interview rescheduled: {i['title']}",
                        f"Your interview for {i['title']} has moved to {vals[0]} at {vals[1]} ({vals[2]}).")
            flash("Interview rescheduled and candidate notified.", "success")
            return redirect(url_for("recruiter.interviews"))
    return render_template("recruiter/interview_form.html", a=i, interview=i, rescheduling=True)


@bp.route("/interviews")
@login_required("recruiter")
def interviews():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    where, args = ["j.recruiter_id=%s"], [session["user_id"]]
    if status in INTERVIEW_STATUSES:
        where.append("i.status=%s")
        args.append(status)
    base = f"""FROM interviews i JOIN applications a ON a.application_id=i.application_id
               JOIN jobs j ON j.job_id=a.job_id JOIN job_seekers s ON s.seeker_id=a.seeker_id
               WHERE {' AND '.join(where)}"""
    rows, pager = paginate(f"SELECT i.*, a.application_id, j.title, s.full_name {base} "
                           "ORDER BY i.interview_date DESC, i.interview_time DESC",
                           f"SELECT COUNT(*) c {base}", args, page)
    return render_template("recruiter/interviews.html", rows=rows, pager=pager, status=status)


@bp.route("/interviews/<int:iid>/status", methods=["POST"])
@login_required("recruiter")
def interview_status(iid):
    i = own_interview(iid)
    status = request.form.get("status")
    if status not in INTERVIEW_STATUSES:
        abort(400)
    execute("UPDATE interviews SET status=%s WHERE interview_id=%s", (status, iid))
    if status == "Cancelled":
        notify_user("seeker", i["seeker_id"], f"Interview cancelled: {i['title']}",
                    f"Your interview for {i['title']} has been cancelled.")
    flash(f"Interview marked {status}.", "success")
    return safe_redirect("recruiter.interviews")
