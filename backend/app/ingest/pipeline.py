"""Runs one ingestion job: fetch -> discover -> parse -> edges -> detect -> embed.

Each stage replaces its own rows (delete-then-insert in one transaction), so a rerun never
duplicates anything. Progress goes to the job row. The clone is always deleted afterwards.
"""

import logging
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.db import pool
from app.detect import detect
from app.detect.imports import broken_imports
from app.detect.ruff import RuffError, run_ruff
from app.detect.rules import BROKEN_IMPORT_RULE, RULES, SECRET_RULE
from app.ingest import clone
from app.ingest.calls import resolve_calls
from app.ingest.discover import DiscoveredFile, DiscoverResult, discover
from app.ingest.parse import (
    IMPORT_SCOPES,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    line_count,
    module_name,
    parse_python,
)
from app.ingest.parse_js import parse_js
from app.ingest.resolve import JsModules, PythonModules, Target, resolve_js, resolve_python
from app.paths import is_doc_path, is_nonrunning_path, is_test_path
from app.qa.chunks import Chunk, build_chunks, search_words
from app.qa.embed import get_embedder

log = logging.getLogger("repolens.ingest")

PARSER_KINDS = ("module", "class", "function", "method")


# One analysis or search retry at a time: each holds file contents, parse results and embedding
# batches in memory, and the demo laptop has little to spare. A waiting job stays 'queued'; its
# time limit starts when it gets its turn.
_JOB_LOCK = threading.Lock()


class JobError(RuntimeError):
    """An expected failure whose message is safe to show the user."""


def _set_job(job_id: int, stage: str, percent: int, status: str = "running", error=None,
             done: int | None = None, total: int | None = None) -> None:
    """`done` / `total` count within the stage (parse: files, embed: chunks) for the Progress
    page; every other update clears them."""
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET stage = %s, percent = %s, status = %s, error = %s,"
            " progress_done = %s, progress_total = %s WHERE id = %s",
            (stage, percent, status, error, done, total, job_id),
        )


def _set_receipt(job_id: int, result: DiscoverResult) -> None:
    """What discover kept and left out, for the status API (the UI's file-limit notice)."""
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET files_kept = %s, files_skipped = %s, files_beyond_limit = %s,"
            " hit_file_limit = %s WHERE id = %s",
            (len(result.files), result.skipped, result.beyond_limit, result.hit_file_limit,
             job_id),
        )


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise JobError(f"Analysis took longer than {config.MAX_ANALYSIS_S}s and was stopped.")


def _secret_snippet(content: str, line: int) -> str:
    lines = content.split("\n")  # "\n" only, as the redactor counts lines
    text = lines[line - 1].strip() if 0 < line <= len(lines) else ""
    return text[:200]


def store_files(snapshot_id: int, files: list[DiscoveredFile]) -> None:
    """Discover stage output: files (redacted content) and their hardcoded-secret findings."""
    with pool().connection() as conn, conn.transaction():
        # Cascades to this snapshot's symbols, findings and chunks that hang off files.
        conn.execute("DELETE FROM files WHERE snapshot_id = %s", (snapshot_id,))
        conn.execute(
            "DELETE FROM findings WHERE snapshot_id = %s AND rule_id = %s",
            (snapshot_id, SECRET_RULE),
        )
        for f in files:
            file_id = conn.execute(
                "INSERT INTO files (snapshot_id, path, language, loc, content)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (snapshot_id, f.path, f.language, f.loc, f.content),
            ).fetchone()["id"]
            # Placeholder keys in tests are common and rarely real: report them, but low. The
            # same for documentation (examples). A value that looks like a stand-in is demoted
            # only in files that do not run (documentation, example or template files); in
            # code and runtime config it keeps its severity and gets a note, because the app
            # may be deployed with it as it is, and a publicly known key is no secret at all.
            in_test = is_test_path(f.path)
            in_docs = is_doc_path(f.path)
            nonrunning = is_nonrunning_path(f.path)
            for s in f.secrets:
                looks_like_template = s.placeholder is not None
                placeholder = looks_like_template and nonrunning
                template_value = looks_like_template and not nonrunning
                conn.execute(
                    "INSERT INTO findings (snapshot_id, file_id, line, rule_id, severity,"
                    " message, snippet, in_test, in_docs, placeholder, template_value)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        snapshot_id,
                        file_id,
                        s.line,
                        SECRET_RULE,
                        "low" if (in_test or in_docs or placeholder) else "high",
                        secret_message(s.kind, in_test, in_docs, placeholder, template_value),
                        _secret_snippet(f.content, s.line),
                        in_test,
                        in_docs,
                        placeholder,
                        template_value,
                    ),
                )


