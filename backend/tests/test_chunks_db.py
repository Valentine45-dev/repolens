"""The embed stage on the fixture repo, with the stub embedder (EMBEDDER=stub in conftest)."""

import math

import pytest
from conftest import SECRET_VALUE, query

pytestmark = pytest.mark.db


@pytest.fixture
def snapshot(client):
    body = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def test_chunks_stored_with_ranges_and_vectors(snapshot):
    rows = query(
        "SELECT c.start_line, c.end_line, c.token_count, c.text, c.embedding::text AS v,"
        " s.kind, s.qualified_name, f.path, f.content FROM chunks c"
        " JOIN symbols s ON s.id = c.symbol_id JOIN files f ON f.id = s.file_id"
        " WHERE c.snapshot_id = %s",
        snapshot,
    )
    assert len(rows) > 20
    for r in rows:
        lines = r["content"].split("\n")
        assert 1 <= r["start_line"] <= r["end_line"] <= len(lines)
        assert r["text"] == "\n".join(lines[r["start_line"] - 1:r["end_line"]])
        assert 0 < r["token_count"] <= 256
        vector = [float(x) for x in r["v"].strip("[]").split(",")]
        assert len(vector) == 384
        assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0, abs_tol=1e-3)
    names = {r["qualified_name"] for r in rows}
    assert {"sample_app.service.create_user", "web/src/app.ts:App.render"} <= names
    assert any(r["kind"] == "module" for r in rows)  # top-level code chunks
    assert all(SECRET_VALUE not in r["text"] for r in rows)


def test_cosine_search_is_scoped_to_the_snapshot(snapshot):
    from app.qa.embed import get_embedder

    (q,) = get_embedder().embed(["create user with name and email"])
    literal = "[" + ",".join(f"{x:.6f}" for x in q) + "]"
    rows = query(
        "SELECT s.qualified_name, c.embedding <=> %s::vector AS distance FROM chunks c"
        " JOIN symbols s ON s.id = c.symbol_id WHERE c.snapshot_id = %s"
        " ORDER BY c.embedding <=> %s::vector LIMIT 3",
        literal, snapshot, literal,
    )
    assert rows[0]["qualified_name"] == "sample_app.service.create_user"
    assert rows[0]["distance"] <= rows[-1]["distance"]


def test_rerun_replaces_chunks(client, snapshot):
    (before,) = query("SELECT count(*) AS n FROM chunks WHERE snapshot_id = %s", snapshot)
    from app.db import pool

    with pool().connection() as conn:
        conn.execute("UPDATE jobs SET status = 'failed' WHERE snapshot_id = %s", (snapshot,))
    client.post("/repos", json={"url": "https://github.com/example/sample"})
    (after,) = query("SELECT count(*) AS n FROM chunks WHERE snapshot_id = %s", snapshot)
    assert after["n"] == before["n"]  # delete-then-insert, no duplicates
