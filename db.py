import mysql.connector
from flask import g, current_app


def get_db():
    if "db" not in g:
        c = current_app.config
        g.db = mysql.connector.connect(
            host=c["DB_HOST"], port=c["DB_PORT"], user=c["DB_USER"],
            password=c["DB_PASSWORD"], database=c["DB_NAME"], autocommit=True,
        )
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None and db.is_connected():
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().cursor(dictionary=True)
    cur.execute(sql, tuple(args))
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=()):
    cur = get_db().cursor()
    cur.execute(sql, tuple(args))
    last_id = cur.lastrowid
    cur.close()
    return last_id
