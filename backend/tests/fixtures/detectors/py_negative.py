"""Detector fixture: nothing in this file may be reported. Never executed."""

import ast
import subprocess


class Model:
    def eval(self):
        return self


def safe(cursor, name, user_id, model):
    model.eval()  # a method called eval, not the builtin
    ast.literal_eval("[1, 2]")
    subprocess.run(["ls", name])  # no shell
    subprocess.run("ls", shell=False)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))  # parameters, not formatting
    cursor.execute("SELECT * FROM users")  # constant SQL
    message = f"Hello {name}, select an item from the list"  # prose, not SQL
    label = "Update " + name + " settings"  # prose
    sql = "SELECT a " "FROM b"  # constant, implicitly concatenated
    try:
        cursor.close()
    except (ValueError, OSError):
        pass
    except Exception as exc:
        raise RuntimeError("failed") from exc
    return message, label, sql
