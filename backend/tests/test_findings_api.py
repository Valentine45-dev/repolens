"""GET /snapshots/{id}/findings and GET /rules, on the detector fixtures ingested as a repo
(three languages, all severities, a secret in src/ and one in tests/)."""

import pytest
from conftest import SECRET_VALUE, query

pytestmark = pytest.mark.db

RANK = {"high": 0, "medium": 1, "low": 2}


def get_all(client, snapshot, **params) -> list[dict]:
    """Every item, page by page (limit 7, so pages break mid-severity)."""
    items, offset = [], 0
    while True:
        body = client.get(f"/snapshots/{snapshot}/findings",
                          params={**params, "limit": 7, "offset": offset}).json()
        items += body["items"]
        offset += 7
        if offset >= body["total"]:
            return items


def test_order_is_severity_rank_then_path_line_id(client, detector_repo):
    items = get_all(client, detector_repo)
    keys = [(RANK[i["severity"]], i["path"].encode(), i["line"], i["id"]) for i in items]
    assert keys == sorted(keys)
    severities = [i["severity"] for i in items]
    assert severities.index("medium") > severities.index("high")  # not alphabetical
    assert severities[-1] == "low"


def test_pages_neither_overlap_nor_skip(client, detector_repo):
    whole = client.get(f"/snapshots/{detector_repo}/findings", params={"limit": 200}).json()
    paged = get_all(client, detector_repo)
    assert [i["id"] for i in paged] == [i["id"] for i in whole["items"]]
    assert len(paged) == whole["total"] == len({i["id"] for i in paged})
    (row,) = query("SELECT count(*) AS n FROM findings WHERE snapshot_id = %s", detector_repo)
    assert whole["total"] == row["n"]


def test_item_shape_and_node_id(client, detector_repo):
    items = get_all(client, detector_repo)
    item = next(i for i in items if i["rule_id"] == "py-eval-exec")
    assert set(item) == {"id", "rule_id", "severity", "message", "file_id", "path", "language",
                         "line", "symbol", "snippet", "in_test", "node_id"}
    assert (item["path"], item["language"], item["line"], item["symbol"]) == (
        "py_positive.py", "python", 9, "handler"
    )
    (sym,) = query("SELECT id FROM symbols WHERE qualified_name = 'py_positive.handler'")
    assert item["node_id"] == sym["id"]

    # A module-level secret has no symbol: node_id falls back to the file's module symbol.
    secret = next(i for i in items if i["path"] == "src/config.py")
    (mod,) = query("SELECT s.id FROM symbols s JOIN files f ON f.id = s.file_id"
                   " WHERE f.path = 'src/config.py' AND s.kind = 'module'"
                   " AND f.snapshot_id = %s", detector_repo)
    assert (secret["symbol"], secret["node_id"]) == (None, mod["id"])


@pytest.mark.parametrize(
    "params, check",
    [
        ({"severity": "low"}, lambda i: i["severity"] == "low"),
        ({"rule": "js-eval"}, lambda i: i["rule_id"] == "js-eval"),
        ({"language": "typescript"}, lambda i: i["path"] == "ts_positive.ts"),
        ({"path_prefix": "src/"}, lambda i: i["path"].startswith("src/")),
        ({"in_test": "true"}, lambda i: i["in_test"] and i["path"].startswith("tests/")),
        ({"in_test": "false"}, lambda i: not i["in_test"]),
    ],
)
def test_filters(client, detector_repo, params, check):
    body = client.get(f"/snapshots/{detector_repo}/findings", params=params).json()
    assert body["total"] > 0 and body["total"] == len(get_all(client, detector_repo, **params))
    assert all(check(i) for i in body["items"])
    # Counts describe the whole snapshot, whatever the filter.
    whole = client.get(f"/snapshots/{detector_repo}/findings").json()
    assert body["counts"] == whole["counts"]


def test_counts(client, detector_repo):
    counts = client.get(f"/snapshots/{detector_repo}/findings").json()["counts"]
    assert counts["total"] == sum(counts["by_severity"].values())
    assert counts["by_rule"]["hardcoded-secret"] == 2
    assert counts["by_severity"]["medium"] == counts["by_rule"]["js-inner-html"]


def test_test_files_included_and_marked(client, detector_repo):
    items = get_all(client, detector_repo)
    tests = [i for i in items if i["in_test"]]
    assert [(i["path"], i["rule_id"], i["severity"]) for i in tests] == [
        ("tests/conftest.py", "hardcoded-secret", "low")
    ]


def test_raw_secret_never_in_any_response(client, detector_repo):
    responses = [client.get("/rules").text]
    for params in [{}, {"rule": "hardcoded-secret"}, {"in_test": "true"}]:
        responses.append(
            client.get(f"/snapshots/{detector_repo}/findings", params=params).text
        )
    assert all(SECRET_VALUE not in r for r in responses)
    assert any("[REDACTED]" in r for r in responses)


@pytest.mark.parametrize(
    "params",
    [{"severity": "critical"}, {"rule": "no-such-rule"}, {"limit": 201}, {"limit": 0},
     {"offset": -1}, {"offset": 10**20}, {"language": "go"}],
)
def test_invalid_params_are_422(client, detector_repo, params):
    r = client.get(f"/snapshots/{detector_repo}/findings", params=params)
    assert r.status_code == 422, r.text


def test_unknown_snapshot_is_404(client, detector_repo):
    assert client.get("/snapshots/999999/findings").status_code == 404


def test_not_ready_says_so(client, monkeypatch):
    from app.ingest import clone

    def failing(url, sha, dest, timeout):
        raise clone.CloneError("not our ref")

    monkeypatch.setattr(clone, "fetch_commit", failing)
    body = client.post("/repos", json={"url": "https://github.com/example/broken"}).json()
    r = client.get(f"/snapshots/{body['snapshot_id']}/findings")
    assert r.status_code == 409
    assert r.json()["detail"] == "Detection did not run: the analysis failed during fetch."

    # Still running.
    from app.db import pool

    with pool().connection() as conn:
        conn.execute("UPDATE jobs SET status = 'running', stage = 'parse' WHERE snapshot_id = %s",
                     (body["snapshot_id"],))
    r = client.get(f"/snapshots/{body['snapshot_id']}/findings")
    assert r.status_code == 409
    assert "has not finished yet (current stage: parse)" in r.json()["detail"]


def test_rules_catalogue(client):
    rules = client.get("/rules").json()
    ids = [r["id"] for r in rules]
    assert "hardcoded-secret" in ids and "js-sql-string" in ids and "py-bare-except" in ids
    for r in rules:
        assert set(r) == {"id", "language", "severity", "title", "checks", "why",
                          "false_positive"}
        assert r["false_positive"].startswith("Possible false positive if ")
