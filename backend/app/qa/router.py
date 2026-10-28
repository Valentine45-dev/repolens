"""Structural questions answered from the graph, with no LLM.

A short list of question patterns captures a target ("which files import X", "what calls Y").
The target is resolved against this snapshot's files and symbols; when nothing matches, the
question goes to the AI route instead (the router is a shortcut, not a gate). When it matches
several things, the answer lists them and asks which one is meant: it never picks one.

Graph answers carry `results` (files or symbols with their node id), never citations:
citations are reserved for validated `path:start-end` ranges in AI answers.
"""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.api.graph import _neighbours
from app.db import pool
from app.paths import is_test_path

MIN_CONFIDENCE = 0.9  # same as the dependents/dependencies endpoints' default
MAX_RESULTS = 50
MAX_CANDIDATES = 5


@dataclass(frozen=True)
class Route:
    direction: str  # "in": what depends on the target; "out": what the target depends on
    edge: str | None  # "imports", "calls" or None for both
    target: str


_T = r"(?P<t>.+?)"
PATTERNS: list[tuple[str, str, str | None]] = [
    # what depends on the target
    (rf"(?:which|what) files? imports? {_T}", "in", "imports"),
    (rf"(?:who|what) imports {_T}", "in", "imports"),
    (rf"where is {_T} imported(?: from)?", "in", "imports"),
    (rf"importers of {_T}", "in", "imports"),
    (rf"(?:who|what|which functions?|which methods?) calls? {_T}", "in", "calls"),
    (rf"callers of {_T}", "in", "calls"),
    (rf"where is {_T} called(?: from)?", "in", "calls"),
    (rf"(?:what|who|which files?) (?:depends? on|uses) {_T}", "in", None),
    (rf"where is {_T} used", "in", None),
    (rf"what (?:would|will) break if i (?:change|remove|delete) {_T}", "in", None),
    (rf"dependents of {_T}", "in", None),
    # what the target depends on
    (rf"what does {_T} import", "out", "imports"),
    (rf"imports of {_T}", "out", "imports"),
    (rf"what (?:functions )?does {_T} call", "out", "calls"),
    (rf"callees of {_T}", "out", "calls"),
    (rf"what does {_T} (?:depend on|use)", "out", None),
    (rf"dependencies of {_T}", "out", None),
]
_COMPILED = [(re.compile(rf"^{p}$", re.IGNORECASE), d, e) for p, d, e in PATTERNS]
_NOUN = re.compile(r"\s+(?:file|module|function|method|class|package)$", re.IGNORECASE)


def match_route(question: str) -> Route | None:
    text = " ".join(question.strip().split()).rstrip("?.! ")
    for pattern, direction, edge in _COMPILED:
        m = pattern.match(text)
        if m:
            target = m["t"].strip().strip("`'\"")
            target = re.sub(r"^the\s+", "", target, flags=re.IGNORECASE)
            target = _NOUN.sub("", target).strip("`'\"() ")
            if target:
                return Route(direction, edge, target)
    return None


_SYMBOL = (
    "SELECT s.id, s.kind, s.name, s.qualified_name, s.file_id, s.start_line, s.end_line, f.path"
    " FROM symbols s LEFT JOIN files f ON f.id = s.file_id WHERE s.snapshot_id = %s"
)


