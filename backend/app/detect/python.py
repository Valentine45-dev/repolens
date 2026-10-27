"""Python detectors: one walk over the Tree-sitter tree, matching the rules in rules.py."""

from tree_sitter import Node, Parser

from app.detect.rules import Hit, looks_like_sql
from app.ingest.parse import PYTHON_LANGUAGE, ParsedImport, text

SUBPROCESS_FUNCS = {"run", "call", "check_call", "check_output", "Popen"}


def _subprocess_names(imports: list[ParsedImport]) -> tuple[set[str], set[str]]:
    """(local names bound to the subprocess module, local names bound to its functions)."""
    modules, funcs = set(), set()
    for imp in imports:
        if imp.specifier != "subprocess":
            continue
        for name, local in imp.names:
            if name == "*" and local != "*":
                modules.add(local)
            elif name in SUBPROCESS_FUNCS:
                funcs.add(local)
    return modules, funcs


def _literal_parts(node: Node) -> tuple[list[str], bool]:
    """String text inside an expression and whether anything in it is not a constant
    (an identifier, call, f-string interpolation, ...)."""
    if node.type == "string":
        parts = [text(c) for c in node.children if c.type == "string_content"]
        dynamic = any(c.type == "interpolation" for c in node.children)
        return parts, dynamic
    if node.type == "concatenated_string":
        parts, dynamic = [], False
        for c in node.named_children:
            p, d = _literal_parts(c)
            parts += p
            dynamic = dynamic or d
        return parts, dynamic
    if node.type in ("binary_operator", "parenthesized_expression"):
        parts, dynamic = [], False
        for c in node.named_children:
            p, d = _literal_parts(c)
            parts += p
            dynamic = dynamic or d
        return parts, dynamic
    return [], True  # identifiers, calls, attributes, numbers built at runtime...


def detect_python(source: str, imports: list[ParsedImport]) -> list[Hit]:
    tree = Parser(PYTHON_LANGUAGE).parse(source.encode("utf-8"))
    sp_modules, sp_funcs = _subprocess_names(imports)
    hits: set[Hit] = set()

    def line(node: Node) -> int:
        return node.start_point.row + 1

    def is_subprocess_call(fn: Node) -> bool:
        if fn.type == "identifier":
            return text(fn) in sp_funcs
        if fn.type == "attribute":
            obj = fn.child_by_field_name("object")
            attr = text(fn.child_by_field_name("attribute"))
            return obj is not None and text(obj) in sp_modules and attr in SUBPROCESS_FUNCS
        return False

    def visit(node: Node) -> None:
        t = node.type
        if t == "call":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn is not None and fn.type == "identifier" and text(fn) in ("eval", "exec"):
                hits.add(Hit("py-eval-exec", line(node)))
            if fn is not None and args is not None and is_subprocess_call(fn):
                for arg in args.named_children:
                    if (arg.type == "keyword_argument"
                            and text(arg.child_by_field_name("name")) == "shell"
                            and arg.child_by_field_name("value") is not None
                            and arg.child_by_field_name("value").type == "true"):
                        hits.add(Hit("py-subprocess-shell", line(node)))
            # "SELECT ... {}".format(x)
            if (fn is not None and fn.type == "attribute"
                    and text(fn.child_by_field_name("attribute")) == "format"
                    and args is not None and args.named_child_count > 0):
                obj = fn.child_by_field_name("object")
                parts, _ = _literal_parts(obj) if obj is not None else ([], False)
                if obj is not None and obj.type in ("string", "concatenated_string") and \
                        looks_like_sql(" ".join(parts)):
                    hits.add(Hit("py-sql-string", line(node)))
        elif t == "string" and any(c.type == "interpolation" for c in node.children):
            # f"SELECT ... {x}"
            parts, _ = _literal_parts(node)
            if looks_like_sql(" ".join(parts)):
                hits.add(Hit("py-sql-string", line(node)))
        elif t == "binary_operator" and (
            node.parent is None or node.parent.type != "binary_operator"
        ):
            # "SELECT ... " + x, "... %s" % x: only the outermost operator of a chain.
            op = node.child_by_field_name("operator")
            if op is not None and text(op) in ("+", "%"):
                parts, dynamic = _literal_parts(node)
                if dynamic and looks_like_sql(" ".join(parts)):
                    hits.add(Hit("py-sql-string", line(node)))
        elif t == "except_clause":
            typed = [c for c in node.named_children if c.type not in ("block", "comment")]
            if not typed:
                hits.add(Hit("py-bare-except", line(node)))
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return sorted(hits, key=lambda h: (h.line, h.rule_id))
