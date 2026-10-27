"""Call edges: best-effort, name-based, each with a confidence.

  1.0  f() defined in the same file or explicitly imported; X.f() with X.f in the same file;
       mod.f() where mod is an imported module of ours
  0.9  self.f() / this.f() hitting a method of the caller's own class (or JS object)
  0.5  exactly one candidate in the whole snapshot; for x.f() only when x is a plain name, not
       a JS global, and (for JS object members like `app.f`) x names the owner
  Ambiguous names, and calls into external packages, get no edge.
Plain calls only match functions/classes; x.f() only matches methods (incl. JS `app.f`).
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from app.ingest.parse import ParsedFile, ParsedImport, ParsedSymbol
from app.ingest.resolve import Target

Ref = tuple[str, str]  # (file path, qualified_name)
ImportResolver = Callable[[str, ParsedImport], list[Target]]
SELF_RECEIVERS = {"self", "this", "cls"}
# Built-in objects: Object.create() is never a call into the repo.
GLOBAL_RECEIVERS = {
    "Object", "Array", "JSON", "Math", "Promise", "Reflect", "Number", "String", "Date",
    "Symbol", "Map", "Set", "console", "process", "Buffer", "globalThis", "window", "document",
}
OWNER_NOISE = {"prototype", "exports", "module"}


def is_member(s: ParsedSymbol) -> bool:
    return s.kind == "method" or "." in s.name


def short_name(s: ParsedSymbol) -> str:
    return s.name.rsplit(".", 1)[-1]


def parent(qualified: str) -> str | None:
    """'m.User.save' -> 'm.User'; 'a.ts:App.render' -> 'a.ts:App'; 'a.ts:main' -> None."""
    if ":" in qualified:  # JS: the path before ':' may contain dots
        head, tail = qualified.split(":", 1)
        return f"{head}:{tail.rsplit('.', 1)[0]}" if "." in tail else None
    return qualified.rsplit(".", 1)[0] if "." in qualified else None


@dataclass(frozen=True)
class CallEdge:
    src: Ref
    dst: Ref
    confidence: float


class _Index:
    def __init__(self, files: dict[str, ParsedFile], resolve_import: ImportResolver):
        self.symbols: dict[str, dict[str, ParsedSymbol]] = {}  # path -> qname -> symbol
        self.by_name: dict[str, dict[str, list[ParsedSymbol]]] = {}  # path -> name -> symbols
        self.prefix: dict[str, str] = {}  # path -> what a top-level name is appended to
        # (is JS, is member, name) -> symbols, for the snapshot-wide unique-name rule
        self.unique: dict[tuple[bool, bool, str], list[Ref]] = defaultdict(list)
        self.bindings: dict[str, dict[str, tuple[Target | None, str]]] = {}

        for path, pf in files.items():
            module = next((s for s in pf.symbols if s.kind == "module"), None)
            if module is None:
                continue
            js = module.qualified_name == path  # JS modules are named by path
            self.prefix[path] = f"{path}:" if js else f"{module.qualified_name}."
            qmap: dict[str, ParsedSymbol] = {}
            names: dict[str, list[ParsedSymbol]] = defaultdict(list)
            for s in pf.symbols:
                if s.kind == "module":
                    continue
                qmap.setdefault(s.qualified_name, s)
                names[s.name].append(s)
                member = is_member(s)
                self.unique[(js, member, short_name(s) if member else s.name)].append(
                    (path, s.qualified_name)
                )
            self.symbols[path] = qmap
            self.by_name[path] = names

            binds: dict[str, tuple[Target | None, str]] = {}
            for imp in pf.imports:
                for orig, local in imp.names:
                    if local == "*":  # star import: names unknown
                        continue
                    one = ParsedImport(imp.specifier, ((orig, local),), imp.line)
                    targets = resolve_import(path, one)
                    binds[local] = (targets[0] if targets else None, orig)
            self.bindings[path] = binds

    def top_level(self, path: str, name: str) -> ParsedSymbol | None:
        """A function/class `name` defined at the top of `path`; CommonJS exports count too."""
        qmap = self.symbols.get(path, {})
        prefix = self.prefix.get(path, "")
        s = qmap.get(prefix + name)
        if s is not None and not is_member(s):
            return s
        for exported in (f"exports.{name}", f"module.exports.{name}"):
            if prefix + exported in qmap:
                return qmap[prefix + exported]
        return None

    def find(self, path: str, name: str, depth: int = 0) -> Ref | None:
        """Where `name`, as seen from the top of `path`, is defined: here, or one re-export away."""
        s = self.top_level(path, name)
        if s is not None:
            return (path, s.qualified_name)
        target, orig = self.bindings.get(path, {}).get(name, (None, ""))
        if depth < 2 and target is not None and target.kind == "internal" and orig not in (
            "*", "default"
        ):
            return self.find(target.key, orig, depth + 1)
        return None

    def is_js(self, path: str) -> bool:
        return self.prefix.get(path, "").endswith(":")

    def only(self, js: bool, member: bool, name: str) -> Ref | None:
        """The single symbol with this name in the snapshot (same language), else None."""
        refs = self.unique.get((js, member, name), [])
        return refs[0] if len(refs) == 1 else None


def _resolve(ix: _Index, path: str, caller: str, name: str, receiver: str | None):
    binds = ix.bindings.get(path, {})
    if receiver is None:
        same = [s for s in ix.by_name.get(path, {}).get(name, []) if not is_member(s)]
        if len(same) > 1:
            top = ix.top_level(path, name)
            return ((path, top.qualified_name), 1.0) if top else None
        if same:
            return (path, same[0].qualified_name), 1.0
        if name in binds:
            target, orig = binds[name]
            if target is None or target.kind != "internal":
                return None  # an external package: not ours to link
            found = ix.find(target.key, orig, 1) if orig not in ("*", "default") else None
            if found:
                return found, 1.0
        ref = ix.only(ix.is_js(path), False, name)
        return (ref, 0.5) if ref else None

    if receiver in SELF_RECEIVERS:
        owner = parent(caller)
        s = ix.symbols.get(path, {}).get(f"{owner}.{name}") if owner else None
        if s is not None and is_member(s):
            return (path, s.qualified_name), 0.9
    elif receiver:
        # X.f() with X.f defined in this file (a class, or a JS object like `app`).
        s = ix.symbols.get(path, {}).get(f"{ix.prefix.get(path, '')}{receiver}.{name}")
        if s is not None:
            return (path, s.qualified_name), 1.0
        if receiver in binds:
            target, orig = binds[receiver]
            if target is None or target.kind != "internal":
                return None
            found = ix.find(target.key, name, 1)
            if found:
                return found, 1.0
            # An imported class: Foo.create() -> Foo.create in Foo's file.
            cls = ix.find(target.key, orig, 1) if orig not in ("*", "default") else None
            if cls and f"{cls[1]}.{name}" in ix.symbols.get(cls[0], {}):
                return (cls[0], f"{cls[1]}.{name}"), 1.0
    if not receiver or receiver.split(".")[0] in GLOBAL_RECEIVERS:
        return None  # "".join(), f().x(), Object.create(): not worth a guess
    ref = ix.only(ix.is_js(path), True, name)
    if ref is None or not _owner_matches(ix.symbols[ref[0]][ref[1]], receiver):
        return None
    return ref, 0.5


def _owner_matches(s: ParsedSymbol, receiver: str) -> bool:
    """For a JS object member like `app.set` or `View.prototype.render`, the receiver must name
    the owner (`app.set()`, `this.app.set()`, `view.render()`); class methods match any receiver."""
    if s.kind == "method" and "." not in s.name:
        return True
    owners = [t.lower() for t in s.name.split(".")[:-1] if t not in OWNER_NOISE]
    return receiver.rsplit(".", 1)[-1].lower() in owners


def resolve_calls(files: dict[str, ParsedFile], resolve_import: ImportResolver) -> list[CallEdge]:
    ix = _Index(files, resolve_import)
    best: dict[tuple[Ref, Ref], float] = {}
    for path, pf in files.items():
        for call in pf.calls:
            hit = _resolve(ix, path, call.caller, call.name, call.receiver)
            if hit is None:
                continue
            dst, confidence = hit
            src = (path, call.caller)
            if dst != src and confidence > best.get((src, dst), 0.0):
                best[(src, dst)] = confidence
    return [CallEdge(src, dst, c) for (src, dst), c in best.items()]
