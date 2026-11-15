"""Call edges: best-effort, name-based, each with a confidence.

  1.0  f() visible at the call: defined at the top of the file, inside an enclosing function,
       or explicitly imported; X.f() with X.f in the same file; mod.f() where mod is an
       imported module of ours; Cls.f() where Cls is an imported class of ours
  0.9  self.f() / this.f() hitting a method of the caller's own class (or JS object)
  0.5  exactly one candidate in the whole snapshot; for x.f() only when x is a plain name, not
       a JS global, and (for JS object members like `app.f`) x names the owner. Also any 1.0
       match above when the name (or the receiver's first name) is a parameter or local
       variable of an enclosing function: it may hold that function, or anything else.
  Ambiguous names, and calls into external packages, get no edge. A function nested inside
  another function is never the target of a call it is not visible from.
Plain calls only match functions/classes; x.f() only matches methods (incl. JS `app.f`).
"""

import builtins
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

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
# Never guessed as a repo function: Python's builtins and the functions JS gets from its runtime.
PY_BUILTINS = frozenset(n for n in dir(builtins) if not n.startswith("_"))
JS_GLOBAL_FUNCTIONS = frozenset({
    "fetch", "setTimeout", "setInterval", "setImmediate", "clearTimeout", "clearInterval",
    "clearImmediate", "queueMicrotask", "structuredClone", "requestAnimationFrame",
    "cancelAnimationFrame", "parseInt", "parseFloat", "isNaN", "isFinite", "encodeURI",
    "encodeURIComponent", "decodeURI", "decodeURIComponent", "escape", "unescape", "eval",
    "alert", "confirm", "prompt", "atob", "btoa", "Symbol", "Number", "String", "Boolean",
    "BigInt", "Array", "Object", "Date", "RegExp", "Error", "TypeError", "RangeError",
    "SyntaxError", "ReferenceError", "EvalError", "URIError", "AggregateError", "Promise", "Map",
    "Set", "WeakMap", "WeakSet", "WeakRef", "Proxy", "ArrayBuffer", "DataView", "URL",
    "URLSearchParams", "TextEncoder", "TextDecoder", "AbortController", "Event", "EventTarget",
    "Blob", "FormData", "Headers", "Request", "Response", "WebSocket", "Worker",
})


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
    # Every call site that resolved to this pair: (line, that site's own confidence), one per
    # line (the best confidence on that line), in line order. `confidence` is the maximum.
    sites: tuple[tuple[int, float], ...] = ()


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


GUESS = 0.5


def _child(ix: _Index, path: str, scope: str, name: str) -> str:
    if ix.is_js(path) and scope == path:
        return f"{path}:{name}"
    return f"{scope}.{name}"


def _visible_def(ix: _Index, path: str, caller: str, name: str) -> Ref | None:
    """`name` is defined inside an enclosing function of `caller`: the definition in the nearest
    one (the caller itself, then enclosing functions; class bodies do not count). JS: a
    declaration inside an anonymous callback is named after the nearest named scope, so at the
    top of the file it looks like a top-level symbol, and that one counts too."""
    qmap = ix.symbols.get(path, {})
    js = ix.is_js(path)
    module = path if js else ix.prefix.get(path, ".")[:-1]
    scope: str | None = caller
    first = True
    while scope is not None:
        if scope == module:
            s = qmap.get(f"{path}:{name}") if js else None
            return (path, s.qualified_name) if s is not None and not is_member(s) else None
        own = qmap.get(scope)
        if first or (own is not None and own.kind in ("function", "method")):
            s = qmap.get(_child(ix, path, scope, name))
            if s is not None and not is_member(s):
                return (path, s.qualified_name)
        first = False
        scope = parent(scope) or (module if js else None)
    return None


def _is_module_binding(target: Target, orig: str, js: bool) -> bool:
    """`orig` names the imported file itself, not a class or function inside it. JS default
    imports keep counting as the module (CommonJS `module.exports = {...}` objects)."""
    if orig == "*":
        return True
    if js:
        return orig == "default"
    p = PurePosixPath(target.key)
    return p.stem == orig or (p.stem == "__init__" and p.parent.name == orig)