def secret_message(kind: str, in_test: bool, in_docs: bool, placeholder: bool,
                   template_value: bool = False) -> str:
    """Where the finding is and why it ranks low, in words (the migration writes the same text
    for rows it marks as documentation)."""
    where = {
        (True, False): " in test or example code",
        (False, True): " in documentation",
        (True, True): " in test or example code and in documentation",
    }.get((in_test, in_docs), "")
    text = f"Possible hardcoded secret ({kind}){where}"
    if placeholder:
        return text + "; the value looks like a placeholder."
    if template_value:
        return text + "; looks like a template value."
    return text + "."


def parse_file(path: str, language: str, content: str) -> ParsedFile:
    """Parse one file. A file the parser cannot handle (for example a RecursionError on a very
    deeply nested expression) keeps only its module symbol, so one file never fails the job."""
    try:
        if language == "python":
            return parse_python(path, content)
        return parse_js(path, content)
    except Exception as e:
        log.warning("parse skipped for one file (%s); module symbol only", type(e).__name__)
        if language == "python":
            name = module_name(path)
            stem = name.rsplit(".", 1)[-1]
        else:
            name, stem = path, path.rsplit("/", 1)[-1].split(".", 1)[0]
        return ParsedFile(symbols=[ParsedSymbol("module", stem, name, 1, line_count(content))])


def detect_file(path: str, language: str, content: str, parsed: ParsedFile) -> list:
    """Detector hits for one file; a file the detectors cannot walk gets none (logged)."""
    try:
        return detect(path, language, content, parsed)
    except Exception as e:
        log.warning("detectors skipped for one file (%s)", type(e).__name__)
        return []


@dataclass
class Parsed:
    language: str
    result: ParsedFile
    content: str  # redacted text, for the detect stage's re-parse and snippets


