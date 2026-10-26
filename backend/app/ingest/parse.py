"""Parse stage: Tree-sitter extracts modules, classes, functions and methods from Python.

Tree-sitter tolerates syntax errors, so a broken file still yields what it can.
"""

from dataclasses import dataclass

import tree_sitter_python
from tree_sitter import Language, Node, Parser

_LANGUAGE = Language(tree_sitter_python.language())


@dataclass(frozen=True)
class ParsedSymbol:
    kind: str  # module|class|function|method
    name: str
    qualified_name: str
    start_line: int  # 1-based, inclusive
    end_line: int
    signature: str | None = None


def module_name(path: str) -> str:
    """'pkg/sub/mod.py' -> 'pkg.sub.mod'; 'pkg/__init__.py' -> 'pkg'."""
    parts = path.removesuffix(".pyi").removesuffix(".py").split("/")
    if parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts)


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node and node.text else ""


def _signature(node: Node) -> str:
    name = _text(node.child_by_field_name("name"))
    if node.type == "class_definition":
        bases = _text(node.child_by_field_name("superclasses"))
        return f"class {name}{bases}"
    prefix = "async def" if node.children and node.children[0].type == "async" else "def"
    sig = f"{prefix} {name}{_text(node.child_by_field_name('parameters'))}"
    ret = node.child_by_field_name("return_type")
    return f"{sig} -> {_text(ret)}" if ret else sig


def parse_python(path: str, source: str) -> list[ParsedSymbol]:
    tree = Parser(_LANGUAGE).parse(source.encode("utf-8"))
    module = module_name(path)
    lines = source.count("\n") + (0 if source.endswith("\n") or not source else 1)
    symbols = [ParsedSymbol("module", module.rsplit(".", 1)[-1], module, 1, max(lines, 1))]

    def visit(node: Node, scope: str, in_class: bool) -> None:
        for child in node.named_children:
            if child.type == "decorated_definition":
                definition = child.child_by_field_name("definition")
                if definition is not None:
                    visit_definition(definition, scope, in_class, span=child)
            elif child.type in ("class_definition", "function_definition"):
                visit_definition(child, scope, in_class, span=child)
            else:
                visit(child, scope, in_class)

    def visit_definition(node: Node, scope: str, in_class: bool, span: Node) -> None:
        name = _text(node.child_by_field_name("name"))
        if not name:
            return
        qualified = f"{scope}.{name}"
        if node.type == "class_definition":
            kind = "class"
        else:
            kind = "method" if in_class else "function"
        symbols.append(
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
    return symbols
