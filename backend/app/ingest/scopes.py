"""Which enclosing function binds a name, and how. Used by call resolution so that a call to a
parameter or local variable is not linked, at full confidence, to a same-named function.

A binding kind is one of:
  "def"    a function or class defined in that scope (or a name assigned a lambda / arrow);
  "import" a name imported inside the function;
  "local"  any other binding: a parameter, an assignment, a loop or `with` target, ...;
  None     no enclosing function binds it: the name is the module's (or a builtin).
Class bodies are not scopes for the functions inside them (as in Python), and JS block scopes
are folded into the function (a slight over-approximation: it can only lower a confidence).
"""

from tree_sitter import Node


def text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node and node.text else ""

PY_SCOPES = {"function_definition", "lambda", "list_comprehension", "set_comprehension",
             "dictionary_comprehension", "generator_expression"}
JS_SCOPES = {"function_declaration", "generator_function_declaration", "function_expression",
             "function", "generator_function", "arrow_function", "method_definition",
             "catch_clause"}
JS_FUNCTION_VALUES = {"arrow_function", "function_expression", "function", "generator_function",
                      "class"}


def _merge(kinds: set[str]) -> str:
    if "global" in kinds:
        return "global"
    if "nonlocal" in kinds:
        return "nonlocal"
    if len(kinds) == 1:
        return next(iter(kinds))
    return "local"


def _py_names(node: Node | None, out: list[str]) -> None:
    """Names bound by an assignment target or a parameter list."""
    if node is None:
        return
    if node.type == "identifier":
        out.append(text(node))
    elif node.type in ("default_parameter", "typed_default_parameter"):
        _py_names(node.child_by_field_name("name"), out)
    elif node.type in ("pattern_list", "tuple_pattern", "list_pattern", "tuple", "list",
                       "parenthesized_expression", "list_splat_pattern", "list_splat",
                       "dictionary_splat_pattern", "as_pattern_target", "typed_parameter",
                       "parameters", "lambda_parameters"):
        for child in node.named_children:
            if child.type != "type":
                _py_names(child, out)


class PythonScopes:
    def __init__(self) -> None:
        self._cache: dict[int, dict[str, str]] = {}

    def bindings(self, scope: Node) -> dict[str, str]:
        found = self._cache.get(scope.id)
        if found is not None:
            return found
        kinds: dict[str, set[str]] = {}

        def bind(names: list[str], kind: str) -> None:
            for n in names:
                if n:
                    kinds.setdefault(n, set()).add(kind)

        def walk(node: Node) -> None:
            for child in node.named_children:
                t = child.type
                if t == "decorated_definition":
                    definition = child.child_by_field_name("definition")
                    if definition is not None:
                        bind([text(definition.child_by_field_name("name"))], "def")
                elif t in ("function_definition", "class_definition"):
                    bind([text(child.child_by_field_name("name"))], "def")
                elif t in PY_SCOPES:
                    continue  # its own scope
                elif t == "assignment":
                    left = child.child_by_field_name("left")
                    right = child.child_by_field_name("right")
                    names: list[str] = []
                    _py_names(left, names)
                    is_def = (left is not None and left.type == "identifier"
                              and right is not None and right.type == "lambda")
                    bind(names, "def" if is_def else "local")
                    if right is not None:
                        walk(right)
                elif t in ("augmented_assignment", "for_statement", "for_in_clause"):
                    names = []
                    _py_names(child.child_by_field_name("left"), names)
                    bind(names, "local")
                    walk(child)
                elif t == "named_expression":
                    bind([text(child.child_by_field_name("name"))], "local")
                    walk(child)
                elif t == "as_pattern_target":
                    names = []
                    _py_names(child, names)
                    bind(names, "local")
                elif t == "import_statement":
                    for item in child.named_children:
                        if item.type == "aliased_import":
                            bind([text(item.child_by_field_name("alias"))], "import")
                        elif item.type == "dotted_name":
                            bind([text(item).split(".")[0]], "import")
                elif t == "import_from_statement":
                    module = child.child_by_field_name("module_name")
                    for item in child.named_children:
                        if item == module:
                            continue
                        if item.type == "aliased_import":
                            bind([text(item.child_by_field_name("alias"))], "import")
                        elif item.type == "dotted_name":
                            bind([text(item)], "import")
                elif t in ("global_statement", "nonlocal_statement"):
                    bind([text(i) for i in child.named_children if i.type == "identifier"],
                         "global" if t == "global_statement" else "nonlocal")
                else:
                    walk(child)

        if scope.type in ("function_definition", "lambda"):
            params: list[str] = []
            _py_names(scope.child_by_field_name("parameters"), params)
            bind(params, "local")
            body = scope.child_by_field_name("body")
            if body is not None and body.type not in PY_SCOPES:
                if scope.type == "lambda" and body.type == "named_expression":
                    bind([text(body.child_by_field_name("name"))], "local")
                walk(body)
        else:  # a comprehension: its `for` targets
            walk(scope)
        result = {n: _merge(k) for n, k in kinds.items()}
        self._cache[scope.id] = result
        return result

    def bound(self, node: Node, name: str) -> str | None:
        child, parent = node, node.parent
        while parent is not None:
            if parent.type in PY_SCOPES:
                body = parent.child_by_field_name("body")
                inside = parent.type not in ("function_definition", "lambda") or (
                    body is not None and body.start_byte <= child.start_byte
                    and child.end_byte <= body.end_byte)
                if inside:
                    kind = self.bindings(parent).get(name)
                    if kind == "global":
                        return None
                    if kind and kind != "nonlocal":
                        return kind
            child, parent = parent, parent.parent
        return None


