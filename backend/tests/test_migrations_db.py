"""The migrations in backend/migrations/ apply on top of the current schema in either order and
leave the snapshot_status view as schema.sql defines it (review S6: the older file used to
rebuild the view without search_state)."""

import os
from pathlib import Path

import psycopg
import pytest

pytestmark = pytest.mark.db

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
FILES = ["2026-10-28-repo-case-and-progress.sql", "2026-10-28-search-state.sql"]


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
