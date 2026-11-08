"""Findings and the rule catalogue. Findings are rule-based and can miss issues or flag safe code;
the UI says so. This API never turns "no rows" into "safe": an unfinished analysis is a 409."""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.db import pool
from app.detect.rules import CATEGORIES, RULE_IDS_BY_CATEGORY, RULES
from app.reach.graph import TIER_RANK
from app.reach.load import get_reach

log = logging.getLogger(__name__)

router = APIRouter()

SEVERITY_RANK = "CASE f.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END"


@router.get("/rules")
def rules() -> list[dict]:
    return [
        {
            "id": r.id,
            "language": r.language,
            "severity": r.severity,
            "category": r.category,
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


def _reachability_page(conn, snapshot_id, select, where_sql, args, limit, offset):
    """The page of findings in reachability order: placeholders last, then the tier (solid path,
    then guess path and not checked, then no path found), then the usual severity, path, line, id.
    The tier is worked out in Python (app/reach), so the order is built from the filtered rows'
    keys and only the requested page is read in full. Falls back to the usual order if the
    reachability picture cannot be built."""
    try:
        reach = get_reach(snapshot_id)
    except Exception:  # noqa: BLE001 - any failure must leave the list usable
        log.exception("reachability failed for snapshot %s", snapshot_id)
        reach = None
    if reach is None:
        rows = conn.execute(
            f"{select} WHERE {where_sql} ORDER BY f.placeholder, {SEVERITY_RANK},"
            ' fi.path COLLATE "C", f.line, f.id LIMIT %s OFFSET %s', [*args, limit, offset]
        ).fetchall()
        for row in rows:
            row["reach_tier"] = None
            row["reach_entry_class"] = None
        return rows, True
    keys = conn.execute(
        f"SELECT f.id, f.file_id, f.line, f.placeholder, {SEVERITY_RANK} AS sev, fi.path"
        f" FROM findings f JOIN files fi ON fi.id = f.file_id WHERE {where_sql}", args
    ).fetchall()
    tiers = {k["id"]: reach.tier(k["file_id"], k["line"]) for k in keys}
    keys.sort(key=lambda k: (k["placeholder"], TIER_RANK[tiers[k["id"]]], k["sev"],
                             k["path"].encode(), k["line"] or 0, k["id"]))
    ids = [k["id"] for k in keys[offset:offset + limit]]
    rows = {r["id"]: r for r in conn.execute(
        f"{select} WHERE f.id = ANY(%s)", [ids]).fetchall()}
    page = [rows[i] for i in ids if i in rows]
    classes = {k["id"]: reach.entry_class(k["file_id"], k["line"])
               for k in keys[offset:offset + limit]}
    for row in page:
        row["reach_tier"] = tiers[row["id"]]
        row["reach_entry_class"] = classes[row["id"]]
    return page, False


@router.get("/snapshots/{snapshot_id}/findings")
def findings(
    snapshot_id: int,
    severity: Literal["high", "medium", "low"] | None = None,
    rule: str | None = None,
    language: Literal["python", "javascript", "typescript"] | None = None,
    path_prefix: str | None = None,
    in_test: bool | None = None,
    category: Literal["security", "quality"] | None = None,
    placeholder: bool | None = None,
    sort: Literal["default", "reachability"] = "default",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),  # larger overflows SQL: a 500
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
    if category is not None:
        where.append("f.rule_id = ANY(%s)")
        args.append(RULE_IDS_BY_CATEGORY[category])
    if placeholder is not None:
        where.append("f.placeholder = %s")
        args.append(placeholder)
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
        select = (
            "SELECT f.id, f.rule_id, f.severity, f.message, f.file_id, fi.path, fi.language,"
            " f.line, CASE WHEN s.kind = 'module' THEN NULL ELSE s.name END AS symbol,"
            " f.snippet, f.in_test, f.in_docs, f.placeholder, f.template_value,"
            " coalesce(f.symbol_id, m.id) AS node_id"
            " FROM findings f JOIN files fi ON fi.id = f.file_id"
            " LEFT JOIN symbols s ON s.id = f.symbol_id"
            " LEFT JOIN symbols m ON m.file_id = f.file_id AND m.kind = 'module'"
        )
        # Probable placeholders last; then severity by rank, not alphabetically; byte order
        # for paths so it is predictable.
        default_order = (f"f.placeholder, {SEVERITY_RANK}, fi.path COLLATE \"C\", f.line, f.id")
        if sort == "reachability":
            items, reach_failed = _reachability_page(
                conn, snapshot_id, select, where_sql, args, limit, offset)
        else:
            items = conn.execute(
                f"{select} WHERE {where_sql} ORDER BY {default_order} LIMIT %s OFFSET %s",
                [*args, limit, offset],
            ).fetchall()
            reach_failed = False
            for item in items:
                item["reach_tier"] = None
                item["reach_entry_class"] = None
        by_severity = conn.execute(
            "SELECT severity, count(*) AS n FROM findings WHERE snapshot_id = %s GROUP BY 1",
            (snapshot_id,),
        ).fetchall()
        by_rule = conn.execute(
            "SELECT rule_id, count(*) AS n FROM findings WHERE snapshot_id = %s"
            " GROUP BY 1 ORDER BY 1",
            (snapshot_id,),
        ).fetchall()
        flags = conn.execute(
            "SELECT count(*) FILTER (WHERE placeholder) AS placeholders,"
            " count(*) FILTER (WHERE in_docs) AS documentation,"
            " count(*) FILTER (WHERE template_value) AS template_values FROM findings"
            " WHERE snapshot_id = %s",
            (snapshot_id,),
        ).fetchone()
        note = conn.execute(
            "SELECT quality_note FROM jobs WHERE snapshot_id = %s ORDER BY id DESC LIMIT 1",
            (snapshot_id,),
        ).fetchone()

    for item in items:
        item["category"] = RULES[item["rule_id"]].category if item["rule_id"] in RULES else None
    by_category = dict.fromkeys(CATEGORIES, 0)
    for r in by_rule:
        if r["rule_id"] in RULES:
            by_category[RULES[r["rule_id"]].category] += r["n"]
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
            "by_category": by_category,
            "placeholders": flags["placeholders"],
            "documentation": flags["documentation"],
            "template_values": flags["template_values"],
        },
        # Things the list cannot promise, in words (for example Ruff did not finish).
        "notes": ([note["quality_note"]] if note and note["quality_note"] else [])
        + (["Reachability could not be worked out for this analysis, so the list is in the usual"
             " order."] if reach_failed else []),
    }
