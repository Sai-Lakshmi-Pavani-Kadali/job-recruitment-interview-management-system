"""Create the database/tables and the default admin account.

Usage:  python init_db.py            # schema + admin
        python init_db.py --reset-admin   # set the admin password back to ADMIN_PASSWORD (default admin123)
        python init_db.py --demo     # also add a demo recruiter, seeker and sample jobs
"""
import os
import sys

import mysql.connector
from werkzeug.security import generate_password_hash

from config import Config

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@hireflow.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def main():
    conn = mysql.connector.connect(host=Config.DB_HOST, port=Config.DB_PORT,
                                   user=Config.DB_USER, password=Config.DB_PASSWORD)
    cur = conn.cursor()
    with open(os.path.join(os.path.dirname(__file__), "schema.sql"), encoding="utf-8") as fh:
        for stmt in fh.read().split(";"):
            if stmt.strip():
                cur.execute(stmt)
    conn.database = Config.DB_NAME

    if "--reset-admin" in sys.argv:
        cur.execute("DELETE FROM admin")
    cur.execute("SELECT COUNT(*) FROM admin")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO admin (username, email, password_hash) VALUES (%s,%s,%s)",
                    (ADMIN_USER, ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD)))
        print(f"Admin created -> username: {ADMIN_USER}  password: {ADMIN_PASSWORD}")

    if "--demo" in sys.argv:
        cur.execute("SELECT COUNT(*) FROM recruiters WHERE email='recruiter@demo.com'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO companies (name, industry, website, location, description) VALUES "
                        "('Northwind Tech','Software','https://example.com','Hyderabad',"
                        "'Product engineering company building logistics software.')")
            cid = cur.lastrowid
            cur.execute("INSERT INTO recruiters (company_id, full_name, email, password_hash, phone) "
                        "VALUES (%s,'Demo Recruiter','recruiter@demo.com',%s,'9999999999')",
                        (cid, generate_password_hash("recruiter123")))
            rid = cur.lastrowid
            jobs = [
                ("Python Backend Developer", "Build REST APIs with Flask and MySQL.", "Python, Flask, MySQL", "Hyderabad", "Full-time", 4, 7),
                ("Frontend Developer", "Build responsive interfaces with HTML, CSS, JavaScript.", "HTML, CSS, JavaScript, Bootstrap", "Bengaluru", "Full-time", 3, 6),
                ("Data Analyst Intern", "Clean data and build dashboards.", "SQL, Excel, Python", "Remote", "Internship", 1, 2),
                ("QA Engineer", "Write test plans and automate regression tests.", "Selenium, Python, SQL", "Chennai", "Contract", 3, 5),
            ]
            for t, d, s, loc, jt, lo, hi in jobs:
                cur.execute("INSERT INTO jobs (recruiter_id, company_id, title, description, skills_required, location, "
                            "job_type, salary_min, salary_max, vacancies) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,2)",
                            (rid, cid, t, d, s, loc, jt, lo, hi))
            cur.execute("INSERT INTO job_seekers (full_name, email, password_hash, phone, location, skills, education, "
                        "experience_years) VALUES ('Demo Seeker','seeker@demo.com',%s,'8888888888','Hyderabad',"
                        "'Python, MySQL, Flask','B.Tech CSE',0)", (generate_password_hash("seeker123"),))
            print("Demo data added -> recruiter@demo.com / recruiter123, seeker@demo.com / seeker123")
    conn.commit()
    cur.close()
    conn.close()
    print("Database ready:", Config.DB_NAME)


if __name__ == "__main__":
    main()
