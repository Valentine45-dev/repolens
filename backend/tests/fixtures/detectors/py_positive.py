"""Detector fixture: every line marked `# expect: <rule>` must be reported. Never executed."""

import subprocess
import subprocess as sp
from subprocess import Popen as P, run


def handler(request, db, cursor, table, user_id, name):
    eval(request.args["expr"])  # expect: py-eval-exec
    exec(request.form["code"])  # expect: py-eval-exec

    subprocess.run(request.args["cmd"], shell=True)  # expect: py-subprocess-shell
    sp.check_output("ls " + name, shell=True)  # expect: py-subprocess-shell
    run(name, shell=True)  # expect: py-subprocess-shell
    P(name, shell=True, stdout=None)  # expect: py-subprocess-shell

    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")  # expect: py-sql-string
    cursor.execute("SELECT name FROM users WHERE name = '" + name + "'")  # expect: py-sql-string
    cursor.execute("DELETE FROM sessions WHERE user_id = %s" % user_id)  # expect: py-sql-string
    db.execute("UPDATE accounts SET balance = {} WHERE id = 1".format(name))  # expect: py-sql-string
    query = "INSERT INTO log (msg) VALUES ('" + name + "')"  # expect: py-sql-string
    cursor.execute(
        "select id from orders "  # expect: py-sql-string
        "where owner = " + name
    )

    try:
        db.commit()
    except:  # expect: py-bare-except
        pass
    return query
