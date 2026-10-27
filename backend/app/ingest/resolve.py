"""Import resolution: does an import point at a repo file, a third-party package, or nothing
we can find? Name-based only; nothing from the repo is executed or installed.
"""

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
