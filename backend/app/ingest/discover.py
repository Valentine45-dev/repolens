"""Discover stage: walk a clone, skip what we must not read, redact what we keep."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from app.ingest.redact import CONFIG_SUFFIXES, SecretMatch, redact

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", ".tox", ".nox", ".eggs",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist", "site-packages", "htmlcov",
    "bower_components", ".next", "coverage",
}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der", ".crt"}
SECRET_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".pgpass", ".npmrc"}

# Python and JS/TS are analysed; the rest is kept so secrets in config are reported and docs can
# be cited. .tsx gets the tsx grammar at parse time, chosen by suffix.
LANGUAGES = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
}
# Generated JS: app.min.js, main.bundle.js, 123.chunk.js (also .mjs/.cjs).
GENERATED_JS_MARKERS = (".min", ".bundle", ".chunk")
# Minified code that is not named as such: very long lines.
MINIFIED_MAX_LINE = 5000
MINIFIED_AVG_LINE = 300
TEXT_SUFFIXES = {
    ".md", ".rst", ".txt", ".toml", ".cfg", ".ini", ".yaml", ".yml", ".json", ".sh",
}


@dataclass
class DiscoveredFile:
    path: str  # relative, forward slashes
    language: str | None
    loc: int
    content: str  # redacted
    secrets: list[SecretMatch] = field(default_factory=list)


@dataclass
class DiscoverResult:
    files: list[DiscoveredFile]
    skipped: int = 0
    hit_file_limit: bool = False
    beyond_limit: int = 0  # files past the limit that the skip rules would have kept
    # Every file walked but not kept (skipped, past the limit, binary, minified), so the
    # broken-import rule knows they exist. Names of secret files are left out. None when there
    # were more than MAX_UNREAD_PATHS: not recorded, which is not the same as none.
    unread_paths: list[str] | None = field(default_factory=list)


MAX_UNREAD_PATHS = 50_000


def _skip_dir(path: Path) -> bool:
    return (
        path.name in SKIP_DIRS
        or path.name.endswith(".egg-info")
        or (path / "pyvenv.cfg").exists()  # a virtualenv under any name
    )


def _secret_file(path: Path) -> bool:
    name = path.name
    return name.startswith(".env") or name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES


def _wanted(path: Path) -> bool:
    if _secret_file(path):
        return False
    if LANGUAGES.get(path.suffix) == "javascript" and path.stem.endswith(GENERATED_JS_MARKERS):
        return False
    return path.suffix in LANGUAGES or path.suffix.lower() in TEXT_SUFFIXES


def _candidate(path: Path, root: Path, max_file_bytes: int) -> bool:
    """The skip rules that need no file contents. Files past the file limit are counted with
    these same rules (skipped folders never reach here), so the total is close to what would
    have been analysed; only binaries and minified files, which need a read, can still be in it."""
    if path.is_symlink() or not _wanted(path) or not path.resolve().is_relative_to(root):
        return False
    try:
        return path.stat().st_size <= max_file_bytes
    except OSError:  # e.g. a path over 260 characters on Windows without long paths
        return False


def _looks_minified(text: str) -> bool:
    lines = text.split("\n")
    longest = max(len(line) for line in lines)
    return longest > MINIFIED_MAX_LINE or len(text) / len(lines) > MINIFIED_AVG_LINE


def discover(root: Path, max_files: int, max_file_bytes: int) -> DiscoverResult:
    root = root.resolve()
    result = DiscoverResult(files=[])
    unread: list[str] = []

    def leave_out(path: Path) -> None:
        if not _secret_file(path):
            unread.append(path.relative_to(root).as_posix())

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(current / d))
        for name in sorted(filenames):
            path = current / name
            if not _candidate(path, root, max_file_bytes):
                result.skipped += 1
                leave_out(path)
                continue
            if len(result.files) >= max_files:
                # Keep walking, without reading: the notice says how much was left out.
                result.hit_file_limit = True
                result.beyond_limit += 1
                leave_out(path)
                continue
            try:
                raw = path.read_bytes()
            except OSError:  # e.g. a path over 260 characters on Windows without long paths
                result.skipped += 1
                leave_out(path)
                continue
            if b"\0" in raw[:8192]:
                result.skipped += 1
                leave_out(path)
                continue

            text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
            language = LANGUAGES.get(path.suffix)
            if language in ("javascript", "typescript") and _looks_minified(text):
                result.skipped += 1
                leave_out(path)
                continue
            content, secrets = redact(text, config=path.suffix.lower() in CONFIG_SUFFIXES)
            result.files.append(
                DiscoveredFile(
                    path=path.relative_to(root).as_posix(),
                    language=language,
                    loc=content.count("\n") + (0 if content.endswith("\n") or not content else 1),
                    content=content,
                    secrets=secrets,
                )
            )
    result.unread_paths = unread if len(unread) <= MAX_UNREAD_PATHS else None
    return result
