import os
import uuid

import mysql.connector
from flask import (Blueprint, abort, current_app, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

from db import execute, query
from utils import login_required, notify_user, paginate, valid_pdf

bp = Blueprint("seeker", __name__, url_prefix="/seeker")


@bp.route("/dashboard")
@login_required("seeker")
def dashboard():
    sid = session["user_id"]
    counts = {r["status"]: r["c"] for r in query(
        "SELECT status, COUNT(*) c FROM applications WHERE seeker_id=%s GROUP BY status", (sid,))}
    recent = query("""SELECT a.*, j.title, c.name AS company FROM applications a
                      JOIN jobs j ON j.job_id=a.job_id JOIN companies c ON c.company_id=j.company_id
                      WHERE a.seeker_id=%s ORDER BY a.applied_at DESC LIMIT 5""", (sid,))
    upcoming = query("""SELECT i.*, j.title, c.name AS company FROM interviews i
                        JOIN applications a ON a.application_id=i.application_id
                        JOIN jobs j ON j.job_id=a.job_id JOIN companies c ON c.company_id=j.company_id
                        WHERE a.seeker_id=%s AND i.status IN ('Scheduled','Rescheduled')
                          AND TIMESTAMP(i.interview_date, i.interview_time) >= NOW()
                        ORDER BY i.interview_date, i.interview_time LIMIT 5""", (sid,))
    resume_count = query("SELECT COUNT(*) c FROM resumes WHERE seeker_id=%s", (sid,), one=True)["c"]
    return render_template("seeker/dashboard.html", counts=counts, total=sum(counts.values()),
                           recent=recent, upcoming=upcoming, resume_count=resume_count)


@bp.route("/profile", methods=["GET", "POST"])
@login_required("seeker")
def profile():
    sid = session["user_id"]
    if request.method == "POST":
        f = request.form
        name = f.get("full_name", "").strip()
        if not name:
            flash("Full name is required.", "danger")
        else:
            exp = min(max(f.get("experience_years", 0, type=int), 0), 60)
            execute("""UPDATE job_seekers SET full_name=%s, phone=%s, location=%s, skills=%s,
                       education=%s, experience_years=%s, about=%s WHERE seeker_id=%s""",
                    (name, f.get("phone", "").strip(), f.get("location", "").strip(),
                     f.get("skills", "").strip(), f.get("education", "").strip(), exp,
                     f.get("about", "").strip(), sid))
            session["name"] = name
            flash("Profile saved.", "success")
            return redirect(url_for("seeker.profile"))
    user = query("SELECT * FROM job_seekers WHERE seeker_id=%s", (sid,), one=True)
    return render_template("seeker/profile.html", user=user)


@bp.route("/resumes", methods=["GET", "POST"])
@login_required("seeker")
def resumes():
    sid = session["user_id"]
    if request.method == "POST":
        f = request.files.get("resume")
        if not f or not f.filename:
            flash("Choose a PDF file to upload.", "danger")
        elif not valid_pdf(f):
            flash("Only PDF files are accepted.", "danger")
        else:
            stored = uuid.uuid4().hex + ".pdf"
            f.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
            execute("INSERT INTO resumes (seeker_id, filename, original_name) VALUES (%s,%s,%s)",
                    (sid, stored, secure_filename(f.filename) or "resume.pdf"))
            flash("Resume uploaded.", "success")
        return redirect(url_for("seeker.resumes"))
    rows = query("""SELECT r.*, (SELECT COUNT(*) FROM applications a WHERE a.resume_id=r.resume_id) AS used
                    FROM resumes r WHERE r.seeker_id=%s ORDER BY r.uploaded_at DESC""", (sid,))
    return render_template("seeker/resumes.html", rows=rows)


@bp.route("/resumes/<int:resume_id>/download")
@login_required("seeker")
def download_resume(resume_id):
    r = query("SELECT * FROM resumes WHERE resume_id=%s AND seeker_id=%s", (resume_id, session["user_id"]), one=True)
    if not r:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], r["filename"],
                               as_attachment=True, download_name=r["original_name"])


@bp.route("/resumes/<int:resume_id>/delete", methods=["POST"])
@login_required("seeker")
def delete_resume(resume_id):
    r = query("""SELECT r.*, (SELECT COUNT(*) FROM applications a WHERE a.resume_id=r.resume_id) AS used
                 FROM resumes r WHERE r.resume_id=%s AND r.seeker_id=%s""", (resume_id, session["user_id"]), one=True)
    if not r:
        abort(404)
    if r["used"]:
        flash("This resume is attached to an application, so it can't be deleted.", "warning")
    else:
        execute("DELETE FROM resumes WHERE resume_id=%s", (resume_id,))
        try:
            os.remove(os.path.join(current_app.config["UPLOAD_FOLDER"], r["filename"]))
        except OSError:
            pass
        flash("Resume deleted.", "success")
    return redirect(url_for("seeker.resumes"))


@bp.route("/apply/<int:job_id>", methods=["POST"])
@login_required("seeker")
def apply(job_id):
    sid = session["user_id"]
    job = query("""SELECT j.*, c.name AS company FROM jobs j JOIN companies c ON c.company_id=j.company_id
                   WHERE j.job_id=%s AND j.status='Open' AND (j.deadline IS NULL OR j.deadline >= CURDATE())""",
                (job_id,), one=True)
    if not job:
        flash("This job is no longer accepting applications.", "warning")
        return redirect(url_for("jobs.listing"))
    resume = query("SELECT * FROM resumes WHERE resume_id=%s AND seeker_id=%s",
                   (request.form.get("resume_id", type=int), sid), one=True)
    if not resume:
        flash("Select one of your uploaded resumes to apply.", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    try:
        execute("INSERT INTO applications (job_id, seeker_id, resume_id, cover_letter) VALUES (%s,%s,%s,%s)",
                (job_id, sid, resume["resume_id"], request.form.get("cover_letter", "").strip()[:3000]))
    except mysql.connector.IntegrityError:
        flash("You have already applied for this job.", "info")
        return redirect(url_for("jobs.detail", job_id=job_id))
    notify_user("recruiter", job["recruiter_id"], f"New application: {job['title']}",
                f"{session['name']} applied for {job['title']}.")
    notify_user("seeker", sid, f"Application submitted: {job['title']}",
                f"Your application for {job['title']} at {job['company']} was submitted.")
    flash("Application submitted. Track its status under My applications.", "success")
    return redirect(url_for("seeker.applications"))


@bp.route("/applications")
@login_required("seeker")
def applications():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    where, args = "a.seeker_id=%s", [session["user_id"]]
    if status:
        where += " AND a.status=%s"
        args.append(status)
    base = f"""FROM applications a JOIN jobs j ON j.job_id=a.job_id JOIN companies c ON c.company_id=j.company_id
               WHERE {where}"""
    rows, pager = paginate(f"SELECT a.*, j.title, j.location, c.name AS company {base} ORDER BY a.applied_at DESC",
                           f"SELECT COUNT(*) c {base}", args, page)
    return render_template("seeker/applications.html", rows=rows, pager=pager, status=status)


@bp.route("/interviews")
@login_required("seeker")
def interviews():
    rows = query("""SELECT i.*, j.title, c.name AS company, c.location AS company_location FROM interviews i
                    JOIN applications a ON a.application_id=i.application_id
                    JOIN jobs j ON j.job_id=a.job_id JOIN companies c ON c.company_id=j.company_id
                    WHERE a.seeker_id=%s ORDER BY i.interview_date DESC, i.interview_time DESC""",
                 (session["user_id"],))
    return render_template("seeker/interviews.html", rows=rows)
