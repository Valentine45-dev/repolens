"""Test database setup.

DB tests use TEST_DATABASE_URL only, never DATABASE_URL, so running pytest cannot wipe dev data.
The database name must end in `_test`; anything else is a hard error. The schema is rebuilt
from schema.sql once per session.
"""

import os
import shutil
from pathlib import Path

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"
FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
DETECTORS = Path(__file__).parent / "fixtures" / "detectors"
SECRET_VALUE = "fixture-not-a-real-password"
SHA = "a" * 40


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
    elif os.environ.get("CI"):
        # Locally DB tests skip without a test database; in CI that would hide them.
        raise pytest.UsageError("TEST_DATABASE_URL must be set in CI")


@pytest.fixture(scope="session")
def test_db():
    """Rebuild the schema in the test database and point the app at it."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("needs TEST_DATABASE_URL")
    url = check_test_database_url(url)

    # Fail fast (not hang) when the database is down.
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(SCHEMA.read_text(encoding="utf-8"))

    from app import config

    config.DATABASE_URL = url
    yield url
    config.DATABASE_URL = ""


@pytest.fixture
def client(test_db, monkeypatch, tmp_path):
    """API client on an empty test database, with git replaced by a copy of the fixture repo."""
    from fastapi.testclient import TestClient

    from app import config
    from app.ingest import clone
    from app.main import app

    def fake_fetch(url, sha, dest, timeout):
        shutil.copytree(FIXTURE, dest)

    monkeypatch.setattr(clone, "resolve_sha", lambda url, timeout: SHA)
    monkeypatch.setattr(clone, "fetch_commit", fake_fetch)
    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "work")

    with TestClient(app) as c:
        from app.db import pool

        with pool().connection() as conn:
            conn.execute("TRUNCATE repos RESTART IDENTITY CASCADE")
        yield c


def query(sql, *args):
    from app.db import pool

    with pool().connection() as conn:
        return conn.execute(sql, args).fetchall()


SECRET = 'DB_PASSWORD = "fixture-not-a-real-password"\n'


@pytest.fixture
def detector_repo(client, monkeypatch, tmp_path):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        shutil.copytree(DETECTORS, dest)
        (dest / "src").mkdir()
        (dest / "src" / "config.py").write_text(SECRET, encoding="utf-8")
        (dest / "tests").mkdir()
        (dest / "tests" / "conftest.py").write_text(SECRET, encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/detectors"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "done", status
    return body["snapshot_id"]
