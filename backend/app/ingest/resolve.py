"""Import resolution: does an import point at a repo file, a third-party package, or nothing
we can find? Name-based only; nothing from the repo is executed or installed.
"""

import json
import posixpath
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from app.ingest.parse import ParsedImport, module_name


@dataclass(frozen=True)
class Target:
    kind: str  # internal|external|unresolved
    key: str  # internal: file path; external: top-level package; unresolved: what we looked for


def _join(*parts: str) -> str:
    return ".".join(p for p in parts if p)


def python_source_roots(paths: list[str]) -> list[str]:
    """Directories that act like sys.path entries: the repo root ('') plus the parent of every
    top-level package (a dir with __init__.py whose parent has none), e.g. 'src', 'backend'."""
    present = set(paths)
    roots = {""}
    for p in paths:
        if PurePosixPath(p).name != "__init__.py":
            continue
        parent = PurePosixPath(p).parent.parent.as_posix()
        parent = "" if parent == "." else parent
        if (f"{parent}/__init__.py" if parent else "__init__.py") not in present:
            roots.add(parent)
    return sorted(roots, key=lambda r: (r.count("/"), r))


class PythonModules:
    """Dotted module name -> file path, for every source root."""

    def __init__(self, paths: list[str]):
        self.by_name: dict[str, str] = {}
        # .py before .pyi, so a stub never hides the real module.
        ordered = sorted(paths, key=lambda p: (p.endswith(".pyi"), p))
        for root in python_source_roots(paths):
            for p in ordered:
                if root and not p.startswith(root + "/"):
                    continue
                rel = p[len(root) + 1:] if root else p
                self.by_name.setdefault(module_name(rel), p)
        self.top_level = {name.split(".")[0] for name in self.by_name}

    def missing(self, name: str, relative: bool) -> Target:
        # A relative import, or a missing submodule of one of our own packages, is unresolved;
        # anything else is a third-party (or stdlib) package, keyed by its top-level name.
        top = name.split(".")[0]
        if relative or top in self.top_level:
            return Target("unresolved", name)
        return Target("external", top)


def resolve_python(importer: str, imp: ParsedImport, modules: PythonModules) -> list[Target]:
    spec = imp.specifier
    relative = spec.startswith(".")
    if relative:
        level = len(spec) - len(spec.lstrip("."))
        own = module_name(importer).split(".")
        package = own if PurePosixPath(importer).stem == "__init__" else own[:-1]
        if level - 1 > len(package):
            return [Target("unresolved", spec)]
        base = _join(*package[: len(package) - (level - 1)], spec[level:])
    else:
        base = spec

    is_plain_import = not relative and all(n == "*" and local != "*" for n, local in imp.names)
    if is_plain_import:  # import a.b [as c]
        path = modules.by_name.get(base)
        return [Target("internal", path) if path else modules.missing(base, relative)]

    # from base import name: the submodule base.name first, then base itself.
    targets: list[Target] = []
    for name, _local in imp.names or (("*", "*"),):
        sub = modules.by_name.get(_join(base, name)) if name != "*" else None
        if sub:
            target = Target("internal", sub)
        elif base in modules.by_name:
            target = Target("internal", modules.by_name[base])
        else:
            target = modules.missing(base or spec, relative)
        if target not in targets:
            targets.append(target)
    return targets


# --- JavaScript / TypeScript ---------------------------------------------------------------

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts")
# A TS project imports './x.js' and means './x.ts'.
JS_TO_TS = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
# Imports of these are assets, not code: no edge at all.
ASSET_EXTENSIONS = {
    ".css", ".scss", ".sass", ".less", ".styl", ".svg", ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".ico", ".bmp", ".json", ".html", ".md", ".txt", ".woff", ".woff2", ".ttf",
    ".eot", ".mp3", ".mp4", ".wasm", ".vue", ".svelte",
}
_PACKAGE = re.compile(r"^(@[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*$", re.IGNORECASE)


def strip_jsonc(source: str) -> str:
    """Remove // and /* */ comments and trailing commas (tsconfig.json allows both).
    Comments go first, so a comma followed by a comment and then '}' is still found."""
    return _strip_jsonc(_strip_jsonc(source, commas=False), commas=True)


