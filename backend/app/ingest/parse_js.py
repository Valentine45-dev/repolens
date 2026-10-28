"""Parse stage for JavaScript/TypeScript: symbols, imports and calls via Tree-sitter.

Grammar by suffix: .ts -> typescript, .tsx -> tsx, everything else -> javascript (handles JSX).
Qualified names: the module is its path ('web/src/app.ts'); members are 'path:Name' and
'path:Class.method' (paths contain dots, so ':' keeps them unambiguous).
"""

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

from app.ingest.parse import (
    ParsedCall,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    line_count,
    text,
)

_JS = Language(tree_sitter_javascript.language())
_TS = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())

CLASS_TYPES = {"class_declaration", "abstract_class_declaration"}
FUNCTION_TYPES = {"function_declaration", "generator_function_declaration"}
FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}


def grammar_for(path: str) -> Language:
    if path.endswith(".tsx"):
        return _TSX
    if path.endswith(".ts"):
        return _TS
    return _JS


def _string(node: Node | None) -> str | None:
    """Value of a plain string literal ('x', "x", or `x` without ${}); None otherwise."""
    if node is None:
        return None
    if node.type == "string":
        return text(node)[1:-1]
    if node.type == "template_string" and not any(
        c.type == "template_substitution" for c in node.named_children
    ):
        return text(node)[1:-1]
    return None


def _single_string_arg(call: Node) -> str | None:
    args = call.child_by_field_name("arguments")
    if args is None or args.named_child_count != 1:
        return None
    return _string(args.named_children[0])


def _receiver(node: Node | None) -> str:
    """Text of `a`, `this` or `a.b.c`; '' for anything else."""
    if node is None:
        return ""
    if node.type in ("identifier", "this"):
        return text(node)
    if node.type == "member_expression":
        inner = _receiver(node.child_by_field_name("object"))
        return f"{inner}.{text(node.child_by_field_name('property'))}" if inner else ""
    return ""


def _pattern_names(pattern: Node) -> tuple[tuple[str, str], ...]:
    """Bindings from `x` or `{ a, b: c }` on the left of `= require(...)`."""
    if pattern.type == "identifier":
        return (("*", text(pattern)),)
    names = []
    if pattern.type == "object_pattern":
        for child in pattern.named_children:
            if child.type == "shorthand_property_identifier_pattern":
                names.append((text(child), text(child)))
            elif child.type == "pair_pattern":
                value = child.child_by_field_name("value")
                if value is not None and value.type == "identifier":
                    names.append((text(child.child_by_field_name("key")), text(value)))
    return tuple(names)


def _import_clause_names(clause: Node) -> list[tuple[str, str]]:
    names = []
    for child in clause.named_children:
        if child.type == "identifier":
            names.append(("default", text(child)))
        elif child.type == "namespace_import":
            ident = next((c for c in child.named_children if c.type == "identifier"), None)
            names.append(("*", text(ident)))
        elif child.type == "named_imports":
            for spec in child.named_children:
                if spec.type == "import_specifier":
                    name = text(spec.child_by_field_name("name"))
                    alias = spec.child_by_field_name("alias")
                    names.append((name, text(alias) if alias else name))
    return names


def _export_from_names(node: Node) -> list[tuple[str, str]]:
    names = []
    for child in node.named_children:
        if child.type == "export_clause":
            for spec in child.named_children:
                if spec.type == "export_specifier":
                    name = text(spec.child_by_field_name("name"))
                    alias = spec.child_by_field_name("alias")
                    names.append((name, text(alias) if alias else name))
        elif child.type == "namespace_export":
            ident = next((c for c in child.named_children if c.type == "identifier"), None)
            names.append(("*", text(ident)))
    if not names:  # export * from './x'
        names.append(("*", "*"))
    return names


def _function_signature(node: Node, name: str, prefix: str) -> str:
    params = node.child_by_field_name("parameters") or node.child_by_field_name("parameter")
    ret = text(node.child_by_field_name("return_type"))
    is_async = bool(node.children) and node.children[0].type == "async"
    return f"{'async ' if is_async else ''}{prefix}{name}{text(params)}{ret}"


def _value_signature(lead: str, value: Node) -> str:
    """'const f = (a) =>', 'app.listen = function listen(port)', 'stop: function ()'."""
    if value.type == "arrow_function":
        return f"{lead}{_function_signature(value, '', '')} =>"
    return lead + _function_signature(value, text(value.child_by_field_name("name")), "function ")


