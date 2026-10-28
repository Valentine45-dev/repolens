"""Retrieval for one question: exact cosine top-k over this snapshot's chunks, then optional
1-hop graph expansion. A plain function so the evaluation can call it with expansion on and off.

Test and example code (chunks.in_test) is left out in SQL unless asked for; if that leaves
nothing, the search runs once more with it included and the result says so.
"""

from dataclasses import dataclass, field

from app import config
from app.db import pool
from app.qa.embed import get_embedder

CHARS_PER_TOKEN = 3.5  # rough estimate for the context budget; chunks are already <= 256 tokens

_COLUMNS = (
    "c.id, c.symbol_id, c.start_line, c.end_line, c.text, c.in_test, s.qualified_name, s.kind,"
    " f.id AS file_id, f.path, c.embedding <=> %s::vector AS distance"
)
NEXT_TO = 3  # a top-level chunk ending this close above a definition belongs with it
_FROM = " FROM chunks c JOIN symbols s ON s.id = c.symbol_id JOIN files f ON f.id = s.file_id"


@dataclass
class Snippet:
    chunk_id: int
    symbol_id: int
    file_id: int
    path: str
    qualified_name: str
    start_line: int
    end_line: int
    text: str
    in_test: bool
    distance: float
    via: str  # "search" or "graph"


@dataclass
class Retrieval:
    snippets: list[Snippet] = field(default_factory=list)
    k: int = 0
    expand: bool = False
    include_tests: bool = False
    used_test_code: bool = False

    def summary(self) -> dict:
        return {
            "k": self.k,
            "expand": self.expand,
            "include_tests": self.include_tests,
            "used_test_code": self.used_test_code,
            "sent": len(self.snippets),
            "from_graph": sum(1 for s in self.snippets if s.via == "graph"),
        }


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def _snippet(row: dict, via: str) -> Snippet:
    return Snippet(row["id"], row["symbol_id"], row["file_id"], row["path"],
                   row["qualified_name"], row["start_line"], row["end_line"], row["text"],
                   row["in_test"], float(row["distance"]), via)


def _search(conn, snapshot_id: int, q: str, k: int, include_tests: bool) -> list[dict]:
    return conn.execute(
        f"SELECT {_COLUMNS}{_FROM} WHERE c.snapshot_id = %s AND (%s OR NOT c.in_test)"
        " ORDER BY distance, c.id LIMIT %s",
        (q, snapshot_id, include_tests, k),
    ).fetchall()


def _expand(conn, snapshot_id: int, q: str, hits: list[dict], include_tests: bool,
            limit: int) -> list[dict]:
    """One hop from each hit, by what the hit is:
    - function or method: its callers and callees (call edges, confidence >= 0.9);
    - class: its methods (`defines` edges);
    - top-level code (module chunk): the definition right below it, if any (e.g. code that
      documents or sets up that function). Never the file's imports: they lead to the top of
      other files, not to the code the chunk is about.
    From each neighbour, its chunk closest to the question. Ordered by edge confidence, then
    similarity."""
    by_kind: dict[str, set[int]] = {}
    for h in hits:
        by_kind.setdefault(h["kind"], set()).add(h["symbol_id"])
    hit_ids = list({h["symbol_id"] for h in hits})
    confidence: dict[int, float] = {}

    callable_ids = list(by_kind.get("function", set()) | by_kind.get("method", set()))
    if callable_ids:
        for r in conn.execute(
            "SELECT n.id, max(round(e.confidence::numeric, 2)) AS confidence FROM edges e"
            " JOIN symbols n ON n.id = CASE WHEN e.src_id = ANY(%s) THEN e.dst_id"
            " ELSE e.src_id END"
            " WHERE e.snapshot_id = %s AND (e.src_id = ANY(%s) OR e.dst_id = ANY(%s))"
            " AND e.type = 'calls' AND round(e.confidence::numeric, 2) >= 0.9"
            " AND n.file_id IS NOT NULL GROUP BY n.id",
            (callable_ids, snapshot_id, callable_ids, callable_ids),
        ):
            confidence[r["id"]] = max(confidence.get(r["id"], 0.0), float(r["confidence"]))
    class_ids = list(by_kind.get("class", set()))
    if class_ids:
        for r in conn.execute(
            "SELECT dst_id AS id FROM edges WHERE snapshot_id = %s AND type = 'defines'"
            " AND src_id = ANY(%s)",
            (snapshot_id, class_ids),
        ):
            confidence[r["id"]] = 1.0
    module_hits = [h for h in hits if h["kind"] == "module"]
    if module_hits:
        below = conn.execute(
            "SELECT id, file_id, start_line FROM symbols WHERE file_id = ANY(%s)"
            " AND kind IN ('function', 'method', 'class')",
            (list({h["file_id"] for h in module_hits}),),
        ).fetchall()
        for h in module_hits:
            near = [s for s in below if s["file_id"] == h["file_id"]
                    and h["end_line"] < s["start_line"] <= h["end_line"] + NEXT_TO]
            if near:
                confidence[min(near, key=lambda s: s["start_line"])["id"]] = 1.0
    for sid in hit_ids:
        confidence.pop(sid, None)
    if not confidence:
        return []
    rows = conn.execute(
        f"SELECT DISTINCT ON (c.symbol_id) {_COLUMNS}{_FROM}"
        " WHERE c.snapshot_id = %s AND c.symbol_id = ANY(%s) AND (%s OR NOT c.in_test)"
        " AND c.id <> ALL(%s) ORDER BY c.symbol_id, distance, c.id",
        (q, snapshot_id, list(confidence), include_tests, [h["id"] for h in hits]),
    ).fetchall()
    rows.sort(key=lambda r: (-confidence[r["symbol_id"]], r["distance"], r["id"]))
    return rows[:limit]


def retrieve(snapshot_id: int, question: str, *, k: int | None = None,
             expand: bool | None = None, include_tests: bool = False,
             expand_max: int | None = None) -> Retrieval:
    k = config.QA_TOP_K if k is None else k
    expand = config.QA_GRAPH_EXPANSION if expand is None else expand
    expand_max = config.QA_EXPAND_MAX if expand_max is None else expand_max
    q = _vector(get_embedder().embed([question])[0])
    with pool().connection() as conn:
        tests = include_tests
        hits = _search(conn, snapshot_id, q, k, tests)
        if not hits and not tests:
            tests = True  # only test or example code here: use it, and say so
            hits = _search(conn, snapshot_id, q, k, tests)
        extra = _expand(conn, snapshot_id, q, hits, tests, expand_max) \
            if expand and hits else []

    budget = config.QA_CONTEXT_TOKENS * CHARS_PER_TOKEN
    snippets: list[Snippet] = []
    for row, via in [(h, "search") for h in hits] + [(e, "graph") for e in extra]:
        if snippets and len(row["text"]) > budget:
            break
        budget -= len(row["text"])
        snippets.append(_snippet(row, via))
    return Retrieval(snippets, k, expand, include_tests,
                     used_test_code=any(s.in_test for s in snippets))
