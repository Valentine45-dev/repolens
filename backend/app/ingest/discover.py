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


def _skip_dir(path: Path) -> bool:
    return (
        path.name in SKIP_DIRS
        or path.name.endswith(".egg-info")
        or (path / "pyvenv.cfg").exists()  # a virtualenv under any name
    )


def _wanted(path: Path) -> bool:
    name = path.name
    if name.startswith(".env") or name in SECRET_NAMES or path.suffix.lower() in SECRET_SUFFIXES:
        return False
    if LANGUAGES.get(path.suffix) == "javascript" and path.stem.endswith(GENERATED_JS_MARKERS):
        return False
    return path.suffix in LANGUAGES or path.suffix.lower() in TEXT_SUFFIXES


def _looks_minified(text: str) -> bool:
    lines = text.split("\n")
    longest = max(len(line) for line in lines)
    return longest > MINIFIED_MAX_LINE or len(text) / len(lines) > MINIFIED_AVG_LINE


def discover(root: Path, max_files: int, max_file_bytes: int) -> DiscoverResult:
    root = root.resolve()
    result = DiscoverResult(files=[])
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not _skip_dir(current / d))
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink() or not _wanted(path):
                result.skipped += 1
                continue
            if not path.resolve().is_relative_to(root):
                result.skipped += 1
                continue
            try:
                if path.stat().st_size > max_file_bytes:
                    result.skipped += 1
                    continue
                raw = path.read_bytes()
            except OSError:  # e.g. a path over 260 characters on Windows without long paths
                result.skipped += 1
                continue
            if b"\0" in raw[:8192]:
                result.skipped += 1
                continue
            if len(result.files) >= max_files:
                result.hit_file_limit = True
                return result

            text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
            language = LANGUAGES.get(path.suffix)
            if language in ("javascript", "typescript") and _looks_minified(text):
                result.skipped += 1
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
    return result
