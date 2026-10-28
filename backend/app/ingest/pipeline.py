"""Runs one ingestion job: fetch -> discover -> parse -> edges -> detect -> embed.

Each stage replaces its own rows (delete-then-insert in one transaction), so a rerun never
duplicates anything. Progress goes to the job row. The clone is always deleted afterwards.
"""

import logging
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.db import pool
from app.detect import detect
from app.detect.rules import DETECTOR_RULES, RULES, SECRET_RULE
from app.ingest import clone
from app.ingest.calls import resolve_calls
from app.ingest.discover import DiscoveredFile, discover
from app.ingest.parse import ParsedFile, ParsedImport, ParsedSymbol, parse_python
from app.ingest.parse_js import parse_js
from app.ingest.resolve import JsModules, PythonModules, Target, resolve_js, resolve_python
from app.paths import is_test_path
from app.qa.chunks import Chunk, build_chunks, search_words
from app.qa.embed import get_embedder

log = logging.getLogger("repolens.ingest")

PARSER_KINDS = ("module", "class", "function", "method")


class JobError(RuntimeError):
    """An expected failure whose message is safe to show the user."""


def _set_job(job_id: int, stage: str, percent: int, status: str = "running", error=None) -> None:
    with pool().connection() as conn:
        conn.execute(
            "UPDATE jobs SET stage = %s, percent = %s, status = %s, error = %s WHERE id = %s",
            (stage, percent, status, error, job_id),
        )


def _check_deadline(deadline: float) -> None:
    if time.monotonic() > deadline:
        raise JobError(f"Analysis took longer than {config.MAX_ANALYSIS_S}s and was stopped.")


def _secret_snippet(content: str, line: int) -> str:
    lines = content.splitlines()
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
            # Placeholder keys in tests are common and rarely real: report them, but low.
            in_test = is_test_path(f.path)
            for s in f.secrets:
                conn.execute(
                    "INSERT INTO findings (snapshot_id, file_id, line, rule_id, severity,"
                    " message, snippet, in_test) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        snapshot_id,
                        file_id,
                        s.line,
                        SECRET_RULE,
                        "low" if in_test else "high",
                        f"Possible hardcoded secret ({s.kind})"
                        + (" in test or example code." if in_test else "."),
                        _secret_snippet(f.content, s.line),
                        in_test,
                    ),
                )


def parse_file(path: str, language: str, content: str) -> ParsedFile:
    if language == "python":
        return parse_python(path, content)
    return parse_js(path, content)


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
            _set_job(job_id, "parse", 40 + int(40 * i / len(files)))

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

    wanted: dict[tuple[str, Target], None] = {}  # ordered set
    for path, p in parsed.items():
        for imp in p.result.imports:
            for target in resolve_import(path, imp):
                if not (target.kind == "internal" and target.key == path):
                    wanted[(path, target)] = None
    calls = resolve_calls({path: p.result for path, p in parsed.items()}, resolve_import)

    counts: Counter = Counter()
    with pool().connection() as conn, conn.transaction():
        conn.execute(
            "DELETE FROM edges WHERE snapshot_id = %s AND type IN ('imports', 'calls')",
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

        rows = []
        for path, target in wanted:
            dst = module_ids.get(target.key) if target.kind == "internal" else node_ids[target]
            if dst is not None:
                rows.append((snapshot_id, module_ids[path], dst))
                counts[target.kind] += 1
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO edges (snapshot_id, src_id, dst_id, type, confidence)"
                " VALUES (%s, %s, %s, 'imports', 1.0)",
                rows,
            )

        symbol_ids: dict[tuple[str, str], int] = {}
        for r in conn.execute(
            "SELECT f.path, s.qualified_name, s.id FROM symbols s JOIN files f ON f.id = s.file_id"
            " WHERE s.snapshot_id = %s ORDER BY s.id",
            (snapshot_id,),
        ):
            symbol_ids.setdefault((r["path"], r["qualified_name"]), r["id"])
        call_rows = []
        for edge in calls:
            src, dst = symbol_ids.get(edge.src), symbol_ids.get(edge.dst)
            if src is not None and dst is not None:
                call_rows.append((snapshot_id, src, dst, edge.confidence))
                counts[f"calls@{edge.confidence}"] += 1
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO edges (snapshot_id, src_id, dst_id, type, confidence)"
                " VALUES (%s, %s, %s, 'calls', %s)",
                call_rows,
            )
    return counts


def _innermost_symbol(symbols: list[ParsedSymbol], line: int) -> ParsedSymbol | None:
    """The smallest symbol (function, method, class, or else the module) containing `line`."""
    containing = [s for s in symbols if s.start_line <= line <= s.end_line]
    return min(containing, key=lambda s: s.end_line - s.start_line, default=None)