def _strip_jsonc(source: str, commas: bool) -> str:
    out = []
    i, n, in_string = 0, len(source), False
    while i < n:
        c = source[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 1
            elif c == '"':
                in_string = False
        elif c == '"':
            in_string = True
            out.append(c)
        elif source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1
            continue
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        elif c == "," and commas:
            j = i + 1
            while j < n and source[j] in " \t\r\n":
                j += 1
            if j < n and source[j] in "}]":
                i += 1
                continue
            out.append(c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


@dataclass(frozen=True)
class Alias:
    prefix: str  # pattern before '*'
    suffix: str  # pattern after '*'
    target: str | None  # repo path with one '*', or None when the mapping is not simple
    exact: bool = False  # pattern without '*': matches only itself

    def matches(self, spec: str) -> bool:
        if self.exact:
            return spec == self.prefix
        return (spec.startswith(self.prefix) and spec.endswith(self.suffix)
                and len(spec) >= len(self.prefix) + len(self.suffix))


def read_tsconfig(source: str | None) -> tuple[str | None, list[Alias]]:
    """(baseUrl as a repo path, aliases) from the root tsconfig.json. Paths in the root
    tsconfig resolve against baseUrl when set, otherwise against the repo root."""
    if not source:
        return None, []
    try:
        options = json.loads(strip_jsonc(source)).get("compilerOptions") or {}
    except (ValueError, AttributeError, RecursionError):
        return None, []
    if not isinstance(options, dict):  # e.g. "compilerOptions": [] would fail the edges stage
        return None, []
    base_url = options.get("baseUrl")
    base = posixpath.normpath(base_url) if isinstance(base_url, str) else None
    base = "" if base == "." else base
    aliases = []
    paths = options.get("paths")
    for pattern, targets in (paths.items() if isinstance(paths, dict) else []):
        simple = (
            pattern.count("*") == 1 and isinstance(targets, list) and len(targets) == 1
            and isinstance(targets[0], str) and targets[0].count("*") == 1
        )
        prefix, star, suffix = pattern.partition("*")
        target = posixpath.normpath(posixpath.join(base or "", targets[0])) if simple else None
        aliases.append(Alias(prefix, suffix, target, exact=not star))
    # Like TypeScript: the longest matching prefix wins.
    return base, sorted(aliases, key=lambda a: -len(a.prefix))


def package_name(spec: str) -> str | None:
    """'lodash/fp' -> 'lodash', '@scope/pkg/x' -> '@scope/pkg', 'node:fs' -> 'fs';
    None when it cannot be an npm package ('@/x', '~/x')."""
    spec = spec.removeprefix("node:")
    parts = spec.split("/")
    name = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
    return name if _PACKAGE.match(name) else None


class JsModules:
    def __init__(self, paths: list[str], tsconfig: str | None = None):
        self.paths = set(paths)
        self.base_url, self.aliases = read_tsconfig(tsconfig)

    def probe(self, path: str) -> str | None:
        """The repo file that `path` (no or any extension) refers to, or None.
        '.' is the repo root: only its index file can match."""
        if path == ".":
            return next((f"index{e}" for e in JS_EXTENSIONS if f"index{e}" in self.paths), None)
        if path in self.paths:
            return path
        root, ext = posixpath.splitext(path)
        for alt in JS_TO_TS.get(ext, ()):
            if root + alt in self.paths:
                return root + alt
        for candidate in [path + e for e in JS_EXTENSIONS] + [
            posixpath.join(path, "index" + e) for e in JS_EXTENSIONS
        ]:
            if candidate in self.paths:
                return candidate
        return None


def resolve_js(importer: str, imp: ParsedImport, modules: JsModules) -> list[Target]:
    spec = imp.specifier
    if posixpath.splitext(spec.split("?")[0])[1].lower() in ASSET_EXTENSIONS:
        return []
    if spec.startswith(("./", "../")) or spec in (".", ".."):
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        if joined == ".." or joined.startswith("../"):
            return [Target("unresolved", spec)]
        found = modules.probe(joined)
        return [Target("internal", found) if found else Target("unresolved", joined)]
    if spec.startswith("/"):
        return [Target("unresolved", spec)]

    for alias in modules.aliases:
        if alias.matches(spec):
            if alias.target is None:
                return [Target("unresolved", spec)]
            star = spec[len(alias.prefix): len(spec) - len(alias.suffix)]
            found = modules.probe(posixpath.normpath(alias.target.replace("*", star)))
            return [Target("internal", found) if found else Target("unresolved", spec)]

    if modules.base_url is not None:
        found = modules.probe(posixpath.normpath(posixpath.join(modules.base_url, spec)))
        if found:
            return [Target("internal", found)]

    package = package_name(spec)
    return [Target("external", package) if package else Target("unresolved", spec)]
