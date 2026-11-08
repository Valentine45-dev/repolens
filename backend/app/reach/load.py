"""Build the reachability picture of one snapshot from what the pipeline already stored: symbols
and their line ranges, import and call edges, and the (redacted) file text. No schema change, no
parse stage of its own, nothing executed. The result is cached per snapshot and analysis job, so a
re-analysis in place starts a fresh one."""

import logging
import posixpath
import threading
from collections import OrderedDict, defaultdict
from pathlib import PurePosixPath

from app.db import pool
from app.ingest.parse import ParsedImport, module_name
from app.ingest.resolve import JsModules, PythonModules, resolve_python
from app.paths import is_test_path
from app.reach import entries as ent
from app.reach.graph import (
    SOLID_CALL_CONFIDENCE,
    Edge,
    Reach,
    Seed,
    Sym,
    innermost,
    parents_of,
    structural_edges,
)

log = logging.getLogger(__name__)

_CACHE: OrderedDict[tuple[int, int], Reach] = OrderedDict()
_CACHE_MAX = 6
_LOCK = threading.Lock()
_CONFIG_NAMES = r"(^|/)(pyproject\.toml|setup\.cfg|package\.json)$"


class Builder:
    """Everything stored for one snapshot, and the entry points found in it."""

    def __init__(self, files: list[dict], symbols: list[Sym], python_text: dict[str, str],
                 head: dict[str, str]):
        self.path_of = {f["id"]: f["path"] for f in files}
        self.file_of = {f["path"]: f["id"] for f in files}
        self.language = {f["path"]: f["language"] for f in files}
        self.symbols = symbols
        self.python_text = python_text
        self.head = head
        self.by_file: dict[int, list[Sym]] = defaultdict(list)
        for s in symbols:
            self.by_file[s.file_id].append(s)
        self.parent = parents_of(symbols)
        self.module_of = {s.file_id: s for s in symbols if s.kind == "module"}
        self.seeds: list[Seed] = []
        self._seen: set[tuple[int, str]] = set()
        py_paths = [p for p, lang in self.language.items() if lang == "python"]
        self.modules = PythonModules(py_paths)
        self.dotted: dict[str, str] = {}
        names = sorted(self.modules.by_name.items(), key=lambda kv: (-len(kv[0]), kv[0]))
        for dotted, path in names:
            self.dotted[path] = dotted  # the shortest dotted name wins (last write)
        self.js = JsModules([p for p, lang in self.language.items()
                             if lang in ("javascript", "typescript")], None)

    # -- helpers -----------------------------------------------------------------------------

    def add(self, symbol: Sym | None, kind: str, label: str, detail: str = "") -> None:
        if symbol is not None and (symbol.id, kind) not in self._seen:
            self._seen.add((symbol.id, kind))
            self.seeds.append(Seed(symbol.id, kind, label, detail))

    def module(self, path: str) -> Sym | None:
        fid = self.file_of.get(path)
        return self.module_of.get(fid) if fid is not None else None

    def top_level(self, path: str, name: str) -> list[Sym]:
        fid = self.file_of.get(path)
        module = self.module_of.get(fid) if fid is not None else None
        if module is None:
            return []
        return [s for s in self.by_file[fid] if s.name == name and s.kind in ("function", "class")
                and self.parent.get(s.id) == module.id]

    def public_methods(self, cls: Sym) -> list[Sym]:
        return [s for s in self.by_file[cls.file_id]
                if s.kind == "method" and self.parent.get(s.id) == cls.id
                and (not s.name.startswith("_") or s.name in ("__init__", "__call__"))]

    def add_with_module(self, symbol: Sym | None, kind: str, label: str, detail: str = "") -> None:
        """A function or class is an entry point; its module ran when it was imported."""
        if symbol is None:
            return
        self.add(symbol, kind, label, detail)
        module = self.module_of.get(symbol.file_id)
        if module is not None and module.id != symbol.id:
            self.add(module, kind, f"`{self.path_of[symbol.file_id]}` (module of {label})", detail)
        if symbol.kind == "class":
            for method in self.public_methods(symbol):
                self.add(method, kind, label, detail)

    def probe_python(self, base: str, dotted: str) -> str | None:
        rel = dotted.replace(".", "/")
        for root in ([f"{base}/src", base] if base else ["src", ""]):
            for candidate in (f"{root}/{rel}.py", f"{root}/{rel}/__init__.py"):
                candidate = candidate.lstrip("/")
                if candidate in self.file_of:
                    return candidate
        return self.modules.by_name.get(dotted)

    # -- entry-point rules -------------------------------------------------------------------

    def detect(self) -> None:
        texts = self.python_text
        code_texts = {p: t for p, t in texts.items() if p.endswith(".py") and not is_test_path(p)}
        for path, text in sorted(code_texts.items()):
            module = self.module(path)
            if module is None:
                continue
            if posixpath.basename(path) == "__main__.py":
                self.add(module, ent.MAIN_MODULE, f"`{path}` (python -m)", path)
            if ent.has_main_block(text):
                self.add(module, ent.MAIN_BLOCK, f"`{path}` (runs as a script)", path)
            if ent.has_shebang(self.head.get(path, "")):
                self.add(module, ent.SHEBANG, f"`{path}` (script with a shebang)", path)
            for line, decorator in ent.decorated_entry_lines(text):
                fid = self.file_of[path]
                items = [s for s in self.by_file[fid] if s.kind in ("function", "method", "class")]
                symbol = innermost(items, line)
                if symbol is not None and symbol.kind != "module":
                    self.add_with_module(symbol, ent.ROUTE, f"`{symbol.name}` (@{decorator})", path)
            if posixpath.basename(path) == "urls.py":
                self._url_handlers(path, text)
        if ent.is_django_project(set(self.language), texts):
            self._django(code_texts)
        for path, text in sorted(texts.items()):
            if not is_test_path(path):
                self._script_refs(path, text)
        self._public_api(code_texts)
        for path, text in sorted(texts.items()):
            if posixpath.basename(path) == "package.json" and not is_test_path(path):
                self._package_json(path, text)
        for path, head in sorted(self.head.items()):
            if self.language.get(path) in ("javascript", "typescript") and not is_test_path(path) \
                    and ent.has_shebang(head):
                self.add(self.module(path), ent.SHEBANG, f"`{path}` (script with a shebang)", path)

    def _url_handlers(self, path: str, text: str) -> None:
        names = set(ent.url_handler_names(text))
        if not names:
            return
        for p in self.file_of:
            if self.language.get(p) != "python" or is_test_path(p) or "view" not in p.lower():
                continue
            for name in names:
                for symbol in self.top_level(p, name):
                    self.add_with_module(symbol, ent.URL_HANDLER,
                                         f"`{symbol.name}` (routed in `{path}`)", path)

    def _django(self, code_texts: dict[str, str]) -> None:
        for path in sorted(code_texts):
            base = posixpath.basename(path)
            if base in ent.DJANGO_MODULES or "/templatetags/" in path:
                self.add(self.module(path), ent.FRAMEWORK_MODULE,
                         f"`{path}` (loaded by Django)", path)
            if "/management/commands/" in path:
                for cls in self.top_level(path, "Command"):
                    self.add_with_module(cls, ent.FRAMEWORK_MODULE,
                                         f"`{path}` (Django management command)", path)

    def _script_refs(self, path: str, text: str) -> None:
        for ref in ent.script_refs(path, text):
            base = posixpath.dirname(path)
            target = self.probe_python(base, ref.module or "")
            if target is None:
                continue
            label = (f"console script `{ref.label}`" if ref.kind == ent.CONSOLE_SCRIPT
                     else f"plugin entry point `{ref.label}`")
            detail = f"{path}: {ref.module}:{ref.attr}" if ref.attr else f"{path}: {ref.module}"
            attr = (ref.attr or "").split(".")[0]
            symbols = self.top_level(target, attr) if attr else []
            if symbols:
                for symbol in symbols:
                    self.add_with_module(symbol, ref.kind, label, detail)
            else:
                self.add(self.module(target), ref.kind, label, detail)

    def _public_api(self, code_texts: dict[str, str]) -> None:
        for path, text in sorted(code_texts.items()):
            if posixpath.basename(path) != "__init__.py":
                continue
            if any(part.startswith("_") for part in PurePosixPath(path).parts[:-1]):
                continue  # a private subpackage is not public API
            package = self.dotted.get(path, module_name(path))
            self.add(self.module(path), ent.PUBLIC_API, f"public API of `{package}`", path)
            imports, all_names, defined = ent.python_exports(text)
            bound: dict[str, tuple[int, str, str]] = {}  # local name -> (level, module, original)
            for level, mod, original, local in imports:
                bound[local] = (level, mod, original)
            names = all_names if all_names is not None else \
                [n for n in bound if not n.startswith("_")] + defined
            for name in dict.fromkeys(names):
                label = f"public API `{name}` of `{package}`"
                if name in defined or name not in bound:
                    for symbol in self.top_level(path, name):
                        self.add_with_module(symbol, ent.PUBLIC_API, label, path)
                    continue
                level, mod, original = bound[name]
                imp = ParsedImport("." * level + mod, ((original, name),), 1)
                for target in resolve_python(path, imp, self.modules):
                    if target.kind != "internal":
                        continue
                    symbols = self.top_level(target.key, original)
                    if symbols:
                        for symbol in symbols:
                            self.add_with_module(symbol, ent.PUBLIC_API, label, path)
                    elif module_name(target.key).rsplit(".", 1)[-1] == original:
                        self.add(self.module(target.key), ent.PUBLIC_API, label, path)

    def _package_json(self, path: str, text: str) -> None:
        for ref in ent.package_json_refs(path, text):
            found = self.js.probe(ref.path or ".")
            if found is None:
                continue
            field = "main" if ref.attr == "index" else ref.attr
            what = f"package.json {field}"
            self.add(self.module(found), ent.PACKAGE_MAIN, f"`{found}` ({what})", path)


