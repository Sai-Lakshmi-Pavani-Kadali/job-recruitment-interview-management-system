# HireFlow – Job Recruitment and Interview Management System

Flask + MySQL web app that connects job seekers and recruiters: profiles, PDF resumes, job search, applications,
shortlisting, interview scheduling, notifications and dashboards.

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

# MySQL credentials (defaults: localhost, user root, empty password, database job_recruitment)
set DB_USER=root
set DB_PASSWORD=your_mysql_password   # macOS/Linux: export DB_PASSWORD=...

python init_db.py --demo         # creates tables, the admin account and demo data (omit --demo for a clean start)
python app.py                    # open http://127.0.0.1:5000
```

| Role | Login |
|------|-------|
| Admin | username `admin`, password `admin123` (change with `ADMIN_PASSWORD` before running `init_db.py`) |
| Recruiter (demo) | `recruiter@demo.com` / `recruiter123` |
| Job seeker (demo) | `seeker@demo.com` / `seeker123` |

Create more admins at `/register/admin` (needs the admin key, default `admin@123`; set `ADMIN_SECRET_KEY` to change it).

If you change `DB_NAME`, also change the database name at the top of `schema.sql`.

## Email notifications
Every status change and interview schedule creates an in-app notification and an email. Emails are only logged to the
console until you set `MAIL_USERNAME`, `MAIL_PASSWORD` (Gmail: use an App Password), and optionally `MAIL_SERVER`,
`MAIL_PORT`, `MAIL_SENDER`.

## Project layout
```
app.py            app factory, CSRF protection, template filters
config.py         settings (environment variables)
db.py             MySQL connection + query helpers
utils.py          role decorator, pagination, notifications/email, constants
init_db.py        creates schema, admin and optional demo data
schema.sql        9 tables: admin, job_seekers, recruiters, companies, jobs, applications, resumes, interviews, notifications
routes/           auth.py  jobs.py  seeker.py  recruiter.py  admin.py
templates/        base, public pages, seeker/, recruiter/, admin/
static/           css/style.css, js/main.js
uploads/resumes/  uploaded PDFs (stored under random names)
```

## Feature map
- **Admin:** dashboard statistics and charts, activate/deactivate/delete job seekers and recruiters, close/reopen/delete jobs, change or delete applications, recent activity.
- **Job seeker:** register/login, profile, PDF resume upload/download/delete, search by title/skill/company, location, type and salary, apply with a chosen resume, application status tracking, interview schedule, notifications.
- **Recruiter:** register/login, company profile, post/edit/delete jobs, view and filter applications, candidate detail, resume download, shortlist/reject/select, schedule/reschedule/cancel/complete interviews, analytics dashboard.
- **Security:** hashed passwords, role-based access, CSRF tokens on all forms, parameterised SQL, PDF signature check, 5 MB upload limit, ownership checks on every recruiter/seeker record.

Before deploying, set a strong `SECRET_KEY`, change the admin password, and run behind a production server (e.g. gunicorn/waitress) with `debug` off.
