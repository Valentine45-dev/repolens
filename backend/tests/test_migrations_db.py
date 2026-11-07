"""The migrations in backend/migrations/ apply on top of the current schema in either order and
leave the snapshot_status view as schema.sql defines it (review S6: the older file used to
rebuild the view without search_state)."""

import os
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.db

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
FILES = ["2026-10-28-repo-case-and-progress.sql", "2026-10-28-search-state.sql",
         "2026-11-05-analysis-receipt.sql", "2026-11-05-import-scope.sql",
         "2026-11-07-findings-categories.sql"]


def _view_columns(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_name = 'snapshot_status' ORDER BY ordinal_position")]


@pytest.mark.parametrize("order", [FILES, FILES[::-1]])
def test_migrations_apply_in_either_order(test_db, order):
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        before = _view_columns(conn)
        assert "search_state" in before
        for name in order:
            conn.execute((MIGRATIONS / name).read_text(encoding="utf-8"))
        assert _view_columns(conn) == before


def test_findings_migration_marks_old_documentation_secrets(test_db):
    """Run on a row analysed before the columns existed: a secret in an .rst file becomes low and
    documentation; one in code is untouched; running it twice changes nothing more."""
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as conn:
        conn.execute("TRUNCATE repos RESTART IDENTITY CASCADE")
        conn.execute("INSERT INTO repos (url) VALUES ('https://github.com/example/old')")
        conn.execute("INSERT INTO snapshots (repo_id, commit_sha) VALUES (1, %s)", ("a" * 40,))
        for i, path in enumerate(["docs/conf.rst", "app.py", "tests/readme.md"], start=1):
            conn.execute("INSERT INTO files (snapshot_id, path, language) VALUES (1, %s, NULL)",
                         (path,))
            conn.execute(
                "INSERT INTO findings (snapshot_id, file_id, line, rule_id, severity, message,"
                " in_test) VALUES (1, %s, 1, 'hardcoded-secret', 'high', %s, %s)",
                (i, "Possible hardcoded secret (secret-assignment)"
                    + (" in test or example code." if i == 3 else "."), i == 3),
            )
        sql = (MIGRATIONS / "2026-11-07-findings-categories.sql").read_text(encoding="utf-8")
        conn.execute(sql)
        conn.execute(sql)
        rows = conn.execute(
            "SELECT fi.path, f.severity, f.in_docs, f.message FROM findings f"
            " JOIN files fi ON fi.id = f.file_id ORDER BY f.id").fetchall()
    assert rows == [
        ("docs/conf.rst", "low", True,
         "Possible hardcoded secret (secret-assignment) in documentation."),
        ("app.py", "high", False, "Possible hardcoded secret (secret-assignment)."),
        ("tests/readme.md", "low", True,
         "Possible hardcoded secret (secret-assignment) in test or example code and in "
         "documentation."),
    ]