def _edges(rows: list[dict], nested_sites: dict[int, list[int]], symbols: dict[int, Sym],
           by_file: dict[int, list[Sym]]) -> list[Edge]:
    out = []
    for r in rows:
        src, dst = symbols.get(r["src_id"]), symbols.get(r["dst_id"])
        if src is None or dst is None or dst.kind != "module" and r["type"] == "imports":
            continue
        if r["type"] == "calls":
            guess = round(r["confidence"], 2) < SOLID_CALL_CONFIDENCE
            out.append(Edge(src.id, dst.id, guess, "calls"))
            continue
        scope = r["import_scope"]
        if scope == "type_checking":
            continue  # never runs
        if scope == "nested":
            lines = nested_sites.get(r["id"], [])
            if not lines:  # analysed before sites existed: the module might run it
                out.append(Edge(src.id, dst.id, True, "imports"))
                continue
            for line in lines:
                where = innermost(by_file[src.file_id], line)
                out.append(Edge((where or src).id, dst.id, False, "imports"))
            continue
        out.append(Edge(src.id, dst.id, False, "imports"))
    return out


def build(snapshot_id: int) -> Reach:
    with pool().connection() as conn:
        files = conn.execute(
            "SELECT id, path, language FROM files WHERE snapshot_id = %s", (snapshot_id,)
        ).fetchall()
        sym_rows = conn.execute(
            "SELECT id, file_id, kind, name, qualified_name, start_line, end_line FROM symbols"
            " WHERE snapshot_id = %s AND file_id IS NOT NULL", (snapshot_id,)
        ).fetchall()
        edge_rows = conn.execute(
            "SELECT id, src_id, dst_id, type, confidence, import_scope FROM edges"
            " WHERE snapshot_id = %s AND type IN ('imports', 'calls')", (snapshot_id,)
        ).fetchall()
        site_rows = conn.execute(
            "SELECT e.id AS edge_id, s.line FROM edge_sites s JOIN edges e ON e.id = s.edge_id"
            " WHERE e.snapshot_id = %s AND e.type = 'imports' AND e.import_scope = 'nested'",
            (snapshot_id,),
        ).fetchall()
        text_rows = conn.execute(
            "SELECT path, content FROM files WHERE snapshot_id = %s"
            " AND (language = 'python' OR path ~ %s)", (snapshot_id, _CONFIG_NAMES),
        ).fetchall()
        head_rows = conn.execute(
            "SELECT path, left(content, 200) AS head FROM files WHERE snapshot_id = %s"
            " AND language IN ('python', 'javascript', 'typescript')", (snapshot_id,),
        ).fetchall()
    symbols = [Sym(r["id"], r["file_id"], r["kind"], r["name"], r["qualified_name"],
                   r["start_line"] or 1, r["end_line"] or r["start_line"] or 1) for r in sym_rows]
    builder = Builder(files, symbols, {r["path"]: r["content"] or "" for r in text_rows},
                      {r["path"]: r["head"] or "" for r in head_rows})
    builder.detect()
    nested: dict[int, list[int]] = defaultdict(list)
    for r in site_rows:
        nested[r["edge_id"]].append(r["line"])
    by_id = {s.id: s for s in symbols}
    edges = _edges(edge_rows, nested, by_id, builder.by_file)
    edges += structural_edges(symbols, builder.path_of)
    return Reach(symbols, edges, builder.seeds, set(builder.module_of))


def get_reach(snapshot_id: int) -> Reach:
    """The cached picture for the snapshot's latest finished job."""
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT job_id FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
        ).fetchone()
    key = (snapshot_id, row["job_id"] if row else 0)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
        reach = build(snapshot_id)
        _CACHE[key] = reach
        for old in [k for k in _CACHE if k[0] == snapshot_id and k != key]:
            del _CACHE[old]
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
        return reach