def store_symbols(snapshot_id: int, job_id: int, deadline: float) -> dict[str, Parsed]:
    """Parse stage: module/class/function/method symbols for every Python and JS/TS file.

    Returns the parse results by path so the edges stage does not parse again.
    """
    with pool().connection() as conn:
        files = conn.execute(
            "SELECT id, path, language, content FROM files WHERE snapshot_id = %s"
            " AND language IN ('python', 'javascript', 'typescript') ORDER BY path",
            (snapshot_id,),
        ).fetchall()

    parsed: dict[str, Parsed] = {}
    rows = []
    _set_job(job_id, "parse", 40, done=0, total=len(files))
    for i, f in enumerate(files, start=1):
        result = parse_file(f["path"], f["language"], f["content"])
        parsed[f["path"]] = Parsed(f["language"], result, f["content"])
        for s in result.symbols:
            rows.append(
                (snapshot_id, f["id"], s.kind, s.name, s.qualified_name,
                 s.start_line, s.end_line, s.signature)
            )
        if i % 50 == 0:
            _check_deadline(deadline)
            _set_job(job_id, "parse", 40 + int(40 * i / len(files)), done=i, total=len(files))

    with pool().connection() as conn, conn.transaction():
        conn.execute(
            "DELETE FROM symbols WHERE snapshot_id = %s AND kind = ANY(%s)",
            (snapshot_id, list(PARSER_KINDS)),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO symbols (snapshot_id, file_id, kind, name, qualified_name,"
                " start_line, end_line, signature) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                rows,
            )
    return parsed


MAX_SITES_PER_EDGE = 20


def _insert_edge(cur, edge: tuple, sites: list[tuple[int, float | None]]) -> int:
    """One edge row plus its first MAX_SITES_PER_EDGE sites; site_count (in `edge`) is the total."""
    edge_id = cur.execute(
        "INSERT INTO edges (snapshot_id, src_id, dst_id, type, confidence, import_scope,"
        " site_count)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        edge,
    ).fetchone()["id"]
    if sites:
        cur.executemany(
            "INSERT INTO edge_sites (edge_id, line, confidence) VALUES (%s, %s, %s)",
            [(edge_id, line, c) for line, c in sites[:MAX_SITES_PER_EDGE]],
        )
    return edge_id


def store_edges(snapshot_id: int, parsed: dict[str, Parsed]) -> Counter:
    """Edges stage, Python and JS/TS: import edges from each file's module symbol to an internal
    module, an external package or an unresolved import; call edges between symbols (calls.py)."""
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT content FROM files WHERE snapshot_id = %s AND path = 'tsconfig.json'",
            (snapshot_id,),
        ).fetchone()
    py_modules = PythonModules([path for path, p in parsed.items() if p.language == "python"])
    js_modules = JsModules(
        [path for path, p in parsed.items() if p.language != "python"],
        row["content"] if row else None,
    )
    def resolve_import(path: str, imp: ParsedImport) -> list[Target]:
        if parsed[path].language == "python":
            return resolve_python(path, imp, py_modules)
        return resolve_js(path, imp, js_modules)

    wanted: dict[tuple[str, Target], str] = {}  # one edge per (file, target), first seen first
    import_lines: dict[tuple[str, Target], set[int]] = {}
    for path, p in parsed.items():
        for imp in p.result.imports:
            for target in resolve_import(path, imp):
                if not (target.kind == "internal" and target.key == path):
                    seen = wanted.get((path, target), imp.scope)
                    wanted[(path, target)] = min(seen, imp.scope, key=IMPORT_SCOPES.index)
                    import_lines.setdefault((path, target), set()).add(imp.line)
    calls = resolve_calls({path: p.result for path, p in parsed.items()}, resolve_import)

    counts: Counter = Counter()
    with pool().connection() as conn, conn.transaction():
        conn.execute(
            "DELETE FROM edges WHERE snapshot_id = %s AND type IN ('imports', 'calls', 'defines')",
            (snapshot_id,),
        )
        conn.execute(
            "DELETE FROM symbols WHERE snapshot_id = %s AND kind IN ('external', 'unresolved')",
            (snapshot_id,),
        )
        module_ids = {
            r["path"]: r["id"]
            for r in conn.execute(
                "SELECT f.path, s.id FROM symbols s JOIN files f ON f.id = s.file_id"
                " WHERE s.snapshot_id = %s AND s.kind = 'module'",
                (snapshot_id,),
            )
        }
        node_ids: dict[Target, int] = {}
        for target in {t for _, t in wanted if t.kind != "internal"}:
            node_ids[target] = conn.execute(
                "INSERT INTO symbols (snapshot_id, file_id, kind, name, qualified_name)"
                " VALUES (%s, NULL, %s, %s, %s) RETURNING id",
                (snapshot_id, target.kind, target.key, target.key),
            ).fetchone()["id"]

        with conn.cursor() as cur:
            for (path, target), scope in wanted.items():
                dst = module_ids.get(target.key) if target.kind == "internal" else node_ids[target]
                if dst is None:
                    continue
                lines = sorted(import_lines[(path, target)])
                _insert_edge(cur, (snapshot_id, module_ids[path], dst, "imports", 1.0,
                                             scope, len(lines)), [(n, None) for n in lines])
                counts[target.kind] += 1

        symbol_ids: dict[tuple[str, str], int] = {}
        kinds: dict[int, str] = {}
        for r in conn.execute(
            "SELECT f.path, s.qualified_name, s.id, s.kind FROM symbols s"
            " JOIN files f ON f.id = s.file_id WHERE s.snapshot_id = %s ORDER BY s.id",
            (snapshot_id,),
        ):
            symbol_ids.setdefault((r["path"], r["qualified_name"]), r["id"])
            kinds[r["id"]] = r["kind"]

        # A class defines its methods: `Pkg.mod.Class.m` / `path:Class.m` -> `...Class`.
        define_rows = []
        for (path, qname), sid in symbol_ids.items():
            if kinds[sid] != "method" or "." not in qname:
                continue
            parent = symbol_ids.get((path, qname.rsplit(".", 1)[0]))
            if parent is not None and kinds[parent] == "class":
                define_rows.append((snapshot_id, parent, sid))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO edges (snapshot_id, src_id, dst_id, type, confidence)"
                " VALUES (%s, %s, %s, 'defines', 1.0)",
                define_rows,
            )
        counts["defines"] = len(define_rows)
        with conn.cursor() as cur:
            for edge in calls:
                src, dst = symbol_ids.get(edge.src), symbol_ids.get(edge.dst)
                if src is not None and dst is not None:
                    _insert_edge(cur, (snapshot_id, src, dst, "calls", edge.confidence, None,
                                       len(edge.sites)), list(edge.sites))
                    counts[f"calls@{edge.confidence}"] += 1
    return counts


