"""Rebuild the edges of finished snapshots from their stored files, to fill edges.import_scope and
edges.site_count / edge_sites.

No clone, no embedding, no LLM: the parse stage reads the same stored (redacted) text. Chunks and
findings are not touched; only import, call and defines edges and the external/unresolved symbols
are replaced, by the edges stage's own transaction. Reports any edge that is not the same after.

Run with the API stopped:
    cd backend; uv run --env-file ../.env python -m app.ingest.backfill
"""

import sys
from collections import Counter

from app.db import close_pool, open_pool, pool
from app.ingest.pipeline import parse_stored, store_edges

# Symbol ids of external/unresolved targets change on a rebuild, so compare by name.
_SIGNATURE = (
    "SELECT sf.path AS src_path, s.qualified_name AS src, df.path AS dst_path,"
    " d.kind AS dst_kind, d.qualified_name AS dst, e.type, round(e.confidence::numeric, 2) AS c"
    " FROM edges e JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
    " LEFT JOIN files sf ON sf.id = s.file_id LEFT JOIN files df ON df.id = d.file_id"
    " WHERE e.snapshot_id = %s"
)


def edge_signature(snapshot_id: int) -> Counter:
    with pool().connection() as conn:
        rows = conn.execute(_SIGNATURE, (snapshot_id,)).fetchall()
    return Counter(tuple(r.values()) for r in rows)


def backfill_snapshot(snapshot_id: int) -> dict:
    """Returns edge counts and scope counts; `changed` lists edges gained or lost (none expected:
    the rebuild must only add the scope)."""
    before = edge_signature(snapshot_id)
    store_edges(snapshot_id, parse_stored(snapshot_id))
    after = edge_signature(snapshot_id)
    changed = list(((after - before) + (before - after)).elements())
    with pool().connection() as conn:
        scopes = conn.execute(
            "SELECT coalesce(import_scope, 'NULL') AS scope, count(*) AS n FROM edges"
            " WHERE snapshot_id = %s AND type = 'imports' GROUP BY 1 ORDER BY 1",
            (snapshot_id,),
        ).fetchall()
    return {"snapshot_id": snapshot_id, "edges": sum(after.values()), "changed": changed,
            "scopes": {r["scope"]: r["n"] for r in scopes}}


def snapshots_to_backfill() -> list[int]:
    """Finished snapshots with an import edge without a scope, or an import/call edge without
    site_count (analysed before sites existed)."""
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT st.snapshot_id FROM snapshot_status st"
            " JOIN edges e ON e.snapshot_id = st.snapshot_id"
            " WHERE st.status = 'done' AND ((e.type = 'imports' AND e.import_scope IS NULL)"
            " OR (e.type IN ('imports', 'calls') AND e.site_count IS NULL))"
            " ORDER BY 1"
        ).fetchall()
    return [r["snapshot_id"] for r in rows]


def main() -> int:
    open_pool()
    try:
        with pool().connection() as conn:
            busy = conn.execute(
                "SELECT count(*) AS n FROM jobs WHERE status IN ('queued', 'running')"
            ).fetchone()["n"]
        if busy:
            print(f"{busy} job(s) queued or running; stop the API first.")
            return 1
        failed = False
        for snapshot_id in snapshots_to_backfill():
            result = backfill_snapshot(snapshot_id)
            print(result["snapshot_id"], "edges", result["edges"], "imports", result["scopes"],
                  "changed", len(result["changed"]))
            for edge in result["changed"]:
                failed = True
                print("  changed:", edge)
        return 1 if failed else 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
