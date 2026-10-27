"""Parse stage: Tree-sitter extracts symbols, imports and calls from Python.

Tree-sitter tolerates syntax errors, so a broken file still yields what it can.
The JS/TS parser (parse_js.py) returns the same ParsedFile shape.
"""

from dataclasses import dataclass, field

import tree_sitter_python
from tree_sitter import Language, Node, Parser

PYTHON_LANGUAGE = Language(tree_sitter_python.language())
_LANGUAGE = PYTHON_LANGUAGE


@dataclass(frozen=True)
class ParsedSymbol:
    kind: str  # module|class|function|method
    name: str
    qualified_name: str
    start_line: int  # 1-based, inclusive
    end_line: int
    signature: str | None = None


@dataclass(frozen=True)
class ParsedImport:
    specifier: str  # as written: 'os.path', '.models', '.', './lib', 'node:fs', 'react'
    # (imported, local) pairs. imported '*' binds the whole module to local
    # (import a.b as c, import * as ns, const x = require(...)); local '*' is a star import.
    names: tuple[tuple[str, str], ...]
    line: int


@dataclass(frozen=True)
class ParsedCall:
    caller: str  # qualified_name of the innermost enclosing symbol (module at top level)
    name: str  # callee name: f in f(), x.f(), self.f(), new F()
    receiver: str | None  # None for f(); 'self', 'this', 'mod', 'a.b' for x.f(); '' if not a name
    line: int


@dataclass
class ParsedFile:
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)


def module_name(path: str) -> str:
    """'pkg/sub/mod.py' -> 'pkg.sub.mod'; 'pkg/__init__.py' -> 'pkg'."""
    parts = path.removesuffix(".pyi").removesuffix(".py").split("/")
    if parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts)


def line_count(source: str) -> int:
    return max(source.count("\n") + (0 if source.endswith("\n") or not source else 1), 1)


def text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node and node.text else ""


def _signature(node: Node) -> str:
    name = text(node.child_by_field_name("name"))
    if node.type == "class_definition":
        bases = text(node.child_by_field_name("superclasses"))
        return f"class {name}{bases}"
    prefix = "async def" if node.children and node.children[0].type == "async" else "def"
    sig = f"{prefix} {name}{text(node.child_by_field_name('parameters'))}"
    ret = node.child_by_field_name("return_type")
    return f"{sig} -> {text(ret)}" if ret else sig


def _receiver(node: Node) -> str:
    """Text of `a` or `a.b.c`; '' for anything else (calls, subscripts, literals)."""
    if node.type == "identifier":
        return text(node)
    if node.type == "attribute":
        inner = _receiver(node.child_by_field_name("object"))
        return f"{inner}.{text(node.child_by_field_name('attribute'))}" if inner else ""
    return ""


def _from_import(node: Node) -> ParsedImport:
    """`from .m import a, b as c` -> ParsedImport('.m', (('a', 'a'), ('b', 'c')))."""
    module_node = node.child_by_field_name("module_name")
    names = []
    for child in node.named_children:
        if child == module_node:
            continue
        if child.type == "wildcard_import":
            names.append(("*", "*"))
        elif child.type == "aliased_import":
            names.append((text(child.child_by_field_name("name")),
                          text(child.child_by_field_name("alias"))))
        elif child.type == "dotted_name":
            names.append((text(child), text(child)))
    return ParsedImport(text(module_node), tuple(names), node.start_point.row + 1)


def _plain_imports(node: Node) -> list[ParsedImport]:
    """`import a.b, c as d` -> one ParsedImport per module."""
    line = node.start_point.row + 1
    result = []
    for child in node.named_children:
        if child.type == "aliased_import":
            module = text(child.child_by_field_name("name"))
            result.append(ParsedImport(module, (("*", text(child.child_by_field_name("alias"))),),
                                       line))
        elif child.type == "dotted_name":
            result.append(ParsedImport(text(child), (("*", text(child)),), line))
    return result


def parse_python(path: str, source: str) -> ParsedFile:
    tree = Parser(_LANGUAGE).parse(source.encode("utf-8"))
    module = module_name(path)
    out = ParsedFile()
    out.symbols.append(
        ParsedSymbol("module", module.rsplit(".", 1)[-1], module, 1, line_count(source))
    )

    def visit(node: Node, scope: str, in_class: bool) -> None:
        for child in node.named_children:
            if child.type == "decorated_definition":
                definition = child.child_by_field_name("definition")
                for dec in child.named_children:
                    if dec != definition:
                        visit(dec, scope, in_class)
                if definition is not None:
                    visit_definition(definition, scope, in_class, span=child)
            elif child.type in ("class_definition", "function_definition"):
                visit_definition(child, scope, in_class, span=child)
            elif child.type == "import_statement":
                out.imports.extend(_plain_imports(child))
            elif child.type == "import_from_statement":
                out.imports.append(_from_import(child))
            elif child.type == "call":
                fn = child.child_by_field_name("function")
                if fn is not None and fn.type == "identifier":
                    out.calls.append(ParsedCall(scope, text(fn), None, child.start_point.row + 1))
                elif fn is not None and fn.type == "attribute":
                    out.calls.append(ParsedCall(
                        scope, text(fn.child_by_field_name("attribute")),
                        _receiver(fn.child_by_field_name("object")), child.start_point.row + 1,
                    ))
                visit(child, scope, in_class)
            else:
                visit(child, scope, in_class)

    def visit_definition(node: Node, scope: str, in_class: bool, span: Node) -> None:
        name = text(node.child_by_field_name("name"))
        if not name:
            return
        qualified = f"{scope}.{name}"
        if node.type == "class_definition":
            kind = "class"
        else:
            kind = "method" if in_class else "function"
        out.symbols.append(
            ParsedSymbol(
                kind=kind,
                name=name,
                qualified_name=qualified,
                start_line=span.start_point.row + 1,
                end_line=span.end_point.row + 1,
                signature=_signature(node),
            )
        )
        body = node.child_by_field_name("body")
        if body is not None:
            visit(body, qualified, in_class=node.type == "class_definition")

    visit(tree.root_node, module, in_class=False)
    return out
