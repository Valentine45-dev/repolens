# ruff: noqa
"""Detector eval fixture: a small shop backend. Never executed, never imported.

Labels are trailing comments: a line marked "vuln" plus a category is an issue a reviewer
should see; "safe" plus a category marks code that looks similar but is fine. Categories:
code-injection, shell-command, sql-injection, bare-except, hardcoded-secret.
"""

import ast
import os
import subprocess

TABLE = "orders"

API_KEY = "a8f5f167f44f4964e6c998dee827110c"  # vuln: hardcoded-secret
DATABASE_URL = "postgresql://shop:Tr0ub4dor3@db.internal/shop"  # vuln: hardcoded-secret
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")  # safe: hardcoded-secret
ADMIN_PASSWORD = "<set-me>"  # safe: hardcoded-secret


def calculate(expression):
    return eval(expression)  # vuln: code-injection


def run_plugin(source):
    exec(source, {})  # vuln: code-injection


def default_rate():
    return eval("0.2 * 100")  # safe: code-injection


def parse_settings(text):
    return ast.literal_eval(text)  # safe: code-injection


def archive(name):
    subprocess.run(f"tar czf /backups/{name}.tgz /data", shell=True)  # vuln: shell-command


def ping(host):
    return subprocess.Popen("ping -c 1 " + host, shell=True)  # vuln: shell-command


def disk_usage():
    return subprocess.check_output("df -h", shell=True)  # safe: shell-command


def list_dir(path):
    return subprocess.run(["ls", "-l", path], capture_output=True)  # safe: shell-command


def find_user(conn, name):
    return conn.execute(f"SELECT * FROM users WHERE name = '{name}'")  # vuln: sql-injection


def find_order(conn, order_id):
    return conn.execute("SELECT * FROM orders WHERE id = " + order_id)  # vuln: sql-injection


def delete_user(conn, user_id):
    conn.execute("DELETE FROM users WHERE id = %s" % user_id)  # vuln: sql-injection


def update_email(conn, email, user_id):
    conn.execute("UPDATE users SET email = '{}' WHERE id = {}".format(email, user_id))  # vuln: sql-injection


def find_user_safely(conn, name):
    return conn.execute("SELECT * FROM users WHERE name = ?", (name,))  # safe: sql-injection


def count_rows(conn):
    return conn.execute(f"SELECT COUNT(*) FROM {TABLE}")  # safe: sql-injection


def log_lookup(name):
    print("SELECT * FROM users WHERE name = " + name)  # safe: sql-injection


def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except:  # vuln: bare-except
        return ""


def load_or_fail(path):
    try:
        with open(path) as f:
            return f.read()
    except:  # safe: bare-except
        raise


def load_quietly(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:  # safe: bare-except
        return ""
