"""Graph, file and symbol endpoints. Read-only; everything comes from the ingested snapshot."""

from fastapi import APIRouter, HTTPException, Query

from app.db import pool
from app.paths import is_test_path

router = APIRouter()

# Confidence is stored as REAL (0.9 -> 0.8999...), so compare and return it rounded.
CONFIDENCE = "round(e.confidence::numeric, 2)"


def _require_done(conn, snapshot_id: int) -> None:
    row = conn.execute(
        "SELECT status FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    if row["status"] != "done":
        raise HTTPException(status_code=409, detail="Snapshot is not ready yet.")


@router.get("/snapshots/{snapshot_id}/graph")
def file_graph(
    snapshot_id: int,
    min_confidence: float = Query(0.9, ge=0.0, le=1.0),
    exclude_tests: bool = True,
) -> dict:
    """File-level graph. External and unresolved imports are not nodes; each file carries
    counts of them instead. Call edges below `min_confidence` are left out."""
    with pool().connection() as conn:
        _require_done(conn, snapshot_id)
        files = conn.execute(
            "SELECT f.id, f.path, f.language, f.loc, s.id AS symbol_id FROM files f"
            " JOIN symbols s ON s.file_id = f.id AND s.kind = 'module'"
            " WHERE f.snapshot_id = %s ORDER BY f.path",
            (snapshot_id,),
        ).fetchall()
        outside = conn.execute(
            "SELECT s.file_id, d.kind, count(*) AS n FROM edges e"
            " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
            " WHERE e.snapshot_id = %s AND e.type = 'imports'"
            " AND d.kind IN ('external', 'unresolved') GROUP BY 1, 2",
            (snapshot_id,),
        ).fetchall()
        findings = conn.execute(
            "SELECT file_id, count(*) AS n FROM findings WHERE snapshot_id = %s GROUP BY 1",
            (snapshot_id,),
        ).fetchall()
        links = conn.execute(
            f"SELECT s.file_id AS source, d.file_id AS target, e.type, count(*) AS n,"
            f" max({CONFIDENCE}) AS confidence FROM edges e"
            " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
            f" WHERE e.snapshot_id = %s AND d.file_id IS NOT NULL AND s.file_id <> d.file_id"
            f" AND {CONFIDENCE} >= %s GROUP BY 1, 2, 3",
            (snapshot_id, min_confidence),
        ).fetchall()

    counts: dict[tuple[int, str], int] = {(r["file_id"], r["kind"]): r["n"] for r in outside}
    finding_counts = {r["file_id"]: r["n"] for r in findings}
    nodes = []
    for f in files:
        if exclude_tests and is_test_path(f["path"]):
            continue
        nodes.append({
            "id": f["id"],
            "symbol_id": f["symbol_id"],
            "path": f["path"],
            "language": f["language"],
            "loc": f["loc"],
            "external_imports": counts.get((f["id"], "external"), 0),
            "unresolved_imports": counts.get((f["id"], "unresolved"), 0),
            "findings": finding_counts.get(f["id"], 0),
        })
    shown = {n["id"] for n in nodes}

    edges: dict[tuple[int, int], dict] = {}
    for link in links:
        if link["source"] not in shown or link["target"] not in shown:
            continue
        edge = edges.setdefault((link["source"], link["target"]), {
            "source": link["source"], "target": link["target"],
            "import": False, "calls": 0, "confidence": 0.0,
        })
        if link["type"] == "imports":
            edge["import"] = True
        elif link["type"] == "calls":
            edge["calls"] += link["n"]
        edge["confidence"] = max(edge["confidence"], float(link["confidence"]))
    for edge in edges.values():
        edge["weight"] = int(edge["import"]) + edge["calls"]

    return {
        "snapshot_id": snapshot_id,
        "min_confidence": min_confidence,
        "exclude_tests": exclude_tests,
        "hidden_files": len(files) - len(nodes),
        "nodes": nodes,
        "edges": sorted(edges.values(), key=lambda e: (e["source"], e["target"])),
    }


@router.get("/snapshots/{snapshot_id}/files/{file_id}")
def file_detail(snapshot_id: int, file_id: int) -> dict:
    with pool().connection() as conn:
        _require_done(conn, snapshot_id)
        f = conn.execute(
            "SELECT id, path, language, loc, content FROM files"
            " WHERE id = %s AND snapshot_id = %s",
            (file_id, snapshot_id),
        ).fetchone()
        if f is None:
            raise HTTPException(status_code=404, detail="File not found.")
        symbols = conn.execute(
            "SELECT id, kind, name, qualified_name, start_line, end_line, signature"
            " FROM symbols WHERE file_id = %s ORDER BY start_line, id",
            (file_id,),
        ).fetchall()
        findings = conn.execute(
            "SELECT id, rule_id, severity, line, message, snippet FROM findings"
            " WHERE file_id = %s ORDER BY line, id",
            (file_id,),
        ).fetchall()
        outside = conn.execute(
            "SELECT d.kind, d.qualified_name FROM edges e"
            " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
            " WHERE s.file_id = %s AND e.type = 'imports' AND d.kind IN ('external', 'unresolved')"
            " ORDER BY d.qualified_name",
            (file_id,),
        ).fetchall()
    return {
        **f,
        "symbols": symbols,
        "findings": findings,
        "external_imports": [r["qualified_name"] for r in outside if r["kind"] == "external"],
        "unresolved_imports": [r["qualified_name"] for r in outside if r["kind"] == "unresolved"],
    }


def _neighbours(symbol_id: int, min_confidence: float, direction: str) -> dict:
    """direction 'in': what depends on the symbol; 'out': what it depends on. A module symbol
    stands for its whole file, so edges between symbols of that same file are left out."""
    near, far = ("dst_id", "src_id") if direction == "in" else ("src_id", "dst_id")
    with pool().connection() as conn:
        sym = conn.execute(
            "SELECT s.id, s.snapshot_id, s.file_id, s.kind, s.name, s.qualified_name,"
            " s.start_line, s.end_line, f.path FROM symbols s"
            " LEFT JOIN files f ON f.id = s.file_id WHERE s.id = %s",
            (symbol_id,),
        ).fetchone()
        if sym is None:
            raise HTTPException(status_code=404, detail="Symbol not found.")
        if sym["kind"] == "module":
            scope = "e.{near} IN (SELECT id FROM symbols WHERE file_id = %s)"
            scope_arg = sym["file_id"]
            same_file = " AND o.file_id IS DISTINCT FROM %s"
            args = (scope_arg, min_confidence, sym["file_id"])
        else:
            scope, scope_arg, same_file = "e.{near} = %s", symbol_id, ""
            args = (scope_arg, min_confidence)
        rows = conn.execute(
            f"SELECT e.type, {CONFIDENCE} AS confidence, o.id, o.kind, o.name,"
            " o.qualified_name, o.file_id, o.start_line, o.end_line, f.path FROM edges e"
            f" JOIN symbols o ON o.id = e.{far} LEFT JOIN files f ON f.id = o.file_id"
            # `defines` (class -> method) is structure, not a dependency.
            f" WHERE {scope.format(near=near)} AND e.type IN ('imports', 'calls')"
            f" AND {CONFIDENCE} >= %s{same_file}"
            " ORDER BY f.path NULLS LAST, o.start_line NULLS FIRST, o.qualified_name, e.type",
            args,
        ).fetchall()

    items = []
    seen = set()
    for r in rows:
        key = (r["type"], r["id"])
        if key in seen:  # several of our symbols -> the same one: list it once
            continue
        seen.add(key)
        items.append({
            "type": r["type"],
            "confidence": float(r["confidence"]),
            "symbol": {k: r[k] for k in (
                "id", "kind", "name", "qualified_name", "file_id", "path", "start_line", "end_line"
            )},
        })
    return {
        "symbol": sym,
        "min_confidence": min_confidence,
        "files": len({i["symbol"]["file_id"] for i in items if i["symbol"]["file_id"]}),
        "items": items,
    }


@router.get("/symbols/{symbol_id}/dependents")
def dependents(symbol_id: int, min_confidence: float = Query(0.9, ge=0.0, le=1.0)) -> dict:
    """What depends on this symbol: importers and callers."""
    return _neighbours(symbol_id, min_confidence, "in")


@router.get("/symbols/{symbol_id}/dependencies")
def dependencies(symbol_id: int, min_confidence: float = Query(0.9, ge=0.0, le=1.0)) -> dict:
    """What this symbol depends on: imports (incl. external/unresolved) and callees."""
    return _neighbours(symbol_id, min_confidence, "out")