def parse_js(path: str, source: str) -> ParsedFile:
    tree = Parser(grammar_for(path)).parse(source.encode("utf-8"))
    module = path
    out = ParsedFile()
    stem = path.rsplit("/", 1)[-1].split(".", 1)[0]
    out.symbols.append(ParsedSymbol("module", stem, module, 1, line_count(source)))

    def member(scope: str, name: str) -> str:
        return f"{scope}:{name}" if scope == module else f"{scope}.{name}"

    def define(kind: str, name: str, scope: str, span: Node, signature: str) -> str:
        qualified = member(scope, name)
        out.symbols.append(ParsedSymbol(
            kind, name, qualified, span.start_point.row + 1, span.end_point.row + 1, signature,
        ))
        return qualified

    def define_function(kind: str, name: str, scope: str, span: Node, value: Node,
                        signature: str) -> None:
        qualified = define(kind, name, scope, span, signature)
        body = value.child_by_field_name("body")
        if body is not None:
            visit_node(body, qualified)

    def visit_object(obj: Node, prefix: str, scope: str) -> None:
        """Top-level `x = { a() {}, b: function () {}, c: () => 1 }` -> methods x.a, x.b, x.c."""
        for prop in obj.named_children:
            if prop.type == "method_definition":
                key = text(prop.child_by_field_name("name"))
                define_function("method", f"{prefix}.{key}", scope, prop, prop,
                                _function_signature(prop, key, ""))
                continue
            value = prop.child_by_field_name("value") if prop.type == "pair" else None
            if value is not None and value.type in FUNCTION_VALUES:
                key = text(prop.child_by_field_name("key"))
                define_function("method", f"{prefix}.{key}", scope, prop, value,
                                _value_signature(f"{key}: ", value))
                continue
            visit_node(prop, scope)

    def add_import(specifier: str, names, node: Node) -> None:
        out.imports.append(ParsedImport(specifier, tuple(names), node.start_point.row + 1))

    def visit(node: Node, scope: str) -> None:
        for child in node.named_children:
            visit_node(child, scope)

    def visit_node(node: Node, scope: str) -> None:
        t = node.type
        if t == "import_statement":
            spec = _string(node.child_by_field_name("source"))
            if spec is not None:
                clause = next((c for c in node.named_children if c.type == "import_clause"), None)
                add_import(spec, _import_clause_names(clause) if clause else [], node)
            return
        if t == "export_statement":
            spec = _string(node.child_by_field_name("source"))
            if spec is not None:
                add_import(spec, _export_from_names(node), node)
                return
            visit(node, scope)
            return
        if t in CLASS_TYPES:
            name = text(node.child_by_field_name("name"))
            body = node.child_by_field_name("body")
            if not name:
                visit(node, scope)
                return
            heritage = next((c for c in node.named_children if c.type == "class_heritage"), None)
            sig = f"class {name}" + (f" {text(heritage)}" if heritage else "")
            qualified = define("class", name, scope, node, sig)
            if heritage is not None:
                visit(heritage, scope)
            if body is not None:
                visit_node(body, qualified)
            return
        if t == "method_definition":
            name = text(node.child_by_field_name("name"))
            qualified = define("method", name, scope, node, _function_signature(node, name, ""))
            body = node.child_by_field_name("body")
            if body is not None:
                visit_node(body, qualified)
            return
        if t in FUNCTION_TYPES:
            name = text(node.child_by_field_name("name"))
            if not name:
                visit(node, scope)
                return
            sig = _function_signature(node, name, "function ")
            qualified = define("function", name, scope, node, sig)
            body = node.child_by_field_name("body")
            if body is not None:
                visit_node(body, qualified)
            return
        if t == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            if value is not None and value.type == "call_expression":
                fn = value.child_by_field_name("function")
                spec = _single_string_arg(value)
                if fn is not None and text(fn) == "require" and spec is not None:
                    add_import(spec, _pattern_names(name_node), value)
                    return
            # Only top-level `const f = () => ...` / `const o = { m() {} }` become symbols.
            if (scope == module and value is not None
                    and name_node is not None and name_node.type == "identifier"):
                name = text(name_node)
                if value.type in FUNCTION_VALUES:
                    span = node.parent if node.parent is not None else node
                    define_function("function", name, scope, span, value,
                                    _value_signature(f"const {name} = ", value))
                    return
                if value.type == "object":
                    visit_object(value, name, scope)
                    return
            visit(node, scope)
            return
        if t == "assignment_expression" and scope == module:
            # CommonJS style: `app.listen = function listen() {}`, `exports.y = () => {}`,
            # `module.exports = function name() {}`, `module.exports = { a() {} }`.
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            is_member = left is not None and left.type == "member_expression"
            target = _receiver(left) if is_member else ""
            if target and right is not None and right.type in FUNCTION_VALUES:
                name = target
                if target == "module.exports":
                    name = text(right.child_by_field_name("name")) or target
                parent = node.parent
                is_statement = parent is not None and parent.type == "expression_statement"
                span = parent if is_statement else node
                define_function("function", name, scope, span, right,
                                _value_signature(f"{target} = ", right))
                return
            if target and right is not None and right.type == "object":
                visit_object(right, target, scope)
                return
            visit(node, scope)
            return
        if t == "call_expression":
            fn = node.child_by_field_name("function")
            spec = _single_string_arg(node)
            is_import = fn is not None and (fn.type == "import" or text(fn) == "require")
            if is_import and spec is not None:
                add_import(spec, [], node)
                return
            record_call(fn, scope, node)
            visit(node, scope)
            return
        if t == "new_expression":
            record_call(node.child_by_field_name("constructor"), scope, node)
            visit(node, scope)
            return
        visit(node, scope)

    def record_call(fn: Node | None, scope: str, node: Node) -> None:
        line = node.start_point.row + 1
        if fn is None:
            return
        if fn.type == "identifier":
            out.calls.append(ParsedCall(scope, text(fn), None, line))
        elif fn.type == "member_expression":
            prop = fn.child_by_field_name("property")
            out.calls.append(ParsedCall(
                scope, text(prop), _receiver(fn.child_by_field_name("object")), line,
            ))

    visit(tree.root_node, module)
    return out
