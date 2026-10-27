"""Findings and the rule catalogue. Findings are rule-based and can miss issues or flag safe code;
the UI says so. This API never turns "no rows" into "safe": an unfinished analysis is a 409."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import pool
from app.detect.rules import RULES

router = APIRouter()

SEVERITY_RANK = "CASE f.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"


@router.get("/rules")
def rules() -> list[dict]:
    return [
        {
            "id": r.id,
            "language": r.language,
            "severity": r.severity,
            "title": r.title,
            "checks": r.looks_for,
            "why": r.why,
            "false_positive": f"Possible false positive if {r.false_positive}",
        }
        for r in RULES.values()
    ]


def _require_detected(conn, snapshot_id: int) -> None:
    """404 for an unknown snapshot; 409 (with the reason) while detection has not finished."""
    row = conn.execute(
        "SELECT status, stage FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    if row["status"] == "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Detection did not run: the analysis failed during {row['stage']}.",
        )
    if row["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Detection has not finished yet (current stage: {row['stage']}).",
        )


@router.get("/snapshots/{snapshot_id}/findings")
def findings(
    snapshot_id: int,
    severity: Literal["high", "medium", "low"] | None = None,
    rule: str | None = None,
    language: Literal["python", "javascript", "typescript"] | None = None,
    path_prefix: str | None = None,
    in_test: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    if rule is not None and rule not in RULES:
        raise HTTPException(status_code=422, detail=f"Unknown rule: {rule}")

    where = ["f.snapshot_id = %s"]
    args: list = [snapshot_id]
    for column, value in (("f.severity", severity), ("f.rule_id", rule),
                          ("fi.language", language), ("f.in_test", in_test)):
        if value is not None:
            where.append(f"{column} = %s")
            args.append(value)
    if path_prefix:
        where.append("starts_with(fi.path, %s)")
        args.append(path_prefix)
    where_sql = " AND ".join(where)

    with pool().connection() as conn:
        _require_detected(conn, snapshot_id)
        total = conn.execute(
            f"SELECT count(*) AS n FROM findings f JOIN files fi ON fi.id = f.file_id"
            f" WHERE {where_sql}",
            args,
        ).fetchone()["n"]
        items = conn.execute(
            "SELECT f.id, f.rule_id, f.severity, f.message, f.file_id, fi.path, fi.language,"
            " f.line, CASE WHEN s.kind = 'module' THEN NULL ELSE s.name END AS symbol,"
            " f.snippet, f.in_test, coalesce(f.symbol_id, m.id) AS node_id"
            " FROM findings f JOIN files fi ON fi.id = f.file_id"
            " LEFT JOIN symbols s ON s.id = f.symbol_id"
            " LEFT JOIN symbols m ON m.file_id = f.file_id AND m.kind = 'module'"
            f" WHERE {where_sql}"
            # Severity by rank, not alphabetically; byte order for paths so it is predictable.
            f" ORDER BY {SEVERITY_RANK}, fi.path COLLATE \"C\", f.line, f.id"
            " LIMIT %s OFFSET %s",
            [*args, limit, offset],
        ).fetchall()
        by_severity = conn.execute(
            "SELECT severity, count(*) AS n FROM findings WHERE snapshot_id = %s GROUP BY 1",
            (snapshot_id,),
        ).fetchall()
        by_rule = conn.execute(
            "SELECT rule_id, count(*) AS n FROM findings WHERE snapshot_id = %s"
            " GROUP BY 1 ORDER BY 1",
            (snapshot_id,),
        ).fetchall()

    severities = {"high": 0, "medium": 0, "low": 0}
    severities.update({r["severity"]: r["n"] for r in by_severity})
    return {
        "snapshot_id": snapshot_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
        # Over the whole snapshot, not the filtered set: tab badge and filter menus.
        "counts": {
            "total": sum(severities.values()),
            "by_severity": severities,
            "by_rule": {r["rule_id"]: r["n"] for r in by_rule},
        },
    }
