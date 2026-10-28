"""Graph, file and symbol endpoints on the ingested fixture repo."""

import pytest
from conftest import query

from app.paths import is_test_path

pytestmark = pytest.mark.db


@pytest.fixture
def snapshot(client):
    body = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def module_id(path: str) -> int:
    (row,) = query("SELECT s.id FROM symbols s JOIN files f ON f.id = s.file_id"
                   " WHERE f.path = %s AND s.kind = 'module'", path)
    return row["id"]


def symbol_id(qualified_name: str) -> int:
    (row,) = query("SELECT id FROM symbols WHERE qualified_name = %s", qualified_name)
    return row["id"]


def by_path(graph):
    paths = {n["id"]: n["path"] for n in graph["nodes"]}
    edges = {(paths[e["source"]], paths[e["target"]]): e for e in graph["edges"]}
    return {n["path"]: n for n in graph["nodes"]}, edges


def items(body):
    return sorted((i["type"], i["symbol"]["qualified_name"], i["confidence"])
                  for i in body["items"])


def test_is_test_path():
    for path in ["tests/x.py", "a/test/b.js", "src/__tests__/a.ts", "examples/app.js",
                 "src/a.test.ts", "src/a.spec.tsx", "lib/math.spec.ts",
                 "test_app.py", "pkg/test_models.py", "pkg/models_test.py"]:
        assert is_test_path(path), path
    for path in ["src/app.ts", "test.js", "src/testing/x.py", "src/latest.py", "spec.ts",
                 "pkg/testing.py", "pkg/contest.py", "test_utils.js"]:
        assert not is_test_path(path), path


def test_graph_defaults_hide_tests_and_externals(client, snapshot):
    g = client.get(f"/snapshots/{snapshot}/graph").json()
    assert (g["min_confidence"], g["exclude_tests"], g["hidden_files"]) == (0.9, True, 2)
    nodes, edges = by_path(g)
    assert sorted(nodes) == [
        "sample_app/__init__.py", "sample_app/broken.py", "sample_app/models.py",
        "sample_app/service.py", "sample_app/settings.py",
        "web/src/app.ts", "web/src/legacy.cjs", "web/src/lib/index.ts", "web/src/lib/math.ts",
        "web/src/server.js", "web/src/util.js", "web/src/view.tsx",
    ]
    app = nodes["web/src/app.ts"]
    assert (app["external_imports"], app["unresolved_imports"], app["language"]) == (
        2, 1, "typescript"
    )
    assert nodes["sample_app/broken.py"]["unresolved_imports"] == 2
    assert nodes["sample_app/settings.py"]["findings"] == 1

    summary = {k: (e["import"], e["calls"], e["weight"], e["confidence"]) for k, e in edges.items()}
    assert summary == {
        ("sample_app/__init__.py", "sample_app/models.py"): (True, 0, 1, 1.0),
        ("sample_app/__init__.py", "sample_app/service.py"): (True, 0, 1, 1.0),
        ("sample_app/__init__.py", "sample_app/settings.py"): (True, 0, 1, 1.0),
        ("sample_app/service.py", "sample_app/models.py"): (True, 1, 2, 1.0),
        ("web/src/app.ts", "web/src/lib/index.ts"): (True, 1, 2, 1.0),
        ("web/src/app.ts", "web/src/lib/math.ts"): (True, 2, 3, 1.0),
        ("web/src/app.ts", "web/src/view.tsx"): (True, 0, 1, 1.0),
        ("web/src/legacy.cjs", "web/src/util.js"): (True, 1, 2, 1.0),
        ("web/src/lib/index.ts", "web/src/lib/math.ts"): (True, 0, 1, 1.0),
        ("web/src/view.tsx", "web/src/lib/index.ts"): (True, 1, 2, 1.0),
    }


def test_graph_with_tests(client, snapshot):
    g = client.get(f"/snapshots/{snapshot}/graph", params={"exclude_tests": "false"}).json()
    nodes, edges = by_path(g)
    assert g["hidden_files"] == 0 and len(nodes) == 14
    assert edges[("tests/check_service.py", "sample_app/service.py")]["calls"] == 1
    assert edges[("web/src/lib/math.spec.ts", "web/src/lib/math.ts")]["weight"] == 2


