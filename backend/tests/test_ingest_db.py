"""End-to-end ingestion against a real Postgres, with git replaced by the fixture repo."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
SHA = "a" * 40


@pytest.fixture
def client(test_db, monkeypatch, tmp_path):
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


def test_ingest_fixture_repo(client, tmp_path):
    r = client.post("/repos", json={"url": "https://github.com/Example/Sample.git"})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["commit_sha"] == SHA

    # TestClient runs background tasks before returning, so the job has finished.
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "done", status
    assert status["percent"] == 100
    assert status["url"] == "https://github.com/example/sample"

    files = query("SELECT path FROM files ORDER BY path")
    assert len(files) == 13  # 5 Python, 7 JS/TS, tsconfig.json

    rows = query("SELECT kind, count(*) AS n FROM symbols GROUP BY kind")
    kinds = {r["kind"]: r["n"] for r in rows}
    assert kinds["module"] == 12
    assert kinds["class"] >= 6

    js = query("SELECT s.qualified_name FROM symbols s JOIN files f ON f.id = s.file_id"
               " WHERE f.path = 'web/src/app.ts' AND s.kind <> 'module'")
    assert {r["qualified_name"] for r in js} >= {"web/src/app.ts:App.render",
                                                 "web/src/app.ts:main"}

    edges = query(
        "SELECT fs.path AS src, d.kind, coalesce(fd.path, d.qualified_name) AS dst"
        " FROM edges e JOIN symbols s ON s.id = e.src_id JOIN files fs ON fs.id = s.file_id"
        " JOIN symbols d ON d.id = e.dst_id LEFT JOIN files fd ON fd.id = d.file_id"
        " WHERE e.type = 'imports'"
    )
    assert sorted((e["src"], e["kind"], e["dst"]) for e in edges) == [
        ("sample_app/__init__.py", "module", "sample_app/models.py"),
        ("sample_app/__init__.py", "module", "sample_app/service.py"),
        ("sample_app/__init__.py", "module", "sample_app/settings.py"),
        ("sample_app/broken.py", "unresolved", "sample_app.gone"),
        ("sample_app/broken.py", "unresolved", "sample_app.missing_mod"),
        ("sample_app/models.py", "external", "dataclasses"),
        ("sample_app/service.py", "external", "logging"),
        ("sample_app/service.py", "module", "sample_app/models.py"),
        ("sample_app/settings.py", "external", "os"),
        ("web/src/app.ts", "external", "fs"),  # node:fs
        ("web/src/app.ts", "external", "react"),
        ("web/src/app.ts", "module", "web/src/lib/index.ts"),  # ./lib -> index
        ("web/src/app.ts", "module", "web/src/lib/math.ts"),  # ./lib/math.js and @lib/math
        ("web/src/app.ts", "module", "web/src/view.tsx"),  # import("./view")
        ("web/src/app.ts", "unresolved", "web/src/missing"),
        ("web/src/legacy.cjs", "external", "path"),
        ("web/src/legacy.cjs", "module", "web/src/util.js"),  # require("./util")
        ("web/src/lib/index.ts", "module", "web/src/lib/math.ts"),  # export ... from
        ("web/src/server.js", "external", "http"),
        ("web/src/view.tsx", "module", "web/src/lib/index.ts"),  # @lib/index, no baseUrl
    ]

    (finding,) = query("SELECT f.rule_id, f.line, f.snippet, fi.path FROM findings f"
                       " JOIN files fi ON fi.id = f.file_id")
    assert finding["rule_id"] == "hardcoded-secret"
    assert finding["path"] == "sample_app/settings.py"
    assert finding["line"] == 5
    assert "[REDACTED]" in finding["snippet"]
    assert "fixture-not-a-real-password" not in finding["snippet"]

    stored = query("SELECT content FROM files WHERE path = 'sample_app/settings.py'")[0]
    assert "fixture-not-a-real-password" not in stored["content"]

    # The clone workspace is gone.
    assert not any((tmp_path / "work").glob("*"))

    # Submitting again reuses the finished job.
    again = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()
    assert again["job_id"] == body["job_id"]
    assert again["status"] == "done"


def test_rejects_non_github_url(client):
    r = client.post("/repos", json={"url": "https://gitlab.com/a/b"})
    assert r.status_code == 422


def test_unknown_snapshot_is_404(client):
    assert client.get("/snapshots/999999/status").status_code == 404


def test_failed_fetch_marks_job_failed_and_cleans_up(client, monkeypatch, tmp_path):
    from app.ingest import clone

    def failing_fetch(url, sha, dest, timeout):
        dest.mkdir(parents=True)
        raise clone.CloneError("git fetch timed out after 1s")

    monkeypatch.setattr(clone, "fetch_commit", failing_fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/broken"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "failed"
    assert status["stage"] == "fetch"
    assert "timed out" in status["error"]
    assert not any((tmp_path / "work").glob("*"))
