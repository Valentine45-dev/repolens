"""Reachability for one finding, and the entry points it was worked out from. A path is a way that
code we analysed could run, found by following imports and name-based calls; "no path found" is
not "unused" and a path is not proof the code runs. Entry points are found by pattern and can be
missed."""

from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from app.api.findings import _require_detected
from app.db import pool
from app.reach.graph import NONE, NOT_CHECKED
from app.reach.load import get_reach

router = APIRouter()


def _node(reach, paths: dict[int, str], symbol_id: int) -> dict:
    s = reach.symbols[symbol_id]
    return {"symbol_id": s.id, "symbol_kind": s.kind, "name": s.name, "file_id": s.file_id,
            "path": paths.get(s.file_id), "start_line": s.start, "end_line": s.end}


@router.get("/snapshots/{snapshot_id}/findings/{finding_id}/reach")
def finding_reach(snapshot_id: int, finding_id: int) -> dict:
    with pool().connection() as conn:
        _require_detected(conn, snapshot_id)
        row = conn.execute(
            "SELECT f.file_id, f.line FROM findings f"
            " WHERE f.id = %s AND f.snapshot_id = %s", (finding_id, snapshot_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Finding not found.")
        paths = {r["id"]: r["path"] for r in conn.execute(
            "SELECT id, path FROM files WHERE snapshot_id = %s", (snapshot_id,))}
    reach = get_reach(snapshot_id)
    tier = reach.tier(row["file_id"], row["line"])
    result = {"tier": tier, "entry_class": None, "entry": None, "path": []}
    if tier in (NOT_CHECKED, NONE):
        return result
    symbol_id = reach.symbol_at(row["file_id"], row["line"])
    steps = reach.path_to(symbol_id)
    seed = reach.seed_for(symbol_id)
    result["entry_class"] = reach.entry_class_of_symbol(symbol_id)
    result["entry"] = {"kind": seed.kind, "label": seed.label, "detail": seed.detail}
    result["path"] = [{**_node(reach, paths, st.symbol_id), "via": st.via, "guess": st.guess}
                      for st in steps]
    return result


@router.get("/snapshots/{snapshot_id}/reach/entry-points")
def entry_points(snapshot_id: int, limit: int = Query(200, ge=1, le=1000)) -> dict:
    with pool().connection() as conn:
        _require_detected(conn, snapshot_id)
        paths = {r["id"]: r["path"] for r in conn.execute(
            "SELECT id, path FROM files WHERE snapshot_id = %s", (snapshot_id,))}
    reach = get_reach(snapshot_id)
    seeds = sorted(reach.seeds, key=lambda s: (s.kind, s.label, s.symbol_id))
    return {
        "total": len(seeds),
        "by_kind": dict(sorted(Counter(s.kind for s in seeds).items())),
        "items": [{"kind": s.kind, "label": s.label, "detail": s.detail,
                   **_node(reach, paths, s.symbol_id)} for s in seeds[:limit]],
    }