def store_findings(snapshot_id: int, parsed: dict[str, Parsed]) -> int:
    """Detect stage: rule findings for every code file. Replaces only the detector rules'
    findings; hardcoded-secret findings belong to the discover stage."""
    rows = []
    for path, p in parsed.items():
        hits = detect(path, p.language, p.content, p.result)
        if not hits:
            continue
        lines = p.content.splitlines()
        for hit in hits:
            rule = RULES[hit.rule_id]
            symbol = _innermost_symbol(p.result.symbols, hit.line)
            snippet = lines[hit.line - 1].strip()[:200] if hit.line <= len(lines) else ""
            rows.append((path, symbol.qualified_name if symbol else None, hit.line, rule.id,
                         rule.severity, rule.title, snippet))

    with pool().connection() as conn, conn.transaction():
        conn.execute(
            "DELETE FROM findings WHERE snapshot_id = %s AND rule_id = ANY(%s)",
            (snapshot_id, DETECTOR_RULES),
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
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO findings (snapshot_id, file_id, symbol_id, line, rule_id, severity,"
                " message, snippet, in_test) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (snapshot_id, file_ids[path], ids.get((path, qname), (None, None))[1],
                     line, rule_id, severity, message, snippet, is_test_path(path))
                    for path, qname, line, rule_id, severity, message, snippet in rows
                ],
            )
    return len(rows)


def store_chunks(snapshot_id: int, job_id: int, parsed: dict[str, Parsed],
                 deadline: float) -> dict:
    """Embed stage: chunks (functions, methods, classes, top-level code) from the redacted
    content, embedded with the configured model. Returns stats for the log and PROGRESS."""
    embedder = get_embedder()
    chunks: list[Chunk] = []
    split_units: set[tuple[str, str, int]] = set()
    for path, p in parsed.items():
        for c in build_chunks(path, p.content, p.result.symbols, embedder.count_tokens,
                              embedder.max_tokens):
            chunks.append(c)
            if c.window:
                split_units.add((c.path, c.qualified_name, c.unit_start))
    _check_deadline(deadline)

    started = time.monotonic()
    vectors: list[list[float]] = []
    step = 256
    for i in range(0, len(chunks), step):
        vectors += embedder.embed([c.embed_text for c in chunks[i:i + step]])
        _check_deadline(deadline)
        _set_job(job_id, "embed", 92 + int(7 * min(i + step, len(chunks)) / max(len(chunks), 1)))
    embed_seconds = time.monotonic() - started

    with pool().connection() as conn, conn.transaction():
        conn.execute("DELETE FROM chunks WHERE snapshot_id = %s", (snapshot_id,))
        symbol_ids: dict[tuple[str, str], int] = {}
        for r in conn.execute(
            "SELECT f.path, s.qualified_name, s.id FROM symbols s JOIN files f ON f.id = s.file_id"
            " WHERE s.snapshot_id = %s ORDER BY s.id DESC",
            (snapshot_id,),
        ):
            symbol_ids[(r["path"], r["qualified_name"])] = r["id"]  # lowest id wins
        rows = [
            (snapshot_id, symbol_ids[(c.path, c.qualified_name)], c.start_line, c.end_line,
             c.token_count, c.text, search_words(c), "[" + ",".join(f"{x:.6f}" for x in v) + "]")
            for c, v in zip(chunks, vectors, strict=True)
            if (c.path, c.qualified_name) in symbol_ids
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO chunks (snapshot_id, symbol_id, start_line, end_line, token_count,"
                " text, search_tsv, embedding)"
                " VALUES (%s, %s, %s, %s, %s, %s, to_tsvector('simple', %s), %s::vector)",
                rows,
            )
    return {
        "chunks": len(rows),
        "windows": sum(1 for c in chunks if c.window),
        "split_units": len(split_units),
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


def run_job(job_id: int, snapshot_id: int, url: str, sha: str) -> None:
    workdir = Path(config.WORKSPACE_DIR) / f"job-{job_id}"
    deadline = time.monotonic() + config.MAX_ANALYSIS_S
    stage = "fetch"
    try:
        _set_job(job_id, stage, 5)
        clone.remove_workspace(workdir)  # leftover from an earlier crash
        _fetch_with_retry(job_id, url, sha, workdir, deadline)
        _check_deadline(deadline)

        stage = "discover"
        _set_job(job_id, stage, 20)
        result = discover(workdir, config.MAX_FILES, config.MAX_FILE_BYTES)
        store_files(snapshot_id, result.files)
        log.info(
            "job %s: %d files kept, %d skipped, file limit hit: %s",
            job_id, len(result.files), result.skipped, result.hit_file_limit,
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
        n_findings = store_findings(snapshot_id, parsed)
        log.info("job %s: %d findings from detectors", job_id, n_findings)
        _check_deadline(deadline)

        stage = "embed"
        _set_job(job_id, stage, 92)
        stats = store_chunks(snapshot_id, job_id, parsed, deadline)
        log.info("job %s: embed %s", job_id, stats)

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
