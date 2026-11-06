"""Source lines on edges: where each import and call happens (parser, stored sites, API)."""

import pytest
from conftest import query

from app.ingest.parse import parse_python
from app.ingest.parse_js import parse_js

PY_MAIN = '''import os
from app import util as u
from app.util import (
    helper,
    other,
)


def run():
    helper()
    def inner():
        other()
    return u.helper(
    )


class K:
    def m(self):
        self.n()
        helper()

    def n(self):
        (
            u
            .helper()
        )
'''
PY_UTIL = "def helper():\n    pass\n\n\ndef other():\n    pass\n"

TS_LIB = "export function f() {}\nexport function g() {\n  return 1;\n}\n"
TS_APP = '''import {
  f,
  g,
} from "./lib";
import * as L from "./lib";
export { f as ff } from "./lib";
function run() {
  f();
  const x = L
    .g()
    .toString();
}
'''
CJS = '''const {
  f,
} = require(
  "./lib"
);
function go() {
  f();
}
'''


def test_python_import_lines_are_statement_starts():
    pf = parse_python("app/main.py", PY_MAIN)
    assert [(i.specifier, i.line) for i in pf.imports] == [
        ("os", 1), ("app", 2), ("app.util", 3),  # the multi-line import starts on line 3
    ]


def test_python_call_line_is_the_callee_names_line():
    pf = parse_python("app/main.py", PY_MAIN)
    got = [(c.name, c.line) for c in pf.calls]
    assert ("helper", 10) in got      # plain call
    assert ("other", 12) in got       # call inside a nested function
    assert ("helper", 13) in got      # u.helper( on one line, the closing paren on the next
    assert ("n", 19) in got           # method call through self
    assert ("helper", 20) in got
    # `u` on line 24, `.helper()` on line 25: the call node starts on 24, the name is on 25.
    assert ("helper", 25) in got and ("helper", 24) not in got


def test_js_multi_line_import_starts_on_the_statement_line_and_require_on_its_own():
    ts = parse_js("web/app.ts", TS_APP)
    assert [(i.specifier, i.line) for i in ts.imports] == [
        ("./lib", 1), ("./lib", 5), ("./lib", 6),
    ]
    cjs = parse_js("web/c.js", CJS)
    # `require` is a call: its line is where `require(` is, not where `const {` starts.
    assert [(i.specifier, i.line) for i in cjs.imports] == [("./lib", 3)]


def test_js_chained_multi_line_call_points_at_the_callee_name_line():
    ts = parse_js("web/app.ts", TS_APP)
    got = [(c.name, c.line) for c in ts.calls]
    assert ("f", 8) in got
    assert ("g", 10) in got and ("toString", 11) in got  # `L` is on line 9, `.g()` on line 10


# --- stored sites -----------------------------------------------------------------------------

