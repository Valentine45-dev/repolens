"""Entry points found by pattern, from stored (redacted) file text. Nothing is executed or imported:
Python is read with `ast`, TOML with `tomllib`, INI with `configparser`, JSON with `json`.

An entry point is where execution can start from outside the code we analyse: a script's
`__main__` block, a console script, a route or command handler, a package's public API. The
patterns are heuristics and miss things (decorators we do not list, plugins loaded by name,
callbacks passed as arguments); the UI says so.
"""

import ast
import configparser
import json
import posixpath
import re
import tomllib
from dataclasses import dataclass

# Entry-point kinds (the `kind` field of the API).
MAIN_BLOCK = "main-block"
MAIN_MODULE = "main-module"
CONSOLE_SCRIPT = "console-script"
PLUGIN_ENTRY = "plugin-entry"
ROUTE = "route-or-command"
URL_HANDLER = "url-handler"
PUBLIC_API = "public-api"
PACKAGE_MAIN = "package-main"
SHEBANG = "shebang"
FRAMEWORK_MODULE = "framework-module"

# Decorators that register a handler with a framework: Flask, FastAPI, Click, Typer, Celery,
# Django signals. A dotted decorator counts when its last part is listed; a bare one only for
# the names that are unambiguous on their own.
DOTTED_DECORATORS = {
    "route", "get", "post", "put", "delete", "patch", "head", "options", "websocket", "api_route",
    "command", "group", "task", "shared_task", "periodic_task", "on_event", "errorhandler",
    "exception_handler", "before_request", "after_request", "teardown_request",
    "teardown_appcontext", "before_app_request", "after_app_request", "context_processor",
    "app_context_processor", "template_filter", "template_global", "url_value_preprocessor",
    "listener", "middleware", "receiver", "event_handler", "subscriber",
}
BARE_DECORATORS = {"shared_task", "task", "receiver", "periodic_task"}

DJANGO_MODULES = {
    "urls.py", "models.py", "admin.py", "apps.py", "signals.py", "middleware.py", "consumers.py",
    "routing.py", "tasks.py", "wsgi.py", "asgi.py", "settings.py",
}


@dataclass(frozen=True)
class Ref:
    """A pointer at code, before it is matched with a symbol."""

    kind: str
    label: str  # the user-facing name: "black", "app.route"
    source: str  # where it was found: a file path
    module: str | None = None  # dotted module name, or
    path: str | None = None  # a repo file path
    attr: str | None = None  # name inside the module ("main", "app.cli")
    line: int | None = None  # decorator line


# --- Python ---------------------------------------------------------------------------------

def _tree(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _is_main_test(test: ast.expr) -> bool:
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1):
        return False
    sides = [test.left, test.comparators[0]]
    names = [s.id for s in sides if isinstance(s, ast.Name)]
    values = [s.value for s in sides if isinstance(s, ast.Constant)]
    return names == ["__name__"] and values == ["__main__"]


def has_main_block(text: str) -> bool:
    """A top-level `if __name__ == "__main__":` in real code (not in a string or comment)."""
    tree = _tree(text)
    return tree is not None and any(
        isinstance(n, ast.If) and _is_main_test(n.test) for n in tree.body)


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def decorated_entry_lines(text: str) -> list[tuple[int, str]]:
    """(line, decorator) for every decorator on a real function or class that registers a handler.
    Decorators shown in a docstring or a comment are not code and are not found."""
    tree = _tree(text)
    if tree is None:
        return []
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for decorator in node.decorator_list:
            dec = _dotted(decorator)
            if not dec:
                continue
            last = dec.rsplit(".", 1)[-1]
            dotted = "." in dec
            if (dotted and last in DOTTED_DECORATORS) or (not dotted and dec in BARE_DECORATORS):
                found.append((decorator.lineno, dec))
    return sorted(found)


