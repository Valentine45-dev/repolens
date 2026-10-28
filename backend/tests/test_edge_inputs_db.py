"""Ingestion of awkward inputs (review fixes, 28 Oct): a file the parser cannot walk, line breaks
other than "\\n", and secrets in config files without quotes."""

import pytest
from conftest import query

pytestmark = pytest.mark.db

# A 1,500-term string concatenation nests deeper than Python's recursion limit allows the
# parser and detector walks to go (a RecursionError before the fix failed the whole job).
# One term per line, so discover does not drop it as minified. (The eval() below is fixture
# text for the detector; nothing in a fixture is ever executed.)
DEEP_JS = "var page =\n  " + " +\n  ".join(f'"part{i}"' for i in range(1500)) + ";\n"
OK_JS = "function stillParsed() {\n  return 1;\n}\n"
# A form feed on line 2: splitlines() treats it as an extra line break, "\n" counting does not.
FORM_FEED_PY = "x = 1\n\x0c\ndef f(data):\n    eval(data)\n"


@pytest.fixture
def edge_snapshot(client, monkeypatch):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        (dest / "web").mkdir(parents=True)
        (dest / "web" / "deep.js").write_text(DEEP_JS, encoding="utf-8")
        (dest / "web" / "ok.js").write_text(OK_JS, encoding="utf-8")
        (dest / "app").mkdir()
        (dest / "app" / "ff.py").write_bytes(FORM_FEED_PY.encode("utf-8"))

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/edges"}).json()
    status = client.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "done", status
    return body["snapshot_id"]


def _symbols(snapshot_id, path):
    return [(r["kind"], r["name"]) for r in query(
        "SELECT s.kind, s.name FROM symbols s JOIN files f ON f.id = s.file_id"
        " WHERE f.snapshot_id = %s AND f.path = %s ORDER BY s.start_line, s.id",
        snapshot_id, path)]


def test_a_file_the_parser_cannot_walk_keeps_only_its_module(edge_snapshot):
    assert _symbols(edge_snapshot, "web/deep.js") == [("module", "deep")]
    assert ("function", "stillParsed") in _symbols(edge_snapshot, "web/ok.js")
    assert query("SELECT count(*) AS n FROM findings f JOIN files fi ON fi.id = f.file_id"
                 " WHERE fi.path = 'web/deep.js'")[0]["n"] == 0


def test_finding_snippet_is_the_reported_line_despite_a_form_feed(edge_snapshot):
    rows = query("SELECT f.line, f.snippet FROM findings f JOIN files fi ON fi.id = f.file_id"
                 " WHERE fi.path = 'app/ff.py' AND f.rule_id = 'py-eval-exec'")
    assert [(r["line"], r["snippet"]) for r in rows] == [(4, "eval(data)")]
