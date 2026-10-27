"""Test database setup.

DB tests use TEST_DATABASE_URL only, never DATABASE_URL, so running pytest cannot wipe dev data.
The database name must end in `_test`; anything else is a hard error. The schema is rebuilt
from schema.sql once per session.
"""

import os
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def check_test_database_url(url: str) -> str:
    """Return the URL if its database name ends in `_test`, else raise."""
    dbname = conninfo_to_dict(url).get("dbname") or ""
    if not dbname.endswith("_test"):
        raise pytest.UsageError(
            f"TEST_DATABASE_URL must name a database ending in '_test' (got {dbname!r})"
        )
    return url


def pytest_configure(config):
    # The app must never see the dev database during tests.
    os.environ.pop("DATABASE_URL", None)
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        check_test_database_url(url)


@pytest.fixture(scope="session")
def test_db():
    """Rebuild the schema in the test database and point the app at it."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("needs TEST_DATABASE_URL")
    url = check_test_database_url(url)

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(SCHEMA.read_text(encoding="utf-8"))

    from app import config

    config.DATABASE_URL = url
    yield url
    config.DATABASE_URL = ""