def _split_args(source: str, start: int) -> list[str]:
    """Top-level comma-separated arguments of the call whose '(' is at source[start]."""
    args, depth, quote, current = [], 0, "", []
    i = start
    while i < len(source):
        ch = source[i]
        if quote:
            current.append(ch)
            if ch == "\\":
                i += 1
                if i < len(source):
                    current.append(source[i])
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch in "([{":
            depth += 1
            if depth > 1:
                current.append(ch)
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(current).strip())
                return args
            current.append(ch)
        elif ch == "," and depth == 1:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    return args


_URL_CALL = re.compile(r"\b(?:path|re_path|url)\s*\(")
_AS_VIEW = re.compile(r"\.as_view\s*\(.*\)\s*$", re.DOTALL)


def url_handler_names(text: str) -> list[str]:
    """Django `path('x', views.index)`, `url(r'^x$', views.Home.as_view())`: the handler's own name
    (the last dotted part, after `.as_view(...)` is removed). `include(...)` is not a handler."""
    names = []
    for m in _URL_CALL.finditer(text):
        args = _split_args(text, m.end() - 1)
        if len(args) < 2:
            continue
        view = _AS_VIEW.sub("", args[1])
        if view.startswith("include") or not re.fullmatch(r"[A-Za-z_][\w.]*", view):
            continue
        name = view.rsplit(".", 1)[-1]
        if name not in names:
            names.append(name)
    return names


def is_django_project(paths: set[str], texts: dict[str, str]) -> bool:
    if any(p == "manage.py" or p.endswith("/manage.py") for p in paths):
        return True
    return any(p.endswith("settings.py") and "INSTALLED_APPS" in t for p, t in texts.items())


def _split_target(value: str) -> tuple[str, str | None]:
    """'pkg.mod:func [extra]' -> ('pkg.mod', 'func'); 'pkg.mod' -> ('pkg.mod', None)."""
    value = value.split("[", 1)[0].strip()
    module, _, attr = value.partition(":")
    return module.strip(), (attr.strip() or None)


def _script_refs(source: str, group: str, items: dict) -> list[Ref]:
    is_script = group in ("console_scripts", "gui_scripts", "scripts")
    kind = CONSOLE_SCRIPT if is_script else PLUGIN_ENTRY
    refs = []
    for name, target in items.items():
        if not isinstance(target, str):
            continue
        module, attr = _split_target(target)
        if module:
            refs.append(Ref(kind, str(name), source, module=module, attr=attr))
    return refs


def _pyproject_refs(path: str, text: str) -> list[Ref]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    refs = []
    project = data.get("project", {})
    for group in ("scripts", "gui-scripts"):
        refs += _script_refs(path, "console_scripts", project.get(group, {}))
    for group, items in project.get("entry-points", {}).items():
        refs += _script_refs(path, str(group), items)
    tool = data.get("tool", {})
    poetry = tool.get("poetry", {})
    refs += _script_refs(path, "console_scripts", poetry.get("scripts", {}))
    for group, items in poetry.get("plugins", {}).items():
        refs += _script_refs(path, str(group), items)
    refs += _script_refs(path, "console_scripts", tool.get("flit", {}).get("scripts", {}))
    return refs


def _ini_pairs(value: str) -> dict[str, str]:
    pairs = {}
    for line in value.splitlines():
        name, eq, target = line.partition("=")
        if eq and name.strip() and not name.strip().startswith("#"):
            pairs[name.strip()] = target.strip()
    return pairs


def _setup_cfg_refs(path: str, text: str) -> list[Ref]:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        parser.read_string(text)
    except configparser.Error:
        return []
    refs = []
    for section in ("options.entry_points",):
        if parser.has_section(section):
            for group, value in parser.items(section):
                refs += _script_refs(path, group, _ini_pairs(value))
    return refs