def resolve_target(snapshot_id: int, target: str) -> list[dict]:
    """Candidates for the target, from the first rule that matches anything: exact file path,
    path suffix, file name without extension, Python dotted module, qualified name, symbol
    name, external package. Test files are dropped when non-test candidates exist."""
    stem = PurePosixPath(target).stem
    dotted = target.replace(".", "/")
    modules = f"{_SYMBOL} AND s.kind = 'module'"
    code = f"{_SYMBOL} AND s.kind IN ('class', 'function', 'method')"
    rules = [
        (f"{modules} AND f.path = %s", (target,)),
        (f"{modules} AND f.path LIKE %s", ("%/" + _like(target),)),
        (f"{modules} AND f.path ~ %s", (r"(^|/)" + re.escape(target) + r"\.[^/.]+$",)),
        (f"{modules} AND f.path ~ %s",
         (r"(^|/)" + re.escape(dotted) + r"(\.py|/__init__\.py)$",)),
        (f"{code} AND s.qualified_name = %s", (target,)),
        (f"{code} AND (s.name = %s OR s.qualified_name LIKE %s OR s.qualified_name LIKE %s)",
         (target, "%." + _like(target), "%:" + _like(target))),
        (f"{_SYMBOL} AND s.kind = 'external' AND s.qualified_name = %s", (target,)),
    ]
    if "/" in target or stem != target:
        rules.pop(2)  # a bare file name rule only makes sense for a bare name
    with pool().connection() as conn:
        for sql, args in rules:
            rows = conn.execute(f"{sql} ORDER BY f.path, s.start_line, s.id",
                                (snapshot_id, *args)).fetchall()
            if rows:
                kept = [r for r in rows if not (r["path"] and is_test_path(r["path"]))]
                return kept or rows
    return []


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _node(row: dict) -> dict:
    return {
        "node_id": row["id"],
        "kind": row["kind"],
        "name": row["name"],
        "qualified_name": row["qualified_name"],
        "file_id": row["file_id"],
        "path": row["path"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
        "in_test": bool(row["path"]) and is_test_path(row["path"]),
    }


def _label(row: dict) -> str:
    if row["kind"] == "module":
        return row["path"]
    if row["kind"] == "external":
        return f"{row['qualified_name']} (external package)"
    short = row["qualified_name"].rsplit(":", 1)[-1]
    return f"{short} in {row['path']}"


# Symbol kind -> (singular, plural) for counted results. Methods are counted as functions.
_NOUNS = {
    "module": ("file", "files"),
    "external": ("package", "packages"),
    "function": ("function", "functions"),
    "method": ("function", "functions"),
    "class": ("class", "classes"),
    "unresolved": ("unresolved import", "unresolved imports"),
}


def count_phrase(kinds: list[str]) -> str:
    """'6 files', '1 package', '2 files and 1 package', '3 files, 2 functions and 1 class'."""
    counts: dict[tuple[str, str], int] = {}
    for kind in kinds:
        noun = _NOUNS.get(kind, ("item", "items"))
        counts[noun] = counts.get(noun, 0) + 1
    parts = [f"{n} {one if n == 1 else many}" for (one, many), n in counts.items()]
    if len(parts) <= 1:
        return parts[0] if parts else "0 items"
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# (some found, none found); {n} is a count phrase ("6 files"), {t} the target.
_SENTENCE = {
    ("in", "imports"): ("{n} import{s} {t}.", "Nothing in the graph imports {t}."),
    ("in", "calls"): ("{n} call{s} {t}.", "Nothing in the graph calls {t}."),
    ("in", None): ("{n} depend{s} on {t}.", "Nothing in the graph depends on {t}."),
    ("out", "imports"): ("{t} imports {n}.", "{t} imports nothing in the graph."),
    ("out", "calls"): ("{t} calls {n}.", "{t} calls nothing in the graph."),
    ("out", None): ("{t} depends on {n}.", "{t} depends on nothing in the graph."),
}


def graph_answer(snapshot_id: int, route: Route) -> dict | None:
    """The graph answer, or None when the target matches nothing (the AI route takes it)."""
    candidates = resolve_target(snapshot_id, route.target)
    if not candidates:
        return None
    # `query` is the target as written, so a client can re-ask with a chosen candidate.
    base = {"kind": "graph", "citations": [], "dropped": 0, "prompt_version": None,
            "retrieval": None, "lower_confidence": 0, "query": route.target}
    if len(candidates) > 1:
        shown = candidates[:MAX_CANDIDATES]
        more = len(candidates) - len(shown)
        return {
            **base,
            "status": "ambiguous",
            "answer": f"“{route.target}” matches {count_phrase([c['kind'] for c in candidates])}"
                      " in this"
                      f" repository{f' (showing {len(shown)})' if more else ''}."
                      " Which one do you mean? Ask again with its file path.",
            "target": None,
            "results": [_node(c) for c in shown],
            "total": len(candidates),
        }

    target = candidates[0]
    found = _neighbours(target["id"], MIN_CONFIDENCE, route.direction)["items"]
    everything = _neighbours(target["id"], 0.0, route.direction)["items"]
    if route.edge:
        found = [i for i in found if i["type"] == route.edge]
        everything = [i for i in everything if i["type"] == route.edge]
    results = []
    for item in found[:MAX_RESULTS]:
        node = _node(item["symbol"])
        results.append({**node, "edge": item["type"], "confidence": item["confidence"]})
    lower = len(everything) - len(found)

    some, none = _SENTENCE[(route.direction, route.edge)]
    count = count_phrase([item["symbol"]["kind"] for item in found])
    answer = (some if found else none).format(
        n=count, t=_label(target), s="s" if len(found) == 1 else "")
    if len(found) > MAX_RESULTS:
        answer += f" Showing the first {MAX_RESULTS}."
    if lower:
        answer += (f" Plus {lower} lower-confidence name {'match' if lower == 1 else 'matches'}"
                   " not shown.")
    answer += " The graph has static imports and name-based calls only."
    return {**base, "status": "answered", "answer": answer, "target": _node(target),
            "results": results, "total": len(found), "lower_confidence": lower}
