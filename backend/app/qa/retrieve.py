"""Retrieval for one question: exact cosine top-k over this snapshot's chunks, then optional
1-hop graph expansion. A plain function so the evaluation can call it with expansion on and off.

Hybrid search (`hybrid=True`, default QA_HYBRID): the vector top-HYBRID_DEPTH and a keyword
top-HYBRID_DEPTH over chunks.search_tsv (OR of the question's terms, app.qa.chunks.query_terms)
are merged by reciprocal rank fusion (score = sum of 1 / (RRF_K + rank)) and cut to top-k; graph
expansion then runs on the fused hits as on plain search hits.

Test and example code (chunks.in_test) is left out in SQL unless asked for; if that leaves
nothing, the search runs once more with it included and the result says so.
"""

from dataclasses import dataclass, field

from app import config
from app.db import pool
from app.qa.chunks import query_terms
from app.qa.embed import get_embedder

CHARS_PER_TOKEN = 3.5  # rough estimate for the context budget; chunks are already <= 256 tokens

# Doc chunks have no symbol; their name is the heading trail, kept in the embedded text only, so
# it is read back from the chunk's first heading line by doc_title().
_COLUMNS = (
    "c.id, c.symbol_id, c.start_line, c.end_line, c.text, c.in_test, c.source,"
    " coalesce(s.qualified_name, '') AS qualified_name, s.kind,"
    " f.id AS file_id, f.path, c.embedding <=> %s::vector AS distance"
)
NEXT_TO = 3  # a top-level chunk ending this close above a definition belongs with it
SCOPE_SHARE = 2 / 3  # of the context budget for a picked file, so other code still fits
_FROM = " FROM chunks c JOIN files f ON f.id = c.file_id LEFT JOIN symbols s ON s.id = c.symbol_id"
_CODE = " AND c.source = 'code'"  # code and documentation are separate pools


@dataclass
class Snippet:
    chunk_id: int
    symbol_id: int | None  # None for documentation
    file_id: int
    path: str
    qualified_name: str
    start_line: int
    end_line: int
    text: str
    in_test: bool
    distance: float
    via: str  # "search", "graph", "scope" or "doc"
    source: str = "code"  # "code" or "doc"


@dataclass
class Retrieval:
    snippets: list[Snippet] = field(default_factory=list)
    k: int = 0
    expand: bool = False
    include_tests: bool = False
    used_test_code: bool = False
    scope_file_id: int | None = None
    hybrid: bool = False
    doc_pool: int = 0
    doc_cutoff_rank: int = 0

    def summary(self) -> dict:
        out = {
            "k": self.k,
            "hybrid": self.hybrid,
            "expand": self.expand,
            "include_tests": self.include_tests,
            "used_test_code": self.used_test_code,
            "sent": len(self.snippets),
            "from_graph": sum(1 for s in self.snippets if s.via == "graph"),
            "docs": sum(1 for s in self.snippets if s.via == "doc"),
            "doc_pool": self.doc_pool,
        }
        if self.scope_file_id is not None:
            out["scope"] = {"file_id": self.scope_file_id,
                            "sent": sum(1 for s in self.snippets if s.via == "scope")}
        return out


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in values) + "]"


def _snippet(row: dict, via: str) -> Snippet:
    return Snippet(row["id"], row["symbol_id"], row["file_id"], row["path"],
                   row["qualified_name"], row["start_line"], row["end_line"], row["text"],
                   row["in_test"], float(row["distance"]), via, row["source"])


def _search(conn, snapshot_id: int, q: str, k: int, include_tests: bool) -> list[dict]:
    return conn.execute(
        f"SELECT {_COLUMNS}{_FROM} WHERE c.snapshot_id = %s AND (%s OR NOT c.in_test){_CODE}"
        " ORDER BY distance, c.id LIMIT %s",
        (q, snapshot_id, include_tests, k),
    ).fetchall()


def _docs(conn, snapshot_id: int, q: str, n: int, include_tests: bool,
          max_distance: float) -> list[dict]:
    """Up to n documentation chunks no farther from the question than max_distance."""
    return conn.execute(
        f"SELECT {_COLUMNS}{_FROM} WHERE c.snapshot_id = %s AND (%s OR NOT c.in_test)"
        " AND c.source = 'doc' AND c.embedding <=> %s::vector <= %s"
        " ORDER BY distance, c.id LIMIT %s",
        (q, snapshot_id, include_tests, q, max_distance, n),
    ).fetchall()


def _keyword(conn, snapshot_id: int, q: str, terms: list[str], depth: int,
              include_tests: bool) -> list[dict]:
    """Chunks whose search words contain any of the terms, best ts_rank first (normalised by
    document length, option 1). Terms are plain [a-z0-9]+ lexemes (query_terms), so the joined
    string is a valid tsquery of ORs and nothing in it is an operator."""
    if not terms:
        return []
    tsquery = " | ".join(terms)
    return conn.execute(
        f"SELECT {_COLUMNS}, ts_rank(c.search_tsv, to_tsquery('simple', %s), 1) AS rank{_FROM}"
        f" WHERE c.snapshot_id = %s AND (%s OR NOT c.in_test){_CODE}"
        " AND c.search_tsv @@ to_tsquery('simple', %s)"
        " ORDER BY rank DESC, c.id LIMIT %s",
        (q, tsquery, snapshot_id, include_tests, tsquery, depth),
    ).fetchall()