def _setup_py_refs(path: str, text: str) -> list[Ref]:
    """`setup(entry_points={...})`, read as a literal; never run. A name bound to a literal at
    the top of the file is followed once."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    literals: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            literals[node.targets[0].id] = node.value
    refs = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not ((isinstance(fn, ast.Name) and fn.id == "setup")
                or (isinstance(fn, ast.Attribute) and fn.attr == "setup")):
            continue
        for kw in node.keywords:
            if kw.arg != "entry_points":
                continue
            value = kw.value
            if isinstance(value, ast.Name):
                value = literals.get(value.id, value)
            try:
                entry = ast.literal_eval(value)
            except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                continue
            if isinstance(entry, str):
                entry = {"console_scripts": entry.splitlines()}
            if not isinstance(entry, dict):
                continue
            for group, items in entry.items():
                if isinstance(items, str):
                    items = items.splitlines()
                if not isinstance(items, (list, tuple)):
                    continue
                refs += _script_refs(path, str(group), _ini_pairs("\n".join(
                    i for i in items if isinstance(i, str))))
    return refs


def script_refs(path: str, text: str) -> list[Ref]:
    """Console scripts and plugin entry points declared in one packaging file, as written; they
    still have to be matched with a module and a function."""
    name = posixpath.basename(path)
    if name == "pyproject.toml":
        return _pyproject_refs(path, text)
    if name == "setup.cfg":
        return _setup_cfg_refs(path, text)
    if name == "setup.py":
        return _setup_py_refs(path, text)
    return []


def python_exports(
    text: str,
) -> tuple[list[tuple[int, str, str, str]], list[str] | None, list[str]]:
    """What a package's `__init__.py` exposes, read with `ast`:
    - imports: (level, module, original_name, local_name) for every `from m import name [as x]`;
    - `__all__` when it is a literal list/tuple of strings, else None;
    - public names defined in the file (functions and classes without a leading underscore)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return [], None, []
    imports, all_names, defined = [], None, []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    imports.append((node.level, node.module or "", alias.name,
                                    alias.asname or alias.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                defined.append(node.name)
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
                if isinstance(value, (list, tuple)):
                    all_names = [v for v in value if isinstance(v, str)]
    return imports, all_names, defined


# --- JavaScript / TypeScript ----------------------------------------------------------------

_NODE_RUN = re.compile(
    r"\b(?:node|nodemon|ts-node|tsx|babel-node|bun|deno run)\s+(?:--?[\w-]+(?:=\S+)?\s+)*"
    r"(['\"]?)([\w./@-]+\.(?:[mc]?js|jsx|tsx?))\1")


def _json_strings(value, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _json_strings(v, out)
    elif isinstance(value, list):
        for v in value:
            _json_strings(v, out)


def package_json_refs(path: str, text: str) -> list[Ref]:
    """`main`, `module`, `bin`, `exports` and the files that `scripts` run with node, as repo paths
    relative to the package. An empty `main` means `index.js`, as in Node."""
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    base = posixpath.dirname(path)
    refs = []

    def add(field: str, value: str) -> None:
        value = value.strip()
        if not value or value.startswith(("/", "#", "node:")):
            return
        target = posixpath.normpath(posixpath.join(base, value))
        refs.append(Ref(PACKAGE_MAIN, field, path, path=target, attr=field))

    for field in ("main", "module"):
        if isinstance(data.get(field), str):
            add(field, data[field])
    bins: list[str] = []
    _json_strings(data.get("bin"), bins)
    for value in bins:
        add("bin", value)
    exports: list[str] = []
    _json_strings(data.get("exports"), exports)
    for value in exports:
        if value.startswith("./") and not value.endswith(".json"):
            add("exports", value)
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        for command in scripts.values():
            if isinstance(command, str):
                for m in _NODE_RUN.finditer(command):
                    add("scripts", m.group(2))
    if not isinstance(data.get("main"), str):
        refs.append(Ref(PACKAGE_MAIN, "main", path, path=base or ".", attr="index"))
    return refs


def has_shebang(head: str) -> bool:
    """A script meant to be run directly: `#!/usr/bin/env python`, `#!/usr/bin/env node`."""
    first = head.split("\n", 1)[0]
    return first.startswith("#!") and ("python" in first or "node" in first)