@pytest.fixture
def lines_snapshot(client, monkeypatch):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        (dest / "app").mkdir(parents=True)
        (dest / "app" / "__init__.py").write_text("", encoding="utf-8")
        (dest / "app" / "main.py").write_text(PY_MAIN, encoding="utf-8")
        (dest / "app" / "util.py").write_text(PY_UTIL, encoding="utf-8")
        (dest / "web").mkdir()
        (dest / "web" / "lib.ts").write_text(TS_LIB, encoding="utf-8")
        (dest / "web" / "app.ts").write_text(TS_APP, encoding="utf-8")
        (dest / "web" / "c.js").write_text(CJS, encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/lines"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def _sites(snapshot_id, kind, src_path, dst_path):
    rows = query(
        "SELECT e.id, e.site_count, array_agg(es.line ORDER BY es.line) AS lines"
        " FROM edges e JOIN symbols s ON s.id = e.src_id JOIN files sf ON sf.id = s.file_id"
        " JOIN symbols d ON d.id = e.dst_id JOIN files df ON df.id = d.file_id"
        " LEFT JOIN edge_sites es ON es.edge_id = e.id"
        " WHERE e.snapshot_id = %s AND e.type = %s AND sf.path = %s AND df.path = %s"
        " GROUP BY e.id",
        snapshot_id, kind, src_path, dst_path)
    return [(r["lines"], r["site_count"]) for r in rows]


@pytest.mark.db
def test_import_sites_are_stored_per_target(lines_snapshot):
    s = lines_snapshot
    # `from app import util as u` (line 2) and `from app.util import (...)` (line 3): one edge.
    assert _sites(s, "imports", "app/main.py", "app/util.py") == [([2, 3], 2)]
    # multi-line import (1), `import * as` (5), `export ... from` (6)
    assert _sites(s, "imports", "web/app.ts", "web/lib.ts") == [([1, 5, 6], 3)]
    assert _sites(s, "imports", "web/c.js", "web/lib.ts") == [([3], 1)]


@pytest.mark.db
def test_call_sites_keep_each_line(lines_snapshot):
    s = lines_snapshot
    rows = query(
        "SELECT sc.qualified_name AS caller, d.qualified_name AS callee, e.site_count,"
        " array_agg(es.line ORDER BY es.line) AS lines FROM edges e"
        " JOIN symbols sc ON sc.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
        " JOIN edge_sites es ON es.edge_id = e.id WHERE e.snapshot_id = %s AND e.type = 'calls'"
        " GROUP BY e.id, sc.qualified_name, d.qualified_name", s)
    got = {(r["caller"], r["callee"]): r["lines"] for r in rows}
    assert got[("app.main.run", "app.util.helper")] == [10, 13]  # two calls, two lines
    assert got[("app.main.K.m", "app.util.helper")] == [20]
    assert got[("app.main.K.m", "app.main.K.n")] == [19]
    assert got[("app.main.K.n", "app.util.helper")] == [25]
    assert got[("web/app.ts:run", "web/lib.ts:f")] == [8]
    assert got[("web/app.ts:run", "web/lib.ts:g")] == [10]
    assert all(r["site_count"] == len(r["lines"]) for r in rows)
    assert query("SELECT count(*) AS n FROM edges WHERE snapshot_id = %s"
                 " AND type IN ('imports', 'calls') AND site_count IS NULL", s)[0]["n"] == 0


def _module_id(snapshot_id, path):
    return query("SELECT sy.id FROM symbols sy JOIN files f ON f.id = sy.file_id"
                 " WHERE sy.snapshot_id = %s AND sy.kind = 'module' AND f.path = %s",
                 snapshot_id, path)[0]["id"]


@pytest.mark.db
def test_api_items_carry_sites_and_keep_their_old_fields(client, lines_snapshot):
    s = lines_snapshot
    main = _module_id(s, "app/main.py")
    body = client.get(f"/symbols/{main}/dependencies?min_confidence=0").json()
    imp = next(i for i in body["items"]
               if i["type"] == "imports" and i["symbol"]["path"] == "app/util.py")
    assert [x["line"] for x in imp["sites"]] == [2, 3] and imp["site_count"] == 2
    assert imp["site_path"] == "app/main.py"  # the lines are in the importing file
    call = next(i for i in body["items"]
                if i["type"] == "calls" and i["symbol"]["qualified_name"] == "app.util.helper")
    assert [x["line"] for x in call["sites"]] == [10, 13, 20, 25]
    util = _module_id(s, "app/util.py")
    back = client.get(f"/symbols/{util}/dependents?min_confidence=0").json()
    imp_in = next(i for i in back["items"] if i["type"] == "imports")
    assert imp_in["site_path"] == "app/main.py" and [x["line"] for x in imp_in["sites"]] == [2, 3]
    assert {"type", "confidence", "symbol"} <= set(imp_in)


@pytest.mark.db
def test_graph_answers_include_sites(client, lines_snapshot):
    body = client.post(f"/snapshots/{lines_snapshot}/ask",
                       json={"question": "Which files import app/util.py?"}).json()
    assert body["kind"] == "graph" and body["results"]
    first = body["results"][0]
    assert first["site_path"] == "app/main.py" and [x["line"] for x in first["sites"]] == [2, 3]


@pytest.mark.db
def test_symbol_view_edges_carry_the_call_lines(client, lines_snapshot):
    view = client.get(f"/snapshots/{lines_snapshot}/graph",
                      params={"level": "symbol", "root": "app/main.py", "min_confidence": 0})
    assert view.status_code == 200, view.text
    calls = [e for e in view.json()["edges"] if e["type"] == "calls"]
    assert calls and all("sites" in e and "site_count" in e for e in calls)
    lines = sorted(x["line"] for e in calls for x in e["sites"] if x["path"] == "app/main.py")
    assert {10, 13} <= set(lines)  # run -> helper (two sites on one edge)
    assert all(e["site_count"] is not None for e in calls)
    assert all(e["sites"] == [] and e["site_count"] is None
               for e in view.json()["edges"] if e["type"] != "calls")


@pytest.mark.db
def test_backfill_restores_sites_and_leaves_edge_rows_unchanged(lines_snapshot):
    from app.db import pool
    from app.ingest.backfill import backfill_snapshot, snapshots_to_backfill

    s = lines_snapshot
    before = query("SELECT count(*) AS n FROM edge_sites")[0]["n"]
    assert before > 0
    with pool().connection() as conn:  # make the snapshot look like it predates sites
        conn.execute("DELETE FROM edge_sites WHERE edge_id IN"
                     " (SELECT id FROM edges WHERE snapshot_id = %s)", (s,))
        conn.execute("UPDATE edges SET site_count = NULL WHERE snapshot_id = %s", (s,))
    assert s in snapshots_to_backfill()
    result = backfill_snapshot(s)
    assert result["changed"] == []
    assert query("SELECT count(*) AS n FROM edge_sites")[0]["n"] == before
    assert s not in snapshots_to_backfill()
