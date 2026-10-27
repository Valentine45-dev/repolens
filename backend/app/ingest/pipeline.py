"""Runs one ingestion job: fetch -> discover -> parse.

Each stage replaces its own rows (delete-then-insert in one transaction), so a rerun never
duplicates anything. Progress goes to the job row. The clone is always deleted afterwards.
"""

import logging
import time
from pathlib import Path

from app import config
from app.db import pool
from app.ingest import clone
from app.ingest.discover import DiscoveredFile, discover
from app.ingest.parse import ParsedFile, parse_python
from app.ingest.parse_js import parse_js

log = logging.getLogger("repolens.ingest")

SECRET_RULE = "hardcoded-secret"
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
            for s in f.secrets:
                conn.execute(
                    "INSERT INTO findings (snapshot_id, file_id, line, rule_id, severity,"
                    " message, snippet) VALUES (%s, %s, %s, %s, 'high', %s, %s)",
                    (
                        snapshot_id,
                        file_id,
                        s.line,
                        SECRET_RULE,
                        f"Possible hardcoded secret ({s.kind}).",
                        _secret_snippet(f.content, s.line),
                    ),
                )


def parse_file(path: str, language: str, content: str) -> ParsedFile:
    if language == "python":
        return parse_python(path, content)
    return parse_js(path, content)


def store_symbols(snapshot_id: int, job_id: int, deadline: float) -> int:
    """Parse stage: module/class/function/method symbols for every Python and JS/TS file."""
    with pool().connection() as conn:
        files = conn.execute(
            "SELECT id, path, language, content FROM files WHERE snapshot_id = %s"
            " AND language IN ('python', 'javascript', 'typescript') ORDER BY path",
            (snapshot_id,),
        ).fetchall()

    rows = []
    for i, f in enumerate(files, start=1):
        for s in parse_file(f["path"], f["language"], f["content"]).symbols:
            rows.append(
                (snapshot_id, f["id"], s.kind, s.name, s.qualified_name,
                 s.start_line, s.end_line, s.signature)
            )
        if i % 50 == 0:
            _check_deadline(deadline)
            _set_job(job_id, "parse", 40 + int(55 * i / len(files)))

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
    return len(rows)


def run_job(job_id: int, snapshot_id: int, url: str, sha: str) -> None:
    workdir = Path(config.WORKSPACE_DIR) / f"job-{job_id}"
    deadline = time.monotonic() + config.MAX_ANALYSIS_S
    stage = "fetch"
    try:
        _set_job(job_id, stage, 5)
        clone.remove_workspace(workdir)  # leftover from an earlier crash
        clone.fetch_commit(url, sha, workdir, timeout=config.CLONE_TIMEOUT_S)
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
        n_symbols = store_symbols(snapshot_id, job_id, deadline)
        log.info("job %s: %d symbols", job_id, n_symbols)

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