def _js_names(node: Node | None, out: list[str]) -> None:
    if node is None:
        return
    t = node.type
    if t in ("identifier", "shorthand_property_identifier_pattern"):
        out.append(text(node))
    elif t in ("assignment_pattern", "object_assignment_pattern"):
        _js_names(node.child_by_field_name("left"), out)
    elif t == "pair_pattern":
        _js_names(node.child_by_field_name("value"), out)
    elif t in ("required_parameter", "optional_parameter"):
        _js_names(node.child_by_field_name("pattern"), out)
    elif t in ("object_pattern", "array_pattern", "rest_pattern", "formal_parameters"):
        for child in node.named_children:
            _js_names(child, out)


class JsScopes:
    def __init__(self) -> None:
        self._cache: dict[int, dict[str, str]] = {}

    def bindings(self, scope: Node) -> dict[str, str]:
        found = self._cache.get(scope.id)
        if found is not None:
            return found
        kinds: dict[str, set[str]] = {}

        def bind(names: list[str], kind: str) -> None:
            for n in names:
                if n:
                    kinds.setdefault(n, set()).add(kind)

        def walk(node: Node) -> None:
            for child in node.named_children:
                t = child.type
                if t in ("function_declaration", "generator_function_declaration",
                         "class_declaration", "abstract_class_declaration"):
                    bind([text(child.child_by_field_name("name"))], "def")
                elif t in JS_SCOPES or t == "class":
                    continue
                elif t == "variable_declarator":
                    name = child.child_by_field_name("name")
                    value = child.child_by_field_name("value")
                    names: list[str] = []
                    _js_names(name, names)
                    is_def = (name is not None and name.type == "identifier"
                              and value is not None and value.type in JS_FUNCTION_VALUES)
                    bind(names, "def" if is_def else "local")
                    if value is not None and not is_def:
                        walk(child)
                elif t == "for_in_statement":
                    names = []
                    _js_names(child.child_by_field_name("left"), names)
                    bind(names, "local")
                    walk(child)
                else:
                    walk(child)

        names: list[str] = []
        if scope.type == "catch_clause":
            _js_names(scope.child_by_field_name("parameter"), names)
        else:
            _js_names(scope.child_by_field_name("parameters"), names)
            _js_names(scope.child_by_field_name("parameter"), names)
        bind(names, "local")
        body = scope.child_by_field_name("body")
        if body is not None and body.type not in JS_SCOPES:
            walk(body)
        result = {n: _merge(k) for n, k in kinds.items()}
        self._cache[scope.id] = result
        return result

    def bound(self, node: Node, name: str) -> str | None:
        parent = node.parent
        while parent is not None:
            if parent.type in JS_SCOPES:
                kind = self.bindings(parent).get(name)
                if kind:
                    return kind
            parent = parent.parent
        return None
