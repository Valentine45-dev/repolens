"""JavaScript/TypeScript detectors: one walk over the Tree-sitter tree (grammar by suffix, as in
parse_js), matching the js-* rules in rules.py."""

from tree_sitter import Node, Parser

from app.detect.rules import Hit, looks_like_sql
from app.ingest.parse import ParsedImport, text
from app.ingest.parse_js import grammar_for

CHILD_PROCESS = {"child_process", "node:child_process"}
EXEC_FUNCS = {"exec", "execSync"}
HTML_PROPS = {"innerHTML", "outerHTML"}


def _child_process_names(imports: list[ParsedImport]) -> tuple[set[str], set[str]]:
    """(local names bound to the child_process module, local names bound to exec/execSync)."""
    modules, funcs = set(), set()
    for imp in imports:
        if imp.specifier not in CHILD_PROCESS:
            continue
        for name, local in imp.names:
            if name in ("*", "default") and local != "*":
                modules.add(local)
            elif name in EXEC_FUNCS:
                funcs.add(local)
    return modules, funcs


def _is_constant_string(node: Node | None) -> bool:
    """A string literal, a template without ${}, or a + chain made only of those."""
    if node is None or node.type not in (
        "string", "template_string", "binary_expression", "parenthesized_expression"
    ):
        return False
    _, dynamic = _literal_parts(node)
    return not dynamic


def _literal_parts(node: Node) -> tuple[list[str], bool]:
    """String text inside an expression and whether anything in it is not a constant."""
    if node.type in ("string", "template_string"):
        parts = [text(c) for c in node.children if c.type == "string_fragment"]
        return parts, any(c.type == "template_substitution" for c in node.children)
    if node.type in ("binary_expression", "parenthesized_expression"):
        parts, dynamic = [], False
        for c in node.named_children:
            p, d = _literal_parts(c)
            parts += p
            dynamic = dynamic or d
        return parts, dynamic
    return [], True


def _is_require_of(node: Node | None, modules: set[str]) -> bool:
    """require("child_process") written inline."""
    if node is None or node.type != "call_expression":
        return False
    fn = node.child_by_field_name("function")
    args = node.child_by_field_name("arguments")
    if fn is None or text(fn) != "require" or args is None or args.named_child_count != 1:
        return False
    arg = args.named_children[0]
    return arg.type == "string" and text(arg)[1:-1] in modules


def detect_javascript(path: str, source: str, imports: list[ParsedImport]) -> list[Hit]:
    tree = Parser(grammar_for(path)).parse(source.encode("utf-8"))
    cp_modules, cp_funcs = _child_process_names(imports)
    hits: set[Hit] = set()

    def line(node: Node) -> int:
        return node.start_point.row + 1

    def is_exec(fn: Node) -> bool:
        if fn.type == "identifier":
            return text(fn) in cp_funcs
        if fn.type == "member_expression":
            obj = fn.child_by_field_name("object")
            prop = text(fn.child_by_field_name("property"))
            if prop not in EXEC_FUNCS or obj is None:
                return False
            return text(obj) in cp_modules or _is_require_of(obj, CHILD_PROCESS)
        return False

    def first_arg(node: Node) -> Node | None:
        args = node.child_by_field_name("arguments")
        return args.named_children[0] if args is not None and args.named_child_count else None

    def visit(node: Node) -> None:
        t = node.type
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier" and text(fn) == "eval":
                hits.add(Hit("js-eval", line(node)))
            if fn is not None and fn.type == "identifier" and text(fn) == "Function":
                hits.add(Hit("js-new-function", line(node)))
            if fn is not None and is_exec(fn):
                arg = first_arg(node)
                if arg is not None and not _is_constant_string(arg):
                    hits.add(Hit("js-child-process-exec", line(node)))
        elif t == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor is not None and text(ctor) == "Function":
                hits.add(Hit("js-new-function", line(node)))
        elif t in ("assignment_expression", "augmented_assignment_expression"):
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if (left is not None and left.type == "member_expression"
                    and text(left.child_by_field_name("property")) in HTML_PROPS
                    and not _is_constant_string(right)):
                hits.add(Hit("js-inner-html", line(node)))
        elif t == "template_string" and any(c.type == "template_substitution"
                                            for c in node.children):
            parts, _ = _literal_parts(node)
            if looks_like_sql(" ".join(parts)):
                hits.add(Hit("js-sql-string", line(node)))
        elif t == "binary_expression" and (
            node.parent is None or node.parent.type != "binary_expression"
        ):
            op = node.child_by_field_name("operator")
            if op is not None and text(op) == "+":
                parts, dynamic = _literal_parts(node)
                if dynamic and looks_like_sql(" ".join(parts)):
                    hits.add(Hit("js-sql-string", line(node)))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return sorted(hits, key=lambda h: (h.line, h.rule_id))