def fuse(vector: list[dict], keyword: list[dict], k: int, rrf_k: int) -> list[dict]:
    """Reciprocal rank fusion of two ranked lists of chunk rows, deduped by chunk id, top k. Ties:
    the better single rank, then vector distance, then chunk id (so the order is reproducible)."""
    score: dict[int, float] = {}
    best: dict[int, int] = {}
    rows: dict[int, dict] = {}
    for ranked in (vector, keyword):
        for rank, row in enumerate(ranked, start=1):
            cid = row["id"]
            score[cid] = score.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            best[cid] = min(best.get(cid, rank), rank)
            rows.setdefault(cid, row)
    order = sorted(rows, key=lambda c: (-score[c], best[c], float(rows[c]["distance"]), c))
    return [rows[c] for c in order[:k]]


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
        f" AND c.id <> ALL(%s){_CODE} ORDER BY c.symbol_id, distance, c.id",
        (q, snapshot_id, list(confidence), include_tests, [h["id"] for h in hits]),
    ).fetchall()
    rows.sort(key=lambda r: (-confidence[r["symbol_id"]], r["distance"], r["id"]))
    return rows[:limit]


def _scoped(conn, snapshot_id: int, q: str, file_id: int) -> list[dict]:
    """All chunks of the file the user picked, closest to the question first. Test code too:
    it was asked for by name."""
    return conn.execute(
        f"SELECT {_COLUMNS}{_FROM} WHERE c.snapshot_id = %s AND f.id = %s{_CODE}"
        " ORDER BY distance, c.id",
        (q, snapshot_id, file_id),
    ).fetchall()


def retrieve(snapshot_id: int, question: str, *, k: int | None = None,
             expand: bool | None = None, include_tests: bool = False,
             expand_max: int | None = None, scope_file_id: int | None = None,
             hybrid: bool | None = None, doc_pool: int | None = None,
             doc_cutoff_rank: int | None = None) -> Retrieval:
    """`scope_file_id` ("Ask about this") puts that file's chunks first, within SCOPE_SHARE of the
    context budget, ahead of the usual search and expansion. Without it, nothing here changes.

    Documentation (`doc_pool`, default QA_DOC_POOL; 0 = none) is a separate pool: up to that many
    doc chunks, each no farther from the question than the `doc_cutoff_rank`-th code vector hit
    (default QA_DOC_CUTOFF_RANK; the last hit if there are fewer), added after the code and graph
    chunks within what is left of the context budget. They never take a code slot, and graph
    expansion never starts from them."""
    k = config.QA_TOP_K if k is None else k
    expand = config.QA_GRAPH_EXPANSION if expand is None else expand
    expand_max = config.QA_EXPAND_MAX if expand_max is None else expand_max
    hybrid = config.QA_HYBRID if hybrid is None else hybrid
    doc_pool = config.QA_DOC_POOL if doc_pool is None else doc_pool
    doc_cutoff_rank = config.QA_DOC_CUTOFF_RANK if doc_cutoff_rank is None else doc_cutoff_rank
    q = _vector(get_embedder().embed([question])[0])
    depth = max(k, config.QA_HYBRID_DEPTH) if hybrid else k
    with pool().connection() as conn:
        tests = include_tests
        hits = _search(conn, snapshot_id, q, depth, tests)
        if not hits and not tests:
            tests = True  # only test or example code here: use it, and say so
            hits = _search(conn, snapshot_id, q, depth, tests)
        docs = []
        if doc_pool > 0 and hits:
            cutoff = float(hits[min(doc_cutoff_rank, len(hits)) - 1]["distance"])
            docs = _docs(conn, snapshot_id, q, doc_pool, tests, cutoff)
        if hybrid:
            words = _keyword(conn, snapshot_id, q, query_terms(question), depth, tests)
            hits = fuse(hits, words, k, config.QA_RRF_K)
        scoped = [] if scope_file_id is None else _scoped(conn, snapshot_id, q, scope_file_id)
        if scoped:
            own = {r["id"] for r in scoped}
            hits = [h for h in hits if h["id"] not in own]
        seeds = scoped + hits
        extra = _expand(conn, snapshot_id, q, seeds, tests, expand_max) \
            if expand and seeds else []

    budget = config.QA_CONTEXT_TOKENS * CHARS_PER_TOKEN
    snippets: list[Snippet] = []
    scope_budget = budget * SCOPE_SHARE
    for row in scoped:
        if snippets and len(row["text"]) > scope_budget:
            break
        scope_budget -= len(row["text"])
        budget -= len(row["text"])
        snippets.append(_snippet(row, "scope"))
    for row, via in [(h, "search") for h in hits] + [(e, "graph") for e in extra]:
        if snippets and len(row["text"]) > budget:
            break
        budget -= len(row["text"])
        snippets.append(_snippet(row, via))
    for row in docs:  # after all code: what is left of the budget, never a code slot
        if len(row["text"]) > budget:
            break
        budget -= len(row["text"])
        snippets.append(_snippet(row, "doc"))
    return Retrieval(snippets, k, expand, include_tests,
                     # A file the user picked is not "test code because nothing else matched".
                     used_test_code=any(s.in_test and s.via not in ("scope", "doc")
                                        for s in snippets),
                     scope_file_id=scope_file_id, hybrid=hybrid, doc_pool=doc_pool,
                     doc_cutoff_rank=doc_cutoff_rank)
