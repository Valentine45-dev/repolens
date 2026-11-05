"""GET /snapshots/{id}/graph?level=... on an ingested fixture repo (fixtures/folder_repo plus a big/
folder written at fetch time). Expected values are worked out by hand from the fixture's source."""

import json
import shutil
from pathlib import Path

import psycopg
import pytest
from conftest import SHA, query

pytestmark = pytest.mark.db

FOLDER_REPO = Path(__file__).parent / "fixtures" / "folder_repo"
MIGRATION = Path(__file__).resolve().parent.parent / "migrations" / "2026-11-05-import-scope.sql"
MODS = 61


def _write_big(dest: Path) -> None:
    big = dest / "big"
    (big / "sub").mkdir(parents=True)
    (big / "hub.py").write_text("import deep.er.only\n\n\ndef shared():\n    return 1\n",
                                encoding="utf-8")
    for i in range(MODS):
        (big / f"mod_{i:02}.py").write_text("from big.hub import shared\n\nVALUE = shared()\n",
                                            encoding="utf-8")
    (big / "sub" / "leaf.py").write_text("from big.hub import shared\n\nLEAF = shared()\n",
                                         encoding="utf-8")
    (big / "sub" / "leaf2.py").write_text("LEAF2 = 1\n", encoding="utf-8")


def _fetch(url, sha, dest, timeout):
    shutil.copytree(FOLDER_REPO, dest)
    _write_big(dest)


@pytest.fixture(scope="module")
def api(test_db, tmp_path_factory):
    """One client for the read-only tests below: an analysis takes a while, a view does not."""
    from fastapi.testclient import TestClient

    from app import config
    from app.db import pool
    from app.ingest import clone
    from app.main import app

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(clone, "resolve_sha", lambda url, timeout: SHA)
        patch.setattr(clone, "fetch_commit", _fetch)
        patch.setattr(config, "WORKSPACE_DIR", tmp_path_factory.mktemp("work"))
        with TestClient(app, base_url="http://127.0.0.1") as c:
            with pool().connection() as conn:
                conn.execute("TRUNCATE repos RESTART IDENTITY CASCADE")
            yield c


@pytest.fixture(scope="module")
def snap(api):
    body = api.post("/repos", json={"url": "https://github.com/example/folders"}).json()
    status = api.get(f"/snapshots/{body['snapshot_id']}/status").json()
    assert status["status"] == "done", status
    return body["snapshot_id"]


