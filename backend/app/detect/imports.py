"""Broken internal imports: an import that points into this repository but matches no file.

Uses the same resolution as the edges stage (app/ingest/resolve.py), then drops what is
expected to be missing:
  - imports guarded by try/except ImportError (optional dependencies and fallbacks);
  - imports that never run (`if TYPE_CHECKING:`, TS `import type`);
  - generated or compiled modules by name (_version, _speedups, *_pb2 ...);
  - Python namespace packages (a directory of modules with no __init__.py);
  - JS: only relative paths and simple tsconfig aliases count; `@/x`, `~/x`, bare names, and
    paths into generated folders do not; `./data` may be `data.json` or `data.node`.
Nothing here reads anything but the parsed imports and the file list.
"""

import posixpath
import re
from dataclasses import dataclass

from app.ingest.parse import TYPE_ONLY, ParsedImport
from app.ingest.resolve import (
    ASSET_EXTENSIONS,
    JsModules,
    PythonModules,
    resolve_python,
)

# Module names that are written at build time or compiled, so no source file exists to find.
GENERATED_PY = re.compile(
    r"^(?:_version|version|_speedups|_cffi\w*|_ext|_generated\w*|\w*_generated|\w*_pb2|\w*_pb2_grpc)$"
)
GENERATED_JS = re.compile(
    r"(?:^|/)(?:generated|__generated__|gen|dist|build|\.next|node_modules)(?:/|$)"
    r"|\.generated(?:\.|$)"
)
EXTRA_JS_SUFFIXES = (".json", ".node")


@dataclass(frozen=True)
class BrokenImport:
    path: str  # the importing file
    line: int
    target: str  # what was looked for: a dotted module name (Python) or a repo path (JS)


def _python(files: dict[str, list[ParsedImport]]) -> list[BrokenImport]:
    modules = PythonModules(list(files))
    # Every dotted prefix of a known module is a package, a regular one or a namespace directory.
    packages = {
        ".".join(parts[:i])
        for name in modules.by_name
        for parts in [name.split(".")]
        for i in range(1, len(parts) + 1)
    }
    found: dict[tuple[str, int, str], BrokenImport] = {}
    for path, imports in files.items():
        if path.endswith(".pyi"):
            continue
        for imp in imports:
            if imp.guarded or imp.scope == TYPE_ONLY:
                continue
            for target in resolve_python(path, imp, modules):
                if target.kind != "unresolved" or target.key in packages:
                    continue
                if GENERATED_PY.match(target.key.rsplit(".", 1)[-1]):
                    continue
                found.setdefault((path, imp.line, target.key),
                                 BrokenImport(path, imp.line, target.key))
    return list(found.values())


def _probe(modules: JsModules, path: str) -> bool:
    return modules.probe(path) is not None or any(
        path + suffix in modules.paths for suffix in EXTRA_JS_SUFFIXES
    )


def _javascript(files: dict[str, list[ParsedImport]], tsconfig: str | None) -> list[BrokenImport]:
    modules = JsModules(list(files), tsconfig)
    found: dict[tuple[str, int, str], BrokenImport] = {}
    for path, imports in files.items():
        for imp in imports:
            spec = imp.specifier
            if imp.guarded or imp.scope == TYPE_ONLY:
                continue
            if posixpath.splitext(spec.split("?")[0])[1].lower() in ASSET_EXTENSIONS:
                continue
            if spec.startswith(("./", "../")) or spec in (".", ".."):
                joined = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
                if joined == ".." or joined.startswith("../"):
                    continue  # leaves the repository: not ours to judge
            else:
                joined = None
                for alias in modules.aliases:
                    if alias.matches(spec):
                        if alias.target is not None:
                            star = spec[len(alias.prefix): len(spec) - len(alias.suffix)]
                            joined = posixpath.normpath(alias.target.replace("*", star))
                        break
                if joined is None:
                    continue  # a package name, or an alias we cannot follow
            if GENERATED_JS.search(joined) or _probe(modules, joined):
                continue
            found.setdefault((path, imp.line, joined), BrokenImport(path, imp.line, joined))
    return list(found.values())


def broken_imports(
    files: dict[str, tuple[str, list[ParsedImport]]], tsconfig: str | None = None
) -> list[BrokenImport]:
    """`files`: path -> (language, imports) for every parsed code file."""
    python = {p: imps for p, (lang, imps) in files.items() if lang == "python"}
    js = {p: imps for p, (lang, imps) in files.items() if lang != "python"}
    return _python(python) + _javascript(js, tsconfig)
