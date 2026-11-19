import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")

    # MySQL
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "Pavani@123")
    DB_NAME = os.environ.get("DB_NAME", "job_recruitment")

    # Resume uploads (PDF only, 5 MB max)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads", "resumes")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    PER_PAGE = 6

    # Default admin account (created automatically if the admin table is empty)
    ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@hireflow.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
    # Secret key needed on the admin registration page (change it!)
    ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "admin@123")

    # Email notifications. Leave MAIL_USERNAME empty to only log emails.
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "admin")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "admin123")
    MAIL_SENDER = os.environ.get("MAIL_SENDER", "") or MAIL_USERNAME
