"""Code-quality findings from Ruff, run on a temporary copy of the (redacted) Python files.

Ruff is the one tool besides ESLint-style linters allowed to read repo files (CLAUDE.md rule 14):
it gets the files as data, with no repository configuration (`--isolated`), no cache, no fixes
and `# noqa` comments ignored, so the repository cannot switch rules off. The copy holds the
redacted text, so no secret value reaches Ruff or its output. Ruff makes no network calls.

How it is started matters as much as its flags. `python -m ruff` with the copy as working
directory puts the copy first on `sys.path`, so a repository file named `ruff.py`, `types.py`,
`subprocess.py` (and others the launcher imports) would be run by Python (review S-01). So the
Ruff binary itself is run, never Python: from an empty working directory, with the copy passed as
an absolute path and an environment that holds no API key, database URL or proxy credential.
"""

import functools
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.detect.ruff_catalogue import RUFF_CODES, RUFF_IGNORE, RUFF_SELECT
from app.detect.rules import RUFF_PREFIX
from app.subproc import run_bounded

log = logging.getLogger(__name__)

# What the Ruff binary gets from the API's environment. It needs none of it to run (checked with
# an empty environment); these only keep Windows system calls and temp folders working.
ENV_ALLOWLIST = ("SYSTEMROOT", "TEMP", "TMP", "TMPDIR")

TIMEOUT_S = 60
MAX_PER_FILE = 50  # a generated file can trigger thousands; the first ones make the point
MAX_MESSAGE = 300


class RuffError(RuntimeError):
    """Ruff did not complete. The text is safe to show to the user."""


@dataclass(frozen=True)
class RuffHit:
    path: str
    line: int
    rule_id: str  # ruff-<CODE>
    message: str


@functools.cache
def ruff_binary() -> str:
    """Absolute path of the Ruff executable installed with the backend (resolved by the API
    process, never by anything in a repository)."""
    from ruff import find_ruff_bin

    return str(Path(find_ruff_bin()).resolve())


def ruff_env() -> dict[str, str]:
    return {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}


def ruff_command(binary: str, src: Path) -> list[str]:
    return [
        binary, "check", "--isolated", "--no-cache", "--no-fix", "--ignore-noqa", "--exit-zero",
        "--output-format", "json", "--target-version", "py312",
        "--select", ",".join(RUFF_SELECT), "--ignore", ",".join(RUFF_IGNORE), "--", str(src),
    ]


COPY_FAILED = "Code-quality checks did not run: the files could not be copied for checking."


def run_ruff(files: dict[str, str], timeout: float = TIMEOUT_S) -> list[RuffHit]:
    """`files`: repo path -> redacted text, Python files only. Returns the hits for the codes in
    the catalogue, at most MAX_PER_FILE per file."""
    files = {p: c for p, c in files.items() if p.endswith(".py")}
    if not files:
        return []
    try:
        binary = ruff_binary()
    except OSError:  # ruff.RuffNotFound is a FileNotFoundError
        raise RuffError("Code-quality checks could not be started.") from None
    try:
        # Cleanup errors are ignored: after a timeout kill Windows can hold a file for a moment,
        # and a leftover temp folder must not fail the whole detect stage.
        tmp_dir = tempfile.TemporaryDirectory(prefix="repolens-ruff-", ignore_cleanup_errors=True)
    except OSError:
        raise RuffError(COPY_FAILED) from None
    with tmp_dir as tmp:
        root = (Path(tmp) / "src").resolve()  # the copy
        work = Path(tmp) / "cwd"  # Ruff's working directory: always empty
        try:
            root.mkdir()
            work.mkdir()
            for rel, content in files.items():
                target = (root / rel).resolve()
                if not target.is_relative_to(root):
                    continue  # a path that climbs out of the copy is never written
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
        except OSError:  # a path too long for Windows, a full disk
            raise RuffError(COPY_FAILED) from None
        try:
            proc = run_bounded(ruff_command(binary, root), cwd=work, env=ruff_env(),
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuffError(f"Code-quality checks timed out after {int(timeout)} s.") from None
        except OSError:
            raise RuffError("Code-quality checks could not be started.") from None
        if proc.returncode != 0:
            log.warning("ruff exited with %s", proc.returncode)
            raise RuffError("Code-quality checks failed to run.")
        try:
            items = json.loads(proc.stdout or "[]")
        except ValueError:
            raise RuffError("Code-quality checks returned output that could not be read.") from None

        per_file: dict[str, int] = {}
        hits = []
        for item in items:
            code = item.get("code")
            if code not in RUFF_CODES:  # syntax errors have no code; unknown codes are ignored
                continue
            try:
                rel = Path(item["filename"]).resolve().relative_to(root).as_posix()
                line = int(item["location"]["row"])
            except (KeyError, TypeError, ValueError):
                continue
            if per_file.get(rel, 0) >= MAX_PER_FILE:
                continue
            per_file[rel] = per_file.get(rel, 0) + 1
            hits.append(RuffHit(rel, line, RUFF_PREFIX + code,
                                str(item.get("message", ""))[:MAX_MESSAGE]))
    return hits
