from flask import Blueprint, abort, render_template, request, session

from db import query
from utils import paginate

bp = Blueprint("jobs", __name__)


@bp.route("/jobs")
def listing():
    q = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    job_type = request.args.get("job_type", "").strip()
    min_salary = request.args.get("min_salary", type=float)
    page = request.args.get("page", 1, type=int)

    where = ["j.status='Open'", "(j.deadline IS NULL OR j.deadline >= CURDATE())"]
    args = []
    if q:
        where.append("(j.title LIKE %s OR j.skills_required LIKE %s OR c.name LIKE %s)")
        args += [f"%{q}%"] * 3
    if location:
        where.append("j.location LIKE %s")
        args.append(f"%{location}%")
    if job_type:
        where.append("j.job_type = %s")
        args.append(job_type)
    if min_salary:
        where.append("j.salary_max >= %s")
        args.append(min_salary)

    base = "FROM jobs j JOIN companies c ON c.company_id = j.company_id WHERE " + " AND ".join(where)
    jobs, pager = paginate(f"SELECT j.*, c.name AS company {base} ORDER BY j.created_at DESC",
                           f"SELECT COUNT(*) c {base}", args, page)
    return render_template("jobs.html", jobs=jobs, pager=pager, q=q, location=location,
                           job_type=job_type, min_salary=request.args.get("min_salary", ""))


@bp.route("/jobs/<int:job_id>")
def detail(job_id):
    job = query("""SELECT j.*, c.name AS company, c.industry, c.website, c.description AS company_about,
                          c.location AS company_location
                   FROM jobs j JOIN companies c ON c.company_id = j.company_id WHERE j.job_id=%s""",
                (job_id,), one=True)
    if not job:
        abort(404)
    applied = resumes = None
    if session.get("role") == "seeker":
        sid = session["user_id"]
        applied = query("SELECT status FROM applications WHERE job_id=%s AND seeker_id=%s", (job_id, sid), one=True)
        resumes = query("SELECT * FROM resumes WHERE seeker_id=%s ORDER BY uploaded_at DESC", (sid,))
    from datetime import date
    expired = bool(job["deadline"] and job["deadline"] < date.today())
    return render_template("job_detail.html", job=job, applied=applied, resumes=resumes, expired=expired)