def _innermost_symbol(symbols: list[ParsedSymbol], line: int) -> ParsedSymbol | None:
    """The smallest symbol (function, method, class, or else the module) containing `line`."""
    containing = [s for s in symbols if s.start_line <= line <= s.end_line]
    return min(containing, key=lambda s: s.end_line - s.start_line, default=None)


def store_findings(snapshot_id: int, parsed: dict[str, Parsed],
                   job_id: int | None = None) -> int:
    """Detect stage: rule findings for every code file, Ruff's code-quality findings for the
    Python files, and broken internal imports. Replaces only the detector rules' findings;
    hardcoded-secret findings belong to the discover stage. If Ruff cannot finish, the rest is
    stored and the job records why (`jobs.quality_note`), so an empty quality list is never read
    as "nothing found"."""
    rows = []
    snippets: dict[str, list[str]] = {}
    for path, p in parsed.items():
        # Split on "\n" only, like Tree-sitter and the redactor (splitlines() would also break
        # on form feeds and U+2028 and shift the snippet off the reported line).
        snippets[path] = p.content.split("\n")
        for hit in detect_file(path, p.language, p.content, p.result):
            rule = RULES[hit.rule_id]
            rows.append((path, hit.line, rule.id, rule.severity, rule.title))

    quality_note = None
    try:
        # The new quality checks skip test and example code: pytest fixtures trip F811, and
        # formatter or parser test data is full of deliberately undefined names (psf/black had
        # 5,026 such hits in tests/data and 0 in its source).
        for hit in run_ruff({path: p.content for path, p in parsed.items()
                             if p.language == "python" and not is_test_path(path)}):
            rule = RULES[hit.rule_id]
            rows.append((hit.path, hit.line, rule.id, rule.severity, hit.message or rule.title))
    except RuffError as e:
        quality_note = str(e)
        log.warning("snapshot %s: %s", snapshot_id, e)

    with pool().connection() as conn:
        tsconfig = conn.execute(
            "SELECT content FROM files WHERE snapshot_id = %s AND path = 'tsconfig.json'",
            (snapshot_id,),
        ).fetchone()
    for b in broken_imports({path: (p.language, p.result.imports) for path, p in parsed.items()},
                            tsconfig["content"] if tsconfig else None):
        if is_test_path(b.path):
            continue  # test data imports things that do not exist on purpose (black: 28 of 28)
        rule = RULES[BROKEN_IMPORT_RULE]
        rows.append((b.path, b.line, rule.id, rule.severity,
                     f"Import of `{b.target}` matches no file in this repository."))

    with pool().connection() as conn, conn.transaction():
        conn.execute(
            # Everything but the discover stage's secrets, so a rule dropped from the catalogue
            # (e.g. ruff-PLE0704) does not leave stale rows behind in an older snapshot.
            "DELETE FROM findings WHERE snapshot_id = %s AND rule_id <> %s",
            (snapshot_id, SECRET_RULE),
        )
        ids = {
            (r["path"], r["qualified_name"]): (r["file_id"], r["id"])
            for r in conn.execute(
                "SELECT f.path, f.id AS file_id, s.qualified_name, s.id FROM symbols s"
                " JOIN files f ON f.id = s.file_id WHERE s.snapshot_id = %s ORDER BY s.id DESC",
                (snapshot_id,),
            )
        }
        file_ids = {
            r["path"]: r["id"]
            for r in conn.execute(
                "SELECT path, id FROM files WHERE snapshot_id = %s", (snapshot_id,)
            )
        }
        values = []
        for path, line, rule_id, severity, message in rows:
            symbol = _innermost_symbol(parsed[path].result.symbols, line)
            lines = snippets[path]
            snippet = lines[line - 1].strip()[:200] if 0 < line <= len(lines) else ""
            values.append((
                snapshot_id, file_ids[path],
                ids.get((path, symbol.qualified_name if symbol else None), (None, None))[1],
                line, rule_id, severity, message, snippet, is_test_path(path),
                is_doc_path(path),
            ))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO findings (snapshot_id, file_id, symbol_id, line, rule_id, severity,"
                " message, snippet, in_test, in_docs)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                values,
            )
        if job_id is not None:
            conn.execute("UPDATE jobs SET quality_note = %s WHERE id = %s", (quality_note, job_id))
    return len(rows)


