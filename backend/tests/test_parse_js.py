from pathlib import Path

from app.ingest.parse_js import parse_js

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def parse_fixture(rel: str):
    return parse_js(rel, (FIXTURE / rel).read_text(encoding="utf-8"))


def symbols(parsed):
    return {s.qualified_name: s for s in parsed.symbols}


def imports(parsed):
    return [(i.specifier, i.names, i.line) for i in parsed.imports]


def calls(parsed):
    return {(c.caller, c.name, c.receiver) for c in parsed.calls}


def test_ts_symbols_and_signatures():
    p = parse_fixture("web/src/app.ts")
    syms = symbols(p)
    mod = syms["web/src/app.ts"]
    assert (mod.kind, mod.name, mod.start_line, mod.end_line) == ("module", "app", 1, 20)
    app = syms["web/src/app.ts:App"]
    assert (app.kind, app.start_line, app.end_line) == ("class", 8, 12)
    assert app.signature == "class App extends Cache<string>"
    render = syms["web/src/app.ts:App.render"]
    assert render.kind == "method"
    assert render.signature == "render(name: string): string"
    assert syms["web/src/app.ts:loadView"].kind == "function"
    main = syms["web/src/app.ts:main"]
    assert (main.kind, main.start_line, main.end_line) == ("function", 16, 20)
    assert main.signature == "function main(): void"


def test_ts_imports_including_dynamic_and_side_effect():
    assert imports(parse_fixture("web/src/app.ts")) == [
        ("node:fs", (("default", "fs"),), 1),
        ("react", (("default", "React"),), 2),
        ("./lib", (("Cache", "Cache"), ("formatName", "fmt")), 3),
        ("./lib/math.js", (("double", "double"),), 4),
        ("@lib/math", (("*", "math"),), 5),
        ("./missing", (), 6),
        ("./view", (), 14),
    ]


def test_ts_calls_with_caller_and_receiver():
    c = calls(parse_fixture("web/src/app.ts"))
    assert ("web/src/app.ts:App.render", "fmt", None) in c
    assert ("web/src/app.ts:App.render", "add", "math") in c
    assert ("web/src/app.ts:App.render", "double", None) in c
    assert ("web/src/app.ts:main", "App", None) in c  # new App()
    assert ("web/src/app.ts:main", "writeFileSync", "fs") in c
    assert ("web/src/app.ts:main", "render", "app") in c
    # import() and require() are imports, not calls.
    assert not any(name in ("import", "require") for _, name, _ in c)


def test_this_call_and_export_from():
    p = parse_fixture("web/src/lib/index.ts")
    assert imports(p) == [("./math", (("add", "add"),), 1)]
    syms = symbols(p)
    assert syms["web/src/lib/index.ts:formatName"].kind == "function"
    assert syms["web/src/lib/index.ts:Cache"].kind == "class"
    assert syms["web/src/lib/index.ts:Cache.getOr"].kind == "method"
    assert ("web/src/lib/index.ts:Cache.getOr", "get", "this") in calls(p)


def test_top_level_arrow_function():
    syms = symbols(parse_fixture("web/src/lib/math.ts"))
    add = syms["web/src/lib/math.ts:add"]
    assert (add.kind, add.start_line, add.end_line) == ("function", 1, 1)
    assert add.signature == "const add = (a: number, b: number): number =>"
    assert syms["web/src/lib/math.ts:double"].kind == "function"


def test_tsx_parses_with_jsx():
    p = parse_fixture("web/src/view.tsx")
    assert imports(p) == [("@lib/index", (("formatName", "formatName"),), 1)]
    assert symbols(p)["web/src/view.tsx:View"].kind == "function"
    assert ("web/src/view.tsx:View", "formatName", None) in calls(p)


def test_commonjs_require():
    p = parse_fixture("web/src/legacy.cjs")
    assert imports(p) == [
        ("./util", (("*", "util"),), 1),
        ("path", (("join", "join"), ("basename", "base")), 2),
    ]
    assert ("web/src/legacy.cjs:legacy", "trim", "util") in calls(p)
    syms = symbols(parse_fixture("web/src/util.js"))
    assert syms["web/src/util.js:trim"].kind == "function"


def test_commonjs_member_assignments_are_functions():
    p = parse_fixture("web/src/server.js")
    syms = symbols(p)
    listen = syms["web/src/server.js:app.listen"]
    assert (listen.kind, listen.name, listen.start_line, listen.end_line) == (
        "function", "app.listen", 6, 9,
    )
    assert listen.signature == "app.listen = function listen(port)"
    assert syms["web/src/server.js:app.handle"].signature == "app.handle = (req) =>"
    assert syms["web/src/server.js:res.send"].kind == "function"
    assert syms["web/src/server.js:exports.version"].kind == "function"
    assert syms["web/src/server.js:module.exports.create"].signature == (
        "module.exports.create = function ()"
    )
    # Calls inside get the assigned function as caller.
    c = calls(p)
    assert ("web/src/server.js:app.listen", "createServer", "http") in c
    assert ("web/src/server.js:app.handle", "send", "res") in c


def test_module_exports_object_methods():
    syms = symbols(parse_fixture("web/src/server.js"))
    start = syms["web/src/server.js:module.exports.start"]
    assert (start.kind, start.start_line, start.end_line) == ("method", 27, 29)
    assert start.signature == "start(port)"
    assert syms["web/src/server.js:module.exports.stop"].signature == "stop: function ()"
    assert syms["web/src/server.js:module.exports.ping"].signature == "ping: () =>"
    # A shorthand property is a reference, not a definition.
    assert "web/src/server.js:module.exports.app" not in syms


def test_module_exports_named_function():
    syms = symbols(parse_fixture("web/src/legacy.cjs"))
    legacy = syms["web/src/legacy.cjs:legacy"]
    assert (legacy.kind, legacy.start_line, legacy.end_line) == ("function", 4, 6)
    assert legacy.signature == "module.exports = function legacy(p)"
    anon = symbols(parse_js("a.js", "module.exports = () => 1;\n"))
    assert anon["a.js:module.exports"].kind == "function"


def test_assignments_inside_functions_are_not_symbols():
    p = parse_js("m.js", "function setup(app) {\n  app.get = function () {};\n}\n"
                         "const api = { list() { return 1; } };\n")
    syms = symbols(p)
    assert "m.js:app.get" not in syms
    assert "m.js:setup" in syms
    assert syms["m.js:api.list"].kind == "method"


def test_js_edge_cases():
    source = (
        "export * from './a';\n"
        "export * as ns from './b';\n"
        "export { x as y } from './c';\n"
        "const lazy = require(name);\n"
        "const t = require(`./t`);\n"
        "function outer() { const inner = () => 1; return inner(); }\n"
    )
    p = parse_js("m.js", source)
    assert imports(p) == [
        ("./a", (("*", "*"),), 1),
        ("./b", (("*", "ns"),), 2),
        ("./c", (("x", "y"),), 3),
        ("./t", (("*", "t"),), 5),
    ]
    syms = symbols(p)
    # Only top-level arrow consts become symbols.
    assert "m.js:outer" in syms
    assert "m.js:outer.inner" not in syms
    assert ("m.js:outer", "inner", None) in calls(p)
