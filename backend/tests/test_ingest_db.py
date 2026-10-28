"""End-to-end ingestion against a real Postgres, with git replaced by the fixture repo."""

import pytest
from conftest import SHA, query

pytestmark = pytest.mark.db


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
    assert len(files) == 16  # 7 Python, 8 JS/TS, tsconfig.json

    rows = query("SELECT kind, count(*) AS n FROM symbols GROUP BY kind")
    kinds = {r["kind"]: r["n"] for r in rows}
    assert kinds["module"] == 15
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
        ("tests/check_service.py", "module", "sample_app/service.py"),
        ("web/src/app.ts", "external", "fs"),  # node:fs
        ("web/src/app.ts", "external", "react"),
        ("web/src/app.ts", "module", "web/src/lib/index.ts"),  # ./lib -> index
        ("web/src/app.ts", "module", "web/src/lib/math.ts"),  # ./lib/math.js and @lib/math
        ("web/src/app.ts", "module", "web/src/view.tsx"),  # import("./view")
        ("web/src/app.ts", "unresolved", "web/src/missing"),
        ("web/src/legacy.cjs", "external", "path"),
        ("web/src/legacy.cjs", "module", "web/src/util.js"),  # require("./util")
        ("web/src/lib/index.ts", "module", "web/src/lib/math.ts"),  # export ... from
        ("web/src/lib/math.spec.ts", "module", "web/src/lib/math.ts"),
        ("web/src/server.js", "external", "http"),
        ("web/src/view.tsx", "module", "web/src/lib/index.ts"),  # @lib/index, no baseUrl
    ]

    calls = query(
        "SELECT s.qualified_name AS src, d.qualified_name AS dst, e.confidence FROM edges e"
        " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
        " WHERE e.type = 'calls'"
    )
    assert len(calls) == 16  # the full list is checked in test_calls.py
    assert ("sample_app.service.main", "sample_app.service.create_user", 1.0) in {
        (c["src"], c["dst"], c["confidence"]) for c in calls
    }
    assert ("web/src/lib/index.ts:Cache.getOr", "web/src/lib/index.ts:Cache.get", 0.9) in {
        (c["src"], c["dst"], round(c["confidence"], 2)) for c in calls
    }

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


def test_pinned_commit_skips_ls_remote_and_reuses_the_analysis(client, monkeypatch):
    from conftest import SHA

    from app.ingest import clone

    first = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()

    def no_ls_remote(url, timeout):
        raise AssertionError("ls-remote must not run for a pinned commit")

    monkeypatch.setattr(clone, "resolve_sha", no_ls_remote)
    again = client.post("/repos", json={"url": "https://github.com/example/sample", "commit": SHA})
    assert again.status_code == 202
    body = again.json()
    assert (body["snapshot_id"], body["job_id"], body["commit_sha"], body["status"]) == (
        first["snapshot_id"], first["job_id"], SHA, "done")


@pytest.mark.parametrize("commit", ["abc123", "A" * 40, "1c6f1b0", ""])
def test_pinned_commit_must_be_a_full_sha(client, commit):
    r = client.post("/repos", json={"url": "https://github.com/example/sample", "commit": commit})
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


def _flaky_fetch(errors):
    """fetch_commit that raises the given CloneErrors in turn, then copies the fixture repo."""
    import shutil

    from conftest import FIXTURE

    calls = []

    def fetch(url, sha, dest, timeout):
        calls.append(dest)
        dest.mkdir(parents=True)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        shutil.rmtree(dest)
        shutil.copytree(FIXTURE, dest)

    return fetch, calls


def test_fetch_network_error_is_retried_once(client, monkeypatch):
    from app.ingest import clone

    fetch, calls = _flaky_fetch([clone.CloneError("Could not resolve host", transient=True)])
    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/flaky"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "done", status
    assert len(calls) == 2


def test_fetch_retries_only_once_and_not_for_other_errors(client, monkeypatch):
    from app.ingest import clone

    twice = [clone.CloneError("timed out", transient=True)] * 2
    fetch, calls = _flaky_fetch(twice)
    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/down"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert (status["status"], status["stage"], len(calls)) == ("failed", "fetch", 2)

    fetch, calls = _flaky_fetch([clone.CloneError("not our ref", transient=False)])
    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/badref"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert (status["status"], len(calls)) == ("failed", 1)


def test_fetch_is_not_retried_without_time_left(client, monkeypatch):
    from app import config
    from app.ingest import clone

    monkeypatch.setattr(config, "MAX_ANALYSIS_S", 10)  # less than CLONE_TIMEOUT_S
    fetch, calls = _flaky_fetch([clone.CloneError("timed out", transient=True)])
    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/late"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert (status["status"], len(calls)) == ("failed", 1)