def _top_level_guess(ix: _Index, js: bool, name: str) -> Ref | None:
    """The single function/class with this name in the snapshot, if it is a top-level one: a
    function nested inside another is not visible from any other place."""
    ref = ix.only(js, False, name)
    if ref is None:
        return None
    top = ix.top_level(ref[0], name)
    return ref if top is not None and top.qualified_name == ref[1] else None


def _resolve(ix: _Index, path: str, caller: str, name: str, receiver: str | None,
             bound: str | None = None):
    binds = ix.bindings.get(path, {})
    js = ix.is_js(path)
    # A parameter or local variable with this name: whatever it holds, it is not provably the
    # same-named function, so any match is a guess.
    cap = GUESS if bound == "local" or (receiver and bound == "def") else 1.0
    imported_here = bound == "import"  # imported inside the function: the import wins
    if receiver is None:
        same = [s for s in ix.by_name.get(path, {}).get(name, []) if not is_member(s)]
        if bound == "def":
            ref = _visible_def(ix, path, caller, name)
            return (ref, 1.0) if ref else None
        top = ix.top_level(path, name)
        if top is not None and not imported_here:
            return (path, top.qualified_name), cap
        if name in binds:
            target, orig = binds[name]
            if target is None or target.kind != "internal":
                return None  # an external package: not ours to link
            found = ix.find(target.key, orig, 1) if orig not in ("*", "default") else None
            if found:
                return found, cap
        if same:
            # Defined only inside other functions here. A local variable may hold one of them
            # (a factory's result): a guess when there is just one; a plain global name never.
            if bound == "local" and len(same) == 1:
                return (path, same[0].qualified_name), GUESS
            return None
        if name in (JS_GLOBAL_FUNCTIONS if js else PY_BUILTINS):
            return None  # open(), len(), fetch(): the runtime's, never a guess into the repo
        ref = _top_level_guess(ix, js, name)
        return (ref, GUESS) if ref else None

    first = receiver.split(".")[0]
    if receiver in SELF_RECEIVERS:
        owner = parent(caller)
        s = ix.symbols.get(path, {}).get(f"{owner}.{name}") if owner else None
        if s is not None and is_member(s):
            return (path, s.qualified_name), 0.9
    elif receiver:
        # X.f() with X.f defined in this file (a class, or a JS object like `app`).
        s = ix.symbols.get(path, {}).get(f"{ix.prefix.get(path, '')}{receiver}.{name}")
        if s is not None and not imported_here:
            return (path, s.qualified_name), cap
        if receiver in binds:
            target, orig = binds[receiver]
            if target is None or target.kind != "internal":
                return None
            if _is_module_binding(target, orig, js):
                found = ix.find(target.key, name, 1)
                if found:
                    return found, cap
            # An imported class: Foo.create() -> Foo.create in Foo's file.
            cls = ix.find(target.key, orig, 1) if orig not in ("*", "default") else None
            if cls and f"{cls[1]}.{name}" in ix.symbols.get(cls[0], {}):
                return (cls[0], f"{cls[1]}.{name}"), cap
        elif first in binds and (binds[first][0] is None or binds[first][0].kind != "internal"):
            return None  # os.path.join(): the first name is an external import
    if not receiver or first in GLOBAL_RECEIVERS:
        return None  # "".join(), f().x(), Object.create(): not worth a guess
    if (not js and first in PY_BUILTINS and first not in binds and bound is None
            and ix.top_level(path, first) is None):
        return None  # str.join(), dict.fromkeys(): a builtin type, not a repo class
    ref = ix.only(js, True, name)
    if ref is None or not _owner_matches(ix.symbols[ref[0]][ref[1]], receiver):
        return None
    return ref, GUESS


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
    sites: dict[tuple[Ref, Ref], dict[int, float]] = defaultdict(dict)
    for path, pf in files.items():
        for call in pf.calls:
            hit = _resolve(ix, path, call.caller, call.name, call.receiver, call.bound)
            if hit is None:
                continue
            dst, confidence = hit
            src = (path, call.caller)
            if dst == src:
                continue
            if confidence > best.get((src, dst), 0.0):
                best[(src, dst)] = confidence
            at = sites[(src, dst)]
            at[call.line] = max(confidence, at.get(call.line, 0.0))
    return [CallEdge(src, dst, c, tuple(sorted(sites[(src, dst)].items())))
            for (src, dst), c in best.items()]
