import os
import secrets
from datetime import date

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from markupsafe import Markup

import db
import utils
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    app.teardown_appcontext(db.close_db)

    from routes.admin import bp as admin_bp
    from routes.auth import bp as auth_bp
    from routes.jobs import bp as jobs_bp
    from routes.recruiter import bp as recruiter_bp
    from routes.seeker import bp as seeker_bp
    for bp in (auth_bp, jobs_bp, seeker_bp, recruiter_bp, admin_bp):
        app.register_blueprint(bp)

    # ----- make sure a default admin exists (so admin login always works) -----
    try:
        from werkzeug.security import generate_password_hash
        with app.app_context():
            if db.query("SELECT COUNT(*) c FROM admin", one=True)["c"] == 0:
                db.execute("INSERT INTO admin (username, email, password_hash) VALUES (%s,%s,%s)",
                           (app.config["ADMIN_USER"], app.config["ADMIN_EMAIL"],
                            generate_password_hash(app.config["ADMIN_PASSWORD"])))
                app.logger.info("Default admin created: %s", app.config["ADMIN_USER"])
    except Exception as exc:  # database not ready yet: run init_db.py
        app.logger.warning("Could not check admin account: %s", exc)

    # ----- CSRF protection for every POST -----
    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            token = session.get("_csrf")
            if not token or token != request.form.get("_csrf"):
                abort(400)

    def csrf_input():
        token = session.setdefault("_csrf", secrets.token_hex(16))
        return Markup(f'<input type="hidden" name="_csrf" value="{token}">')

    def page_url(n):
        args = request.args.to_dict()
        args["page"] = n
        return url_for(request.endpoint, **{**(request.view_args or {}), **args})

    app.jinja_env.globals.update(csrf_input=csrf_input, page_url=page_url, salary_text=utils.salary_text)
    app.jinja_env.filters.update(fmt_time=utils.fmt_time, fmt_date=utils.fmt_date, fmt_dt=utils.fmt_dt)

    @app.context_processor
    def inject_globals():
        unread, role = 0, session.get("role")
        if role in ("seeker", "recruiter"):
            try:
                unread = db.query(
                    "SELECT COUNT(*) c FROM notifications WHERE user_type=%s AND user_id=%s AND is_read=0",
                    (role, session["user_id"]), one=True)["c"]
            except Exception:
                unread = 0
        return dict(unread=unread, STATUSES=utils.STATUSES, JOB_TYPES=utils.JOB_TYPES,
                    INTERVIEW_STATUSES=utils.INTERVIEW_STATUSES, INTERVIEW_MODES=utils.INTERVIEW_MODES,
                    today=date.today().isoformat())

    @app.errorhandler(400)
    def bad_request(_e):
        return render_template("error.html", code=400,
                               message="That request could not be processed. Go back, refresh the page, and try again."), 400

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="We couldn't find that page."), 404

    @app.errorhandler(413)
    def too_large(_e):
        flash("File is too large. Resumes must be 5 MB or smaller.", "danger")
        return redirect(request.referrer or url_for("auth.index"))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