def view(api, snap, **params):
    response = api.get(f"/snapshots/{snap}/graph", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def nodes(v):
    return {n["id"]: n for n in v["nodes"]}


def edges(v):
    return {(e["source"], e["target"]): e for e in v["edges"]}


def counts(e):
    return e["count"], e["imports"], e["calls"], e["cycle_edges"]


def underlying(snap, sql_filter, *args):
    """Direct count of import + call edges, for the conservation check."""
    (row,) = query(
        "SELECT count(*) AS n FROM edges e JOIN symbols s ON s.id = e.src_id"
        " JOIN symbols d ON d.id = e.dst_id JOIN files sf ON sf.id = s.file_id"
        " JOIN files df ON df.id = d.file_id WHERE e.snapshot_id = %s"
        " AND e.type IN ('imports', 'calls') AND s.file_id <> d.file_id"
        " AND round(e.confidence::numeric, 2) >= 0.9 AND " + sql_filter,
        snap, *args)
    return row["n"]


def test_root_nodes_exact(api, snap):
    v = view(api, snap, level="folder")
    assert (v["level"], v["root"], v["view_limit"]) == ("folder", "", 60)
    assert (v["total_files"], v["hidden_files"], v["hidden_count"]) == (98, 2, 0)
    assert [(n["id"], n["label"], n["file_count"]) for n in v["nodes"]] == [
        ("dir:alpha", "alpha", 2),
        ("dir:beta", "beta", 2),
        ("dir:big", "big", 64),
        ("dir:challenge", "challenge", 2),
        ("dir:deploy", "deploy", 1),  # one code file, but its compose.yml has a finding
        ("dir:gx", "gx", 2),
        ("dir:gy", "gy", 2),
        ("dir:lazy", "lazy", 2),
        ("dir:scoring", "scoring", 3),
        ("dir:src/mapped", "src/mapped", 3),  # the merged chain
        ("dir:typed", "typed", 2),
        ("dir:web", "web", 10),
        ("file:core/engine.py", "core/engine.py", 1),  # a single-file folder
        ("file:deep/er/only.py", "deep/er/only.py", 1),  # a chain ending in one file
        ("file:top.py", "top.py", 1),
    ]
    by_id = nodes(v)
    assert by_id["dir:deploy"]["finding_count"] == 1
    assert by_id["dir:scoring"]["finding_count"] == 1  # the bare except; tests.py's is hidden
    assert by_id["dir:scoring"]["test_file_count"] == 1
    assert v["other_findings"] == 1  # README.md, on no node
    file_node = by_id["file:top.py"]
    assert (file_node["language"], file_node["kind"]) == ("python", "file")
    assert (file_node["external_imports"], file_node["unresolved_imports"]) == (0, 0)
    assert v["breadcrumbs"] == [{"path": "", "label": ""}]


def test_root_edges_exact(api, snap):
    v = view(api, snap, level="folder")
    assert {k: counts(e) for k, e in edges(v).items()} == {
        ("dir:alpha", "dir:beta"): (2, 1, 1, 1),
        ("dir:beta", "dir:alpha"): (2, 1, 1, 1),
        ("dir:big", "file:deep/er/only.py"): (1, 1, 0, 0),
        ("dir:challenge", "dir:scoring"): (2, 1, 1, 0),
        ("dir:scoring", "dir:challenge"): (4, 2, 2, 0),
        ("file:top.py", "dir:big"): (2, 1, 1, 0),
    }
    by_id = nodes(v)
    # Inside a folder: not drawn, still counted.
    assert by_id["dir:lazy"]["internal_count"] == 3  # one->two import + call, two->one import
    assert by_id["dir:typed"]["internal_count"] == 3  # x->y import + call, y->x type import
    assert by_id["dir:src/mapped"]["internal_count"] == 2
    assert by_id["dir:web"]["internal_count"] == 11
    # The repo root has no outside.
    assert all(n["outside_in"] == n["outside_out"] == 0 for n in v["nodes"])
    assert not any(e["guess"] for e in v["edges"])


def test_two_way_folder_edges_are_not_cycles(api, snap):
    """challenge <-> scoring, with top-level imports both ways and a function-local one: both
    edges exist, no cycle edge, and neither folder is marked. As in PyGoat."""
    v = view(api, snap, level="folder")
    pair = edges(v)
    assert pair["dir:challenge", "dir:scoring"]["cycle_edges"] == 0
    assert pair["dir:scoring", "dir:challenge"]["cycle_edges"] == 0
    assert nodes(v)["dir:challenge"]["in_cycle"] is False
    assert nodes(v)["dir:scoring"]["in_cycle"] is False


def test_cycles_exact_and_false_cycles_excluded(api, snap):
    v = view(api, snap, level="folder")
    assert v["cycle_scope"] == "top_level_imports" and v["cycles_available"] is True
    assert v["cycles"] == [
        {"id": 1, "size": 2, "files": ["alpha/p.py", "beta/q.py"]},
        {"id": 2, "size": 2, "files": ["src/mapped/a.py", "src/mapped/b.py"]},
        {"id": 3, "size": 2, "files": ["web/c1.js", "web/c2.js"]},
    ]
    by_id = nodes(v)
    assert {k for k, n in by_id.items() if n["in_cycle"]} == {
        "dir:alpha", "dir:beta", "dir:src/mapped", "dir:web"}
    assert by_id["dir:web"]["cycle_ids"] == [3] and by_id["dir:web"]["cycle_files"] == 2
    # The false cycles are real edges: lazy (function-local), typed (TYPE_CHECKING),
    # web one<->two (import type), lazy_a<->lazy_b (require in a function), dyn (import()).
    paths = [("lazy/one.py", "lazy/two.py"), ("lazy/two.py", "lazy/one.py"),
             ("typed/x.py", "typed/y.py"), ("typed/y.py", "typed/x.py"),
             ("web/one.ts", "web/two.ts"), ("web/two.ts", "web/one.ts"),
             ("web/lazy_a.js", "web/lazy_b.js"), ("web/lazy_b.js", "web/lazy_a.js"),
             ("web/dyn_a.ts", "web/dyn_b.ts"), ("web/dyn_b.ts", "web/dyn_a.ts")]
    for source, target in paths:
        assert underlying(snap, "sf.path = %s AND df.path = %s AND e.type = 'imports'",
                          source, target) == 1, (source, target)


def test_import_scopes_stored(api, snap):
    rows = query(
        "SELECT sf.path AS a, df.path AS b, e.import_scope FROM edges e"
        " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
        " JOIN files sf ON sf.id = s.file_id JOIN files df ON df.id = d.file_id"
        " WHERE e.snapshot_id = %s AND e.type = 'imports'"
        " AND (sf.path LIKE 'web/%%' OR sf.path LIKE 'typed/%%' OR sf.path LIKE 'lazy/%%')",
        snap)
    assert {(r["a"], r["b"]): r["import_scope"] for r in rows} == {
        ("lazy/one.py", "lazy/two.py"): "top_level",
        ("lazy/two.py", "lazy/one.py"): "nested",
        ("typed/x.py", "typed/y.py"): "top_level",
        ("typed/y.py", "typed/x.py"): "type_checking",
        ("web/one.ts", "web/two.ts"): "type_checking",
        ("web/two.ts", "web/one.ts"): "top_level",
        ("web/both.ts", "web/one.ts"): "top_level",
        ("web/both.ts", "web/two.ts"): "type_checking",
        ("web/shape.d.ts", "web/one.ts"): "type_checking",
        ("web/lazy_a.js", "web/lazy_b.js"): "top_level",
        ("web/lazy_b.js", "web/lazy_a.js"): "nested",
        ("web/dyn_a.ts", "web/dyn_b.ts"): "nested",
        ("web/dyn_b.ts", "web/dyn_a.ts"): "top_level",
        ("web/c1.js", "web/c2.js"): "top_level",
        ("web/c2.js", "web/c1.js"): "top_level",
    }
    # External edges get a scope too, so the column is never NULL on a new analysis.
    assert query("SELECT count(*) AS n FROM edges WHERE snapshot_id = %s AND type = 'imports'"
                 " AND import_scope IS NULL", snap)[0]["n"] == 0
    assert query("SELECT count(*) AS n FROM edges WHERE snapshot_id = %s AND type <> 'imports'"
                 " AND import_scope IS NOT NULL", snap)[0]["n"] == 0


def test_tests_shown_adds_the_cycle_through_a_test_file(api, snap):
    v = view(api, snap, level="folder", exclude_tests="false")
    assert (v["total_files"], v["hidden_files"]) == (100, 0)
    assert [c["files"] for c in v["cycles"]] == [
        ["alpha/p.py", "beta/q.py"], ["core/engine.py", "tests/check_ring.py"],
        ["src/mapped/a.py", "src/mapped/b.py"], ["web/c1.js", "web/c2.js"]]
    pair = edges(v)
    assert counts(pair["file:core/engine.py", "file:tests/check_ring.py"]) == (1, 1, 0, 1)
    assert counts(pair["file:tests/check_ring.py", "file:core/engine.py"]) == (1, 1, 0, 1)
    assert nodes(v)["dir:scoring"]["file_count"] == 4
    assert nodes(v)["dir:scoring"]["finding_count"] == 2


def test_guesses_only_with_the_toggle_and_stay_dashed(api, snap):
    assert ("dir:gx", "dir:gy") not in edges(view(api, snap, level="folder"))
    v = view(api, snap, level="folder", min_confidence=0.5)
    edge = edges(v)["dir:gx", "dir:gy"]
    assert (edge["count"], edge["imports"], edge["calls"], edge["guess_calls"]) == (1, 0, 1, 1)
    assert (edge["confidence"], edge["guess"]) == (0.5, True)


def test_conservation_against_sql(api, snap):
    """Aggregated counts equal the edges between the subtrees, read directly with SQL."""
    v = view(api, snap, level="folder")
    tests = "NOT (sf.path = 'scoring/tests.py' OR df.path = 'scoring/tests.py')"
    for a, b in (("challenge", "scoring"), ("scoring", "challenge"), ("alpha", "beta")):
        direct = underlying(snap, f"sf.path LIKE %s AND df.path LIKE %s AND {tests}",
                            f"{a}/%", f"{b}/%")
        assert edges(v)[f"dir:{a}", f"dir:{b}"]["count"] == direct

    # Everything between visible files is either on an edge or inside a node.
    visible = ("NOT (sf.path LIKE 'tests/%%' OR df.path LIKE 'tests/%%') AND "
               "NOT (sf.path = 'scoring/tests.py' OR df.path = 'scoring/tests.py')")
    assert underlying(snap, visible) == (sum(e["count"] for e in v["edges"])
                                         + sum(n["internal_count"] for n in v["nodes"]))

    # And a folder's own view: on an edge, or across its boundary.
    big = view(api, snap, level="folder", root="big")
    inside = underlying(snap, "(sf.path LIKE 'big/%%' OR df.path LIKE 'big/%%')")
    assert inside == (sum(e["count"] for e in big["edges"])
                      + sum(n["internal_count"] + n["outside_in"] + n["outside_out"]
                            for n in big["nodes"]))


def test_overflow_exact(api, snap):
    v = view(api, snap, level="folder", root="big")
    # 61 modules, hub.py and sub/: 63 children. The folder first, then by connectivity, then path.
    assert v["hidden_count"] == 3 and len(v["nodes"]) == 61
    ids = [n["id"] for n in v["nodes"]]
    assert ids[0] == "dir:big/sub"
    assert ids[1:3] == ["file:big/hub.py", "file:big/mod_00.py"]
    assert ids[-2:] == ["file:big/mod_57.py", "more:big"]
    more = nodes(v)["more:big"]
    assert (more["label"], more["hidden_count"], more["file_count"], more["path"]) == (
        "3 more", 3, 3, "big")
    pair = edges(v)
    assert counts(pair["more:big", "file:big/hub.py"]) == (6, 3, 3, 0)
    assert counts(pair["dir:big/sub", "file:big/hub.py"]) == (2, 1, 1, 0)
    hub = nodes(v)["file:big/hub.py"]
    assert (hub["outside_in"], hub["outside_out"]) == (2, 1)  # top.py; deep/er/only.py


def test_file_level_of_a_folder(api, snap):
    v = view(api, snap, level="file", root="scoring")
    assert (v["level"], v["root"], v["hidden_files_under_root"]) == ("file", "scoring", 1)
    assert [n["label"] for n in v["nodes"]] == ["admin.py", "services.py", "signals.py"]
    by_id = nodes(v)
    assert v["edges"] == []
    assert by_id["file:scoring/services.py"]["outside_in"] == 2  # challenge/models.py
    assert by_id["file:scoring/signals.py"]["outside_out"] == 2  # challenge/models.py
    assert by_id["file:scoring/services.py"]["finding_count"] == 1

    # Recursive, and capped like any other view.
    big = view(api, snap, level="file", root="big")
    assert big["hidden_count"] == 4 and len(big["nodes"]) == 61
    assert big["nodes"][0]["id"] == "file:big/hub.py"
    assert "file:big/sub/leaf2.py" not in nodes(big)


def test_symbol_level_exact(api, snap):
    v = view(api, snap, level="symbol", root="challenge/models.py")
    assert (v["level"], v["root"], v["hidden_count"], v["hidden_symbols"]) == (
        "symbol", "challenge/models.py", 0, 0)
    assert v["breadcrumbs"] == [
        {"path": "", "label": ""}, {"path": "challenge", "label": "challenge"},
        {"path": "challenge/models.py", "label": "models.py"}]
    assert v["file"]["path"] == "challenge/models.py" and v["file"]["in_cycle"] is False
    assert sorted((n["label"], n["kind"], n["own"], n["path"]) for n in v["nodes"]) == [
        ("Challenge", "class", True, "challenge/models.py"),
        ("default_difficulty", "function", False, "scoring/services.py"),
        ("on_save", "function", False, "scoring/signals.py"),
        ("save", "method", True, "challenge/models.py"),
    ]
    label = {n["id"]: n["label"] for n in v["nodes"]}
    assert sorted((label[e["source"]], label[e["target"]], e["type"], e["confidence"])
                  for e in v["edges"]) == [
        ("Challenge", "save", "defines", 1.0),
        ("on_save", "Challenge", "calls", 1.0),
        ("save", "default_difficulty", "calls", 1.0),
    ]


def test_symbol_level_hides_test_neighbours_until_asked(api, snap):
    v = view(api, snap, level="symbol", root="scoring/services.py")
    assert v["hidden_symbols"] == 1
    assert "tests" not in {n["label"] for n in v["nodes"]}
    shown = view(api, snap, level="symbol", root="scoring/services.py", exclude_tests="false")
    assert shown["hidden_symbols"] == 0
    assert "scoring/tests.py" in {n["path"] for n in shown["nodes"]}
    # A test file can be opened by name even with tests hidden.
    assert view(api, snap, level="symbol", root="scoring/tests.py")["file"]["path"] == (
        "scoring/tests.py")


def test_bad_requests(api, snap):
    url = f"/snapshots/{snap}/graph"
    assert api.get(url, params={"level": "nope"}).status_code == 422
    assert api.get(url, params={"root": "big"}).status_code == 422  # root needs a level
    assert api.get(url, params={"level": "symbol"}).status_code == 422
    for level, root in (("folder", "nope"), ("folder", "top.py"), ("file", "../etc"),
                        ("folder", "big\\sub"), ("symbol", "nope.py"), ("symbol", "README.md"),
                        ("symbol", "big")):
        assert api.get(url, params={"level": level, "root": root}).status_code == 404, root
    assert api.get("/snapshots/999999/graph", params={"level": "folder"}).status_code == 404


def test_root_forms(api, snap):
    # `src` holds only mapped/: it opens as src/mapped. Slashes do not matter.
    for root in ("src", "src/", "/src/mapped", "src/mapped/"):
        assert view(api, snap, level="folder", root=root)["root"] == "src/mapped"
    # A real folder whose files are all hidden: empty, and says so.
    v = view(api, snap, level="folder", root="tests")
    assert (v["nodes"], v["hidden_files_under_root"]) == ([], 1)


def test_flat_graph_shape_unchanged(api, snap):
    """No level: the exact keys, in order, that the current UI reads."""
    body = api.get(f"/snapshots/{snap}/graph").json()
    assert list(body) == ["snapshot_id", "min_confidence", "exclude_tests", "hidden_files",
                          "nodes", "edges"]
    assert list(body["nodes"][0]) == ["id", "symbol_id", "path", "language", "loc",
                                      "external_imports", "unresolved_imports", "findings"]
    assert list(body["edges"][0]) == ["source", "target", "import", "calls", "confidence",
                                      "weight"]
    # And it has every file, uncapped by the view limit.
    assert len(body["nodes"]) == 98


def test_no_file_content_in_any_view(api, snap):
    for params in ({"level": "folder"}, {"level": "file"},
                   {"level": "symbol", "root": "scoring/tests.py"}):
        assert "fixture-not-a-real-password" not in json.dumps(view(api, snap, **params))


# Below: tests that change the database, after the read-only ones above.

def test_a_top_level_import_beats_a_nested_one_for_the_same_target(client, monkeypatch):
    from app.ingest import clone

    def fetch(url, sha, dest, timeout):
        dest.mkdir(parents=True)
        (dest / "a.py").write_text("def f():\n    import b\n\nimport b\n", encoding="utf-8")
        (dest / "b.py").write_text("if TYPE_CHECKING:\n    import a\n\ndef g():\n    import a\n",
                                   encoding="utf-8")

    monkeypatch.setattr(clone, "fetch_commit", fetch)
    client.post("/repos", json={"url": "https://github.com/example/dup"})
    rows = query("SELECT s.name, e.import_scope FROM edges e JOIN symbols s ON s.id = e.src_id"
                 " WHERE e.type = 'imports' ORDER BY s.name")
    assert [(r["name"], r["import_scope"]) for r in rows] == [("a", "top_level"), ("b", "nested")]


def test_old_snapshot_says_cycles_unknown_and_backfill_fills_them(client, monkeypatch, test_db):
    from app.ingest import clone
    from app.ingest.backfill import backfill_snapshot, snapshots_to_backfill

    monkeypatch.setattr(clone, "fetch_commit", _fetch)
    snap = client.post("/repos", json={"url": "https://github.com/example/old"}).json()[
        "snapshot_id"]
    with psycopg.connect(test_db, autocommit=True) as conn:
        conn.execute("UPDATE edges SET import_scope = NULL WHERE snapshot_id = %s", (snap,))
    v = view(client, snap, level="folder")
    assert v["cycles_available"] is False and v["cycles"] == []
    assert all(n["in_cycle"] is None for n in v["nodes"])
    flat_before = client.get(f"/snapshots/{snap}/graph").content
    assert snapshots_to_backfill() == [snap]

    result = backfill_snapshot(snap)
    assert result["changed"] == []  # the rebuild only added the scope
    assert "NULL" not in result["scopes"]
    assert snapshots_to_backfill() == []
    assert [c["id"] for c in view(client, snap, level="folder")["cycles"]] == [1, 2, 3]
    assert client.get(f"/snapshots/{snap}/graph").content == flat_before


def test_migration_adds_the_column_to_an_old_table_and_is_idempotent(test_db):
    sql = MIGRATION.read_text(encoding="utf-8")
    with psycopg.connect(test_db, autocommit=True) as conn:
        conn.execute("ALTER TABLE edges DROP COLUMN import_scope")
        conn.execute(sql)
        conn.execute(sql)
        (name,) = conn.execute(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'edges' AND column_name = 'import_scope'").fetchone()
        assert name == "import_scope"