def build_all_chunks(parsed: dict[str, Parsed], embedder) -> tuple[list[Chunk], int]:
    """Chunks (functions, methods, classes, top-level code) from the redacted content, and how
    many units had to be split into windows."""
    chunks: list[Chunk] = []
    split_units: set[tuple[str, str, int]] = set()
    for path, p in parsed.items():
        for c in build_chunks(path, p.content, p.result.symbols, embedder.count_tokens,
                              embedder.max_tokens):
            chunks.append(c)
            if c.window:
                split_units.add((c.path, c.qualified_name, c.unit_start))
    return chunks, len(split_units)


def _set_progress(job_id: int, done: int, total: int, percent: int | None = None) -> None:
    """Counts only (the stage and status stay): also used after the job is done, while test
    code is embedded in the background."""
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET progress_done = %s, progress_total = %s,"
            " percent = coalesce(%s, percent) WHERE id = %s",
            (done, total, percent, job_id),
        )


def embed_group(snapshot_id: int, job_id: int, chunks: list[Chunk], in_test: bool,
                deadline: float, percent: tuple[int, int] | None = None) -> dict:
    """Embed one group (non-test or test chunks) and replace that group's rows in one
    transaction. `percent` maps progress onto the job's percent while the job is running."""
    embedder = get_embedder()
    started = time.monotonic()
    vectors: list[list[float]] = []
    step = 256
    _set_progress(job_id, 0, len(chunks))
    for i in range(0, len(chunks), step):
        vectors += embedder.embed([c.embed_text for c in chunks[i:i + step]])
        _check_deadline(deadline)
        done = min(i + step, len(chunks))
        pct = (percent[0] + int((percent[1] - percent[0]) * done / len(chunks))
               if percent else None)
        _set_progress(job_id, done, len(chunks), pct)
    embed_seconds = time.monotonic() - started

    with pool().connection() as conn, conn.transaction():
        conn.execute("DELETE FROM chunks WHERE snapshot_id = %s AND in_test = %s",
                     (snapshot_id, in_test))
        symbol_ids: dict[tuple[str, str], int] = {}
        for r in conn.execute(
            "SELECT f.path, s.qualified_name, s.id FROM symbols s JOIN files f ON f.id = s.file_id"
            " WHERE s.snapshot_id = %s ORDER BY s.id DESC",
            (snapshot_id,),
        ):
            symbol_ids[(r["path"], r["qualified_name"])] = r["id"]  # lowest id wins
        rows = [
            (snapshot_id, symbol_ids[(c.path, c.qualified_name)], c.start_line, c.end_line,
             c.token_count, in_test, c.text, search_words(c),
             "[" + ",".join(f"{x:.6f}" for x in v) + "]")
            for c, v in zip(chunks, vectors, strict=True)
            if (c.path, c.qualified_name) in symbol_ids
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (snapshot_id, symbol_id, start_line, end_line, token_count,"
                " in_test, text, search_tsv, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, to_tsvector('simple', %s), %s::vector)",
                rows,
            )
    return {
        "group": "test" if in_test else "non_test",
        "chunks": len(rows),
        "windows": sum(1 for c in chunks if c.window),
        "max_tokens": max((c.token_count for c in chunks), default=0),
        "model_max_tokens": embedder.max_tokens,
        "embed_seconds": round(embed_seconds, 1),
        "model": f"{embedder.name}@{embedder.revision}",
    }


def _fetch_with_retry(job_id: int, url: str, sha: str, workdir: Path, deadline: float) -> None:
    """Fetch the commit; on a network error or timeout, try once more on a clean workspace,
    if a full attempt still fits before the deadline. Other git errors fail at once."""
    try:
        clone.fetch_commit(url, sha, workdir, timeout=config.CLONE_TIMEOUT_S)
    except clone.CloneError as e:
        if not e.transient or deadline - time.monotonic() < config.CLONE_TIMEOUT_S:
            raise
        log.warning("job %s: fetch failed (%s), retrying once", job_id, e)
        clone.remove_workspace(workdir)
        clone.fetch_commit(url, sha, workdir, timeout=config.CLONE_TIMEOUT_S)


def _set_search(job_id: int, state: str, error: str | None = None) -> None:
    with pool().connection() as conn:
        conn.execute("UPDATE jobs SET search_state = %s, search_error = %s WHERE id = %s",
                     (state, error, job_id))


def search_first(job_id: int, snapshot_id: int, parsed: dict[str, Parsed], deadline: float,
                 percent: tuple[int, int] | None = None) -> list[Chunk] | None:
    """Search, part 1 (spec 5.2): embed the non-test chunks, which is what Ask uses by default.
    Not fatal: graph and findings are stored already, so a failure leaves only AI questions
    unavailable (search_state 'failed', retryable). Returns the test chunks still to embed
    (empty when there are none), or None on failure."""
    _set_search(job_id, "embedding")
    try:
        chunks, split_units = build_all_chunks(parsed, get_embedder())
        _check_deadline(deadline)
        test = [c for c in chunks if is_test_path(c.path)]
        stats = embed_group(snapshot_id, job_id, [c for c in chunks if not is_test_path(c.path)],
                            False, deadline, percent)
    except JobError as e:
        log.warning("job %s: search stopped: %s", job_id, e)
        # Only the search stopped: say so, and say what is still complete.
        _set_search(job_id, "failed",
                    f"Search setup took longer than {config.MAX_ANALYSIS_S} s and was stopped. "
                    "The map and findings are complete.")
        return None
    except Exception as e:
        log.error("job %s: search failed: %s", job_id, type(e).__name__)
        _set_search(job_id, "failed",
                    "Search for questions could not be prepared (internal error).")
        return None
    log.info("job %s: embed %s split_units=%d", job_id, stats, split_units)
    _set_search(job_id, "tests" if test else "ready")
    return test


def search_tests(job_id: int, snapshot_id: int, test: list[Chunk]) -> None:
    """Search, part 2, after Ask is already on: test code, with its own time budget. On
    failure Ask keeps working on non-test code; the state is 'failed' so it can be retried."""
    deadline = time.monotonic() + config.MAX_TEST_EMBED_S
    try:
        stats = embed_group(snapshot_id, job_id, test, True, deadline)
    except JobError:  # the only one embed_group raises: its deadline
        log.warning("job %s: test-code search stopped at its time limit", job_id)
        _set_search(job_id, "failed",
                    f"Test-code search setup timed out after {config.MAX_TEST_EMBED_S}s.")
        return
    except Exception as e:
        log.error("job %s: test-code search failed: %s", job_id, type(e).__name__)
        _set_search(job_id, "failed",
                    "Test code could not be prepared for search (internal error).")
        return
    log.info("job %s: embed %s", job_id, stats)
    _set_search(job_id, "ready")


def parse_stored(snapshot_id: int) -> dict[str, Parsed]:
    """Parse results from the stored (redacted) files, for a search retry: no clone needed."""
    with pool().connection() as conn:
        files = conn.execute(
            "SELECT path, language, content FROM files WHERE snapshot_id = %s"
            " AND language IN ('python', 'javascript', 'typescript') ORDER BY path",
            (snapshot_id,),
        ).fetchall()
    return {f["path"]: Parsed(f["language"], parse_file(f["path"], f["language"], f["content"]),
                              f["content"])
            for f in files}


def claim_search_retry(snapshot_id: int) -> int | None:
    """Mark a finished analysis whose search failed as being prepared again; returns its job id,
    or None when there is nothing to retry (atomic, so two clicks start one retry)."""
    with pool().connection() as conn:
        row = conn.execute(
            "UPDATE jobs SET search_state = 'embedding', search_error = NULL,"
            " progress_done = NULL, progress_total = NULL"
            " WHERE id = (SELECT job_id FROM snapshot_status WHERE snapshot_id = %s)"
            " AND status = 'done'"
            " AND (search_state = 'failed' OR (search_state IS NULL AND search_error IS NOT NULL))"
            " RETURNING id",
            (snapshot_id,),
        ).fetchone()
    return row["id"] if row else None


def run_search_retry(job_id: int, snapshot_id: int) -> None:
    """"Retry preparing search": re-embed from the stored files with a fresh time budget (this
    run does no clone, parse-to-database or detection, so it gets the whole budget)."""
    with _JOB_LOCK:
        _run_search_retry(job_id, snapshot_id)


def _run_search_retry(job_id: int, snapshot_id: int) -> None:
    deadline = time.monotonic() + config.MAX_ANALYSIS_S
    try:
        parsed = parse_stored(snapshot_id)
    except Exception as e:
        log.error("job %s: search retry failed while parsing: %s", job_id, type(e).__name__)
        _set_search(job_id, "failed",
                    "Search for questions could not be prepared (internal error).")
        return
    test = search_first(job_id, snapshot_id, parsed, deadline)
    if test:
        search_tests(job_id, snapshot_id, test)


def run_job(job_id: int, snapshot_id: int, url: str, sha: str) -> None:
    with _JOB_LOCK:
        _run_job(job_id, snapshot_id, url, sha)


def _run_job(job_id: int, snapshot_id: int, url: str, sha: str) -> None:
    workdir = Path(config.WORKSPACE_DIR) / f"job-{job_id}"
    deadline = time.monotonic() + config.MAX_ANALYSIS_S
    stage = "fetch"
    test_chunks = None
    try:
        _set_job(job_id, stage, 5)
        clone.remove_workspace(workdir)  # leftover from an earlier crash
        _fetch_with_retry(job_id, url, sha, workdir, deadline)
        _check_deadline(deadline)

        stage = "discover"
        _set_job(job_id, stage, 20)
        result = discover(workdir, config.MAX_FILES, config.MAX_FILE_BYTES)
        store_files(snapshot_id, result.files)
        _set_receipt(job_id, result)
        log.info(
            "job %s: %d files kept, %d skipped, file limit hit: %s (%d files past it)",
            job_id, len(result.files), result.skipped, result.hit_file_limit, result.beyond_limit,
        )
        _check_deadline(deadline)

        stage = "parse"
        _set_job(job_id, stage, 40)
        parsed = store_symbols(snapshot_id, job_id, deadline)
        log.info("job %s: %d files parsed", job_id, len(parsed))
        _check_deadline(deadline)

        stage = "edges"
        _set_job(job_id, stage, 85)
        counts = store_edges(snapshot_id, parsed)
        log.info("job %s: edges %s", job_id, dict(counts))
        _check_deadline(deadline)

        stage = "detect"
        _set_job(job_id, stage, 90)
        n_findings = store_findings(snapshot_id, parsed, job_id)
        log.info("job %s: %d findings from detectors", job_id, n_findings)
        _check_deadline(deadline)

        # Search: non-test code first (Ask unlocks with it), then the job is done and test
        # code is embedded in the background after the workspace is gone (spec 5.2).
        stage = "embed"
        _set_job(job_id, stage, 92)
        test_chunks = search_first(job_id, snapshot_id, parsed, deadline, percent=(92, 99))

        _set_job(job_id, "done", 100, status="done")
    except (clone.CloneError, JobError) as e:
        log.warning("job %s failed in %s: %s", job_id, stage, e)
        _set_job(job_id, stage, 100, status="failed", error=str(e))
    except Exception as e:
        # Unexpected errors may carry arbitrary text; show the user only the stage.
        log.error("job %s crashed in %s: %s", job_id, stage, type(e).__name__)
        _set_job(job_id, stage, 100, status="failed", error=f"Internal error during {stage}.")
    finally:
        clone.remove_workspace(workdir)
    if test_chunks:
        search_tests(job_id, snapshot_id, test_chunks)
