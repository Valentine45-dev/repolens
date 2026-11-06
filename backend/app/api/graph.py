"""Graph, file and symbol endpoints. Read-only; everything comes from the ingested snapshot."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import pool
from app.graph_map import (
    GUESS_BELOW,
    SYMBOL_EDGE_SITES,
    CodeFile,
    FileLink,
    MapSymbol,
    RepoMap,
    SymbolEdge,
    symbol_view,
)
from app.paths import is_test_path

router = APIRouter()

# Confidence is stored as REAL (0.9 -> 0.8999...), so compare and return it rounded.
MAX_SITES = 20
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
def graph(
    snapshot_id: int,
    min_confidence: float = Query(0.9, ge=0.0, le=1.0),
    exclude_tests: bool = True,
    level: Literal["folder", "file", "symbol"] | None = None,
    root: str | None = None,
) -> dict:
    """No `level`: the flat file graph. With `level`: one view of the folder-first map, see
    app/graph_map.py. `root` is a folder (level folder or file; default the repo root) or a file
    (level symbol)."""
    if level is None:
        if root is not None:
            raise HTTPException(status_code=422, detail="root needs a level.")
        return file_graph(snapshot_id, min_confidence, exclude_tests)
    if level == "symbol" and not root:
        raise HTTPException(status_code=422, detail="level=symbol needs a file as root.")
    return map_view(snapshot_id, level, (root or "").strip("/"), min_confidence, exclude_tests)


def load_repo_map(conn, snapshot_id: int, min_confidence: float, exclude_tests: bool) -> RepoMap:
    """Everything the folder and file views add up, read once per request."""
    code = conn.execute(
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
        "SELECT f.id, f.path, count(*) AS n FROM findings fi JOIN files f ON f.id = fi.file_id"
        " WHERE fi.snapshot_id = %s GROUP BY 1, 2",
        (snapshot_id,),
    ).fetchall()
    rows = conn.execute(
        f"SELECT sf.path AS source, df.path AS target, e.type, e.import_scope,"
        f" {CONFIDENCE} AS confidence, count(*) AS n FROM edges e"
        " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
        " JOIN files sf ON sf.id = s.file_id JOIN files df ON df.id = d.file_id"
        " WHERE e.snapshot_id = %s AND e.type IN ('imports', 'calls')"
        f" AND s.file_id <> d.file_id AND {CONFIDENCE} >= %s GROUP BY 1, 2, 3, 4, 5",
        (snapshot_id, min_confidence),
    ).fetchall()
    # An import edge without a scope was analysed before scopes existed.
    unknown_scope = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM edges WHERE snapshot_id = %s AND type = 'imports'"
        " AND import_scope IS NULL) AS unknown",
        (snapshot_id,),
    ).fetchone()["unknown"]

    counts = {(r["file_id"], r["kind"]): r["n"] for r in outside}
    finding_counts = {r["id"]: r["n"] for r in findings}
    files = [
        CodeFile(f["id"], f["symbol_id"], f["path"], f["language"], f["loc"],
                 counts.get((f["id"], "external"), 0), counts.get((f["id"], "unresolved"), 0),
                 finding_counts.get(f["id"], 0))
        for f in code
    ]
    code_ids = {f["id"] for f in code}
    other = {r["path"]: r["n"] for r in findings if r["id"] not in code_ids}

    links: dict[tuple[str, str], FileLink] = {}
    for r in rows:
        link = links.setdefault((r["source"], r["target"]), FileLink(r["source"], r["target"]))
        confidence = float(r["confidence"])
        link.confidence = max(link.confidence, confidence)
        if r["type"] == "imports":
            link.imports = 1
            link.top_level_import = r["import_scope"] == "top_level"
        else:
            link.calls += r["n"]
            if confidence < GUESS_BELOW:
                link.guess_calls += r["n"]
    return RepoMap(files, list(links.values()), other, exclude_tests=exclude_tests,
                   cycles_available=not unknown_scope)


def _load_symbols(conn, snapshot_id: int, file: CodeFile,
                  min_confidence: float) -> tuple[list[MapSymbol], list[SymbolEdge]]:
    own = conn.execute(
        "SELECT id FROM symbols WHERE file_id = %s AND kind IN"
        " ('module', 'class', 'function', 'method')",
        (file.id,),
    ).fetchall()
    own_ids = [r["id"] for r in own]
    rows = conn.execute(
        f"SELECT e.id, e.site_count, e.src_id, e.dst_id, e.type, {CONFIDENCE} AS confidence"
        " FROM edges e"
        " JOIN symbols s ON s.id = e.src_id JOIN symbols d ON d.id = e.dst_id"
        " WHERE e.snapshot_id = %s AND e.type IN ('calls', 'defines')"
        " AND s.file_id IS NOT NULL AND d.file_id IS NOT NULL"
        f" AND (e.src_id = ANY(%s) OR e.dst_id = ANY(%s)) AND {CONFIDENCE} >= %s",
        (snapshot_id, own_ids, own_ids, min_confidence),
    ).fetchall()
    lines: dict[int, list[int]] = {}
    for sr in conn.execute(
        "SELECT edge_id, line FROM edge_sites WHERE edge_id = ANY(%s) ORDER BY line",
        ([r["id"] for r in rows],),
    ):
        lines.setdefault(sr["edge_id"], []).append(sr["line"])
    ids = set(own_ids) | {r["src_id"] for r in rows} | {r["dst_id"] for r in rows}
    symbols = conn.execute(
        "SELECT s.id, s.kind, s.name, s.qualified_name, s.start_line, s.end_line, s.file_id,"
        " f.path, (SELECT count(*) FROM findings fi WHERE fi.symbol_id = s.id) AS findings"
        " FROM symbols s JOIN files f ON f.id = s.file_id WHERE s.id = ANY(%s)",
        (list(ids),),
    ).fetchall()
    return (
        [MapSymbol(s["id"], s["kind"], s["name"], s["qualified_name"], s["path"], s["file_id"],
                   s["start_line"], s["end_line"], s["findings"]) for s in symbols],
        [SymbolEdge(r["src_id"], r["dst_id"], r["type"], float(r["confidence"]),
                    tuple(lines.get(r["id"], ())[:SYMBOL_EDGE_SITES]), r["site_count"])
         for r in rows],
    )


def map_view(snapshot_id: int, level: str, root: str, min_confidence: float,
             exclude_tests: bool) -> dict:
    """404 for a path that is not a folder (or file, at symbol level) with code in this snapshot.
    A real folder whose files are all hidden is an empty view, which says how many are hidden."""
    with pool().connection() as conn:
        _require_done(conn, snapshot_id)
        repo = load_repo_map(conn, snapshot_id, min_confidence, exclude_tests)
        if level == "symbol":
            file = repo.all_by_path.get(root)
            if file is None:
                raise HTTPException(status_code=404, detail="File not found in this analysis.")
            symbols, edges = _load_symbols(conn, snapshot_id, file, min_confidence)
    if level == "symbol":
        view = symbol_view(repo, file, symbols, edges)
    else:
        if not repo.is_folder(root):
            raise HTTPException(status_code=404, detail="Folder not found in this analysis.")
        view = repo.folder_view(root) if level == "folder" else repo.file_view(root)
    return {"snapshot_id": snapshot_id, "min_confidence": min_confidence,
            "exclude_tests": exclude_tests, **view}


def file_graph(snapshot_id: int, min_confidence: float, exclude_tests: bool) -> dict:
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
            f"SELECT e.id AS edge_id, e.site_count, e.type, {CONFIDENCE} AS confidence, o.id,"
            " o.kind,"
            " o.name,"
            " o.qualified_name, o.file_id, o.start_line, o.end_line, f.path FROM edges e"
            f" JOIN symbols o ON o.id = e.{far} LEFT JOIN files f ON f.id = o.file_id"
            # `defines` (class -> method) is structure, not a dependency.
            f" WHERE {scope.format(near=near)} AND e.type IN ('imports', 'calls')"
            f" AND {CONFIDENCE} >= %s{same_file}"
            " ORDER BY f.path NULLS LAST, o.start_line NULLS FIRST, o.qualified_name, e.type",
            args,
        ).fetchall()

    with pool().connection() as conn:
        site_rows = conn.execute(
            "SELECT edge_id, line, round(confidence::numeric, 2) AS confidence FROM edge_sites"
            " WHERE edge_id = ANY(%s) ORDER BY line",
            ([r["edge_id"] for r in rows],),
        ).fetchall()
    sites_of: dict[int, list[dict]] = {}
    for sr in site_rows:
        sites_of.setdefault(sr["edge_id"], []).append({
            "line": sr["line"],
            "confidence": float(sr["confidence"]) if sr["confidence"] is not None else None,
        })

    items = []
    by_key: dict = {}
    for r in rows:
        key = (r["type"], r["id"])
        if key in by_key:  # several of our symbols -> the same one: list it once, sites merged
            by_key[key]["_edges"].append(r)
            continue
        # Where the import/call happens: in the other file when something depends on this symbol,
        # in this file otherwise.
        in_file = (r["file_id"], r["path"]) if direction == "in" else (sym["file_id"], sym["path"])
        item = {
            "type": r["type"],
            "confidence": float(r["confidence"]),
            "symbol": {k: r[k] for k in (
                "id", "kind", "name", "qualified_name", "file_id", "path", "start_line", "end_line"
            )},
            "site_file_id": in_file[0],
            "site_path": in_file[1],
            "_edges": [r],
        }
        by_key[key] = item
        items.append(item)
    for item in items:
        edges = item.pop("_edges")
        merged: dict[int, dict] = {}
        for r in edges:
            for site in sites_of.get(r["edge_id"], []):
                prev = merged.get(site["line"])
                if prev is None or (site["confidence"] or 0) > (prev["confidence"] or 0):
                    merged[site["line"]] = site
        known = all(r["site_count"] is not None for r in edges)
        lines = [merged[n] for n in sorted(merged)]
        item["sites"] = lines[:MAX_SITES]
        # None = this snapshot's edges predate sites (rebuild them); never 0 for "unknown".
        item["site_count"] = (
            max(len(lines), max(r["site_count"] for r in edges)) if known else None
        )
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