def test_graph_min_confidence_and_dashed_guesses(client, snapshot):
    from app.db import pool

    # Two guessed (0.5) calls: one alongside an import, one between files with nothing else.
    with pool().connection() as conn:
        for src, dst in [
            ("sample_app.service.main", "sample_app.models.User.display_name"),
            ("web/src/util.js:trim", "web/src/server.js:res.send"),
        ]:
            conn.execute(
                "INSERT INTO edges (snapshot_id, src_id, dst_id, type, confidence)"
                " VALUES (%s, %s, %s, 'calls', 0.5)",
                (snapshot, symbol_id(src), symbol_id(dst)),
            )
    _, strict = by_path(client.get(f"/snapshots/{snapshot}/graph").json())
    assert strict[("sample_app/service.py", "sample_app/models.py")]["calls"] == 1
    assert ("web/src/util.js", "web/src/server.js") not in strict

    _, loose = by_path(client.get(f"/snapshots/{snapshot}/graph",
                                  params={"min_confidence": 0.5}).json())
    with_import = loose[("sample_app/service.py", "sample_app/models.py")]
    assert (with_import["calls"], with_import["confidence"]) == (2, 1.0)
    guess_only = loose[("web/src/util.js", "web/src/server.js")]
    assert (guess_only["import"], guess_only["calls"], guess_only["confidence"]) == (
        False, 1, 0.5
    )


def test_graph_errors(client, snapshot):
    assert client.get("/snapshots/999/graph").status_code == 404
    assert client.get(f"/snapshots/{snapshot}/graph",
                      params={"min_confidence": 2}).status_code == 422


def test_graph_not_ready_is_409(client, monkeypatch):
    from app.ingest import clone

    def failing_fetch(url, sha, dest, timeout):
        raise clone.CloneError("nope")

    monkeypatch.setattr(clone, "fetch_commit", failing_fetch)
    body = client.post("/repos", json={"url": "https://github.com/example/broken"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/graph").status_code == 409


def test_file_detail(client, snapshot):
    (f,) = query("SELECT id FROM files WHERE path = 'web/src/app.ts'")
    d = client.get(f"/snapshots/{snapshot}/files/{f['id']}").json()
    assert d["path"] == "web/src/app.ts"
    assert d["content"].startswith('import fs from "node:fs";')
    assert "web/src/app.ts:App.render" in {s["qualified_name"] for s in d["symbols"]}
    assert d["symbols"][0]["kind"] == "module"
    assert d["external_imports"] == ["fs", "react"]
    assert d["unresolved_imports"] == ["web/src/missing"]

    (s,) = query("SELECT id FROM files WHERE path = 'sample_app/settings.py'")
    settings = client.get(f"/snapshots/{snapshot}/files/{s['id']}").json()
    assert "fixture-not-a-real-password" not in settings["content"]
    assert [(x["rule_id"], x["line"]) for x in settings["findings"]] == [("hardcoded-secret", 5)]

    assert client.get(f"/snapshots/{snapshot}/files/999999").status_code == 404


def test_module_dependents_cover_the_whole_file(client, snapshot):
    body = client.get(f"/symbols/{module_id('sample_app/service.py')}/dependents").json()
    assert items(body) == [
        ("calls", "tests.check_service.check_create_user", 1.0),  # calls create_user
        ("imports", "sample_app", 1.0),  # sample_app/__init__.py
        ("imports", "tests.check_service", 1.0),
    ]
    assert body["files"] == 2


def test_module_dependencies_include_outside_imports(client, snapshot):
    body = client.get(f"/symbols/{module_id('web/src/app.ts')}/dependencies").json()
    assert items(body) == [
        ("calls", "web/src/lib/index.ts:formatName", 1.0),
        ("calls", "web/src/lib/math.ts:add", 1.0),
        ("calls", "web/src/lib/math.ts:double", 1.0),
        ("imports", "fs", 1.0),
        ("imports", "react", 1.0),
        ("imports", "web/src/lib/index.ts", 1.0),
        ("imports", "web/src/lib/math.ts", 1.0),
        ("imports", "web/src/missing", 1.0),
        ("imports", "web/src/view.tsx", 1.0),
    ]


def test_symbol_dependents_respect_min_confidence(client, snapshot):
    render = symbol_id("web/src/app.ts:App.render")
    assert client.get(f"/symbols/{render}/dependents").json()["items"] == []
    loose = client.get(f"/symbols/{render}/dependents", params={"min_confidence": 0.5}).json()
    assert items(loose) == [("calls", "web/src/app.ts:main", 0.5)]
    deps = client.get(f"/symbols/{render}/dependencies").json()
    assert {i["symbol"]["name"] for i in deps["items"]} == {"formatName", "add", "double"}
    assert client.get("/symbols/999999/dependents").status_code == 404
