"""The detect stage end to end: detector fixtures ingested as a repo (git replaced by a copy)."""

import re
import shutil
from pathlib import Path

import pytest
from conftest import query

pytestmark = pytest.mark.db

DETECTORS = Path(__file__).parent / "fixtures" / "detectors"
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


def test_detect_stage_stores_findings_with_symbols(detector_repo):
    rows = query(
        "SELECT f.rule_id, f.severity, f.line, f.message, f.snippet, fi.path,"
        " s.qualified_name FROM findings f JOIN files fi ON fi.id = f.file_id"
        " LEFT JOIN symbols s ON s.id = f.symbol_id WHERE f.snapshot_id = %s"
        " AND f.rule_id <> 'hardcoded-secret' ORDER BY f.line",
        detector_repo,
    )
    positives = ["js_positive.js", "py_positive.py", "ts_positive.ts"]
    assert sorted({r["path"] for r in rows}) == positives  # nothing from the negatives
    marks = sum(
        len(re.findall(r"(?:#|//)\s*expect:\s*[\w-]+", (DETECTORS / name).read_text()))
        for name in positives
    )
    assert len(rows) == marks
    rows = [r for r in rows if r["path"] == "py_positive.py"]
    first = rows[0]
    assert (first["rule_id"], first["severity"], first["line"]) == ("py-eval-exec", "high", 9)
    assert first["qualified_name"] == "py_positive.handler"
    assert first["message"] == "Use of eval() or exec()"
    assert first["snippet"].startswith("eval(request.args")
    assert {r["rule_id"] for r in rows} == {
        "py-eval-exec", "py-subprocess-shell", "py-sql-string", "py-bare-except",
    }


def test_js_findings_attach_to_js_symbols(detector_repo):
    rows = query(
        "SELECT f.rule_id, f.line, s.qualified_name FROM findings f"
        " JOIN files fi ON fi.id = f.file_id LEFT JOIN symbols s ON s.id = f.symbol_id"
        " WHERE f.snapshot_id = %s AND fi.path = 'ts_positive.ts' ORDER BY f.line",
        detector_repo,
    )
    assert rows[0]["rule_id"] == "js-eval"
    assert {r["qualified_name"] for r in rows} == {"ts_positive.ts:handler"}


def test_secrets_in_test_files_are_low(detector_repo):
    rows = query(
        "SELECT fi.path, f.severity, f.message, f.snippet FROM findings f"
        " JOIN files fi ON fi.id = f.file_id WHERE f.snapshot_id = %s"
        " AND f.rule_id = 'hardcoded-secret' ORDER BY fi.path",
        detector_repo,
    )
    assert [(r["path"], r["severity"]) for r in rows] == [
        ("src/config.py", "high"),
        ("tests/conftest.py", "low"),
    ]
    assert rows[1]["message"].endswith("in a test file.")
    assert all("fixture-not-a-real-password" not in r["snippet"] for r in rows)


def test_detect_stage_is_visible_in_progress(detector_repo):
    (job,) = query("SELECT stage, status FROM jobs ORDER BY id DESC LIMIT 1")
    assert (job["stage"], job["status"]) == ("done", "done")
