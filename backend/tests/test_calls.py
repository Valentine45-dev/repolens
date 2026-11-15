from pathlib import Path

from app.ingest.calls import parent, resolve_calls
from app.ingest.discover import discover
from app.ingest.parse import parse_python
from app.ingest.parse_js import parse_js
from app.ingest.pipeline import parse_file
from app.ingest.resolve import JsModules, PythonModules, resolve_js, resolve_python

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def edges_for(sources: dict[str, str], tsconfig: str | None = None):
    """Parse in-memory files and resolve their calls; returns {(src qname, dst qname): conf}."""
    parsed = {
        p: parse_python(p, s) if p.endswith(".py") else parse_js(p, s) for p, s in sources.items()
    }
    py = PythonModules([p for p in sources if p.endswith(".py")])
    js = JsModules([p for p in sources if not p.endswith(".py")], tsconfig)

    def resolve(path, imp):
        return resolve_python(path, imp, py) if path.endswith(".py") else resolve_js(path, imp, js)

    return {(e.src[1], e.dst[1]): e.confidence for e in resolve_calls(parsed, resolve)}


def test_parent():
    assert parent("m.User.save") == "m.User"
    assert parent("web/a.ts:App.render") == "web/a.ts:App"
    assert parent("web/a.ts:main") is None


def test_fixture_repo_call_edges():
    found = discover(FIXTURE, 100, 1_000_000).files
    code = {f.path: f for f in found if f.language}
    parsed = {p: parse_file(p, f.language, f.content) for p, f in code.items()}
    tsconfig = next(f.content for f in found if f.path == "tsconfig.json")
    py = PythonModules([p for p, f in code.items() if f.language == "python"])
    js = JsModules([p for p, f in code.items() if f.language != "python"], tsconfig)

    def resolve(path, imp):
        if code[path].language == "python":
            return resolve_python(path, imp, py)
        return resolve_js(path, imp, js)

    got = sorted((e.src[1], e.dst[1], e.confidence) for e in resolve_calls(parsed, resolve))
    assert got == sorted([
        ("sample_app.service.create_user", "sample_app.models.User", 1.0),  # imported class
        ("sample_app.service.fetch_user", "sample_app.service.fetch_user._key", 1.0),  # nested
        ("sample_app.service.main", "sample_app.service.create_user", 1.0),
        ("web/src/app.ts:App.render", "web/src/lib/index.ts:formatName", 1.0),  # fmt alias
        ("web/src/app.ts:App.render", "web/src/lib/math.ts:add", 1.0),  # math.add, * as math
        ("web/src/app.ts:App.render", "web/src/lib/math.ts:double", 1.0),
        ("web/src/app.ts:main", "web/src/app.ts:App", 1.0),  # new App()
        ("web/src/app.ts:main", "web/src/app.ts:App.render", 0.5),  # app.render(), unique name
        ("web/src/legacy.cjs:legacy", "web/src/util.js:trim", 1.0),  # util = require('./util')
        ("web/src/lib/index.ts:Cache.getOr", "web/src/lib/index.ts:Cache.get", 0.9),  # this.get
        ("web/src/lib/math.ts:double", "web/src/lib/math.ts:add", 1.0),
        ("web/src/server.js:app.handle", "web/src/server.js:res.send", 1.0),  # res.send here
        ("web/src/server.js:module.exports.start", "web/src/server.js:app.listen", 1.0),
        ("web/src/view.tsx:View", "web/src/lib/index.ts:formatName", 1.0),  # via tsconfig alias
        ("tests.check_service.check_create_user", "sample_app.service.create_user", 1.0),
        ("web/src/lib/math.spec.ts:checkAdd", "web/src/lib/math.ts:add", 1.0),
    ])


def test_ambiguous_names_get_no_edge():
    edges = edges_for({
        "a.py": "class A:\n    def save(self): pass\n",
        "b.py": "class B:\n    def save(self): pass\n",
        "c.py": "def run(x):\n    x.save()\n    helper()\n",
        "d.py": "def helper(): pass\n",
        "e.py": "def helper(): pass\n",
    })
    assert edges == {}


def test_self_method_imported_class_and_unique_fallback():
    edges = edges_for({
        "pkg/__init__.py": "from .models import User\n",
        "pkg/models.py": (
            "class User:\n"
            "    @classmethod\n"
            "    def create(cls): return cls.build()\n"
            "    @classmethod\n"
            "    def build(cls): pass\n"
            "    def save(self): self.validate()\n"
            "    def validate(self): pass\n"
        ),
        "app.py": (
            "from pkg import User\n"  # via the package __init__ re-export
            "def main(u):\n"
            "    User.create()\n"
            "    u.validate()\n"
        ),
    })
    assert edges == {
        ("pkg.models.User.create", "pkg.models.User.build"): 0.9,  # cls.build()
        ("pkg.models.User.save", "pkg.models.User.validate"): 0.9,  # self.validate()
        ("app.main", "pkg.models.User.create"): 1.0,  # imported class, one re-export hop
        ("app.main", "pkg.models.User.validate"): 0.5,  # u.validate(): unique method name
    }


def test_external_and_builtin_calls_get_no_edge():
    edges = edges_for({
        "m.py": "import os\nfrom json import dumps\ndef f():\n    os.getcwd()\n    dumps(1)\n",
        "n.py": "def getcwd(): pass\ndef dumps(): pass\n",
    })
    assert edges == {}


def test_plain_call_never_matches_a_method_and_member_call_never_a_function():
    edges = edges_for({
        "a.js": "function trim(s) { return s.trim(); }\n",
        "b.js": "class C { run() { go(); } }\n",
        "c.js": "const o = { go() {} };\n",
    })
    assert edges == {}


def test_recursion_is_dropped_and_languages_do_not_mix():
    edges = edges_for({
        "a.py": "def walk(n):\n    walk(n - 1)\n    render()\n",
        "b.js": "function render() {}\n",
    })
    assert edges == {}


def test_commonjs_module_members():
    edges = edges_for({
        "lib/util.js": "exports.trim = (s) => s;\nmodule.exports.pad = function (s) {};\n",
        "lib/app.js": (
            "const util = require('./util');\n"
            "const app = {};\n"
            "app.init = function () { this.set(); util.trim(); util.pad(); };\n"
            "app.set = function () {};\n"
        ),
    })
    assert edges == {
        ("lib/app.js:app.init", "lib/app.js:app.set"): 0.9,  # this.set() on the same object
        ("lib/app.js:app.init", "lib/util.js:exports.trim"): 1.0,
        ("lib/app.js:app.init", "lib/util.js:module.exports.pad"): 1.0,
    }


# --- C-03: confidence 1.0 only for what the call site can see ---


def test_parameter_or_local_with_a_functions_name_is_a_guess():
    py = edges_for({"m.py": "def callback(): pass\ndef register(callback):\n    callback()\n"
                            "def plain():\n    callback()\n"})
    assert py[("m.register", "m.callback")] == 0.5
    assert py[("m.plain", "m.callback")] == 1.0  # control: no parameter in the way
    js = edges_for({"a.js": "function next() {}\nfunction handler(req, res, next) { next(); }\n"
                            "function other() { const done = 1; next(); }\n"})
    assert js[("a.js:handler", "a.js:next")] == 0.5
    assert js[("a.js:other", "a.js:next")] == 1.0


def test_nested_function_is_only_visible_inside_its_enclosing_function():
    py = edges_for({"m.py": "def a():\n    def helper(): pass\n    helper()\n"
                            "def b():\n    helper()\n"})
    assert py == {("m.a", "m.a.helper"): 1.0}
    js = edges_for({"a.js": "function a() { function helper() {} helper(); }\n"
                            "function b() { helper(); }\n"})
    assert js == {("a.js:a", "a.js:a.helper"): 1.0}


def test_nearest_definition_wins_over_a_top_level_one_and_reaches_closures():
    src = ("def gen(): pass\n"
           "def a():\n    def gen(): pass\n    def inner():\n        gen()\n    gen()\n"
           "def b():\n    def gen(): pass\n    gen()\n")
    edges = edges_for({"m.py": src})
    assert edges[("m.a", "m.a.gen")] == 1.0
    assert edges[("m.a.inner", "m.a.gen")] == 1.0
    assert edges[("m.b", "m.b.gen")] == 1.0
    assert ("m.a", "m.gen") not in edges


def test_js_declaration_inside_an_anonymous_callback_is_still_found():
    src = ("describe('x', () => {\n  function expectIt(v) {}\n  it('y', () => { expectIt(1); });\n"
           "});\n")
    assert edges_for({"a.test.js": src}) == {("a.test.js", "a.test.js:expectIt"): 1.0}


def test_local_holding_a_factorys_nested_function_is_a_guess():
    src = ("def make():\n    def check(i): pass\n    return check\n"
           "def use():\n    check = make()\n    check(1)\n")
    edges = edges_for({"m.py": src})
    assert edges[("m.use", "m.make.check")] == 0.5


def test_import_inside_the_function_wins_over_a_same_file_definition():
    edges = edges_for({"m.py": "def helper(): pass\ndef f():\n    from other import helper\n"
                               "    helper()\n",
                       "other.py": "def helper(): pass\n"})
    assert edges[("m.f", "other.helper")] == 1.0
    assert ("m.f", "m.helper") not in edges


def test_imported_class_method_is_not_the_modules_same_named_function():
    py = edges_for({"models.py": "def create(): pass\nclass User:\n    def create(self): pass\n",
                    "views.py": "from models import User\nimport models\n"
                                "def signup():\n    User.create()\n    models.create()\n"})
    assert py[("views.signup", "models.User.create")] == 1.0
    assert py[("views.signup", "models.create")] == 1.0  # module receiver: the function
    js = edges_for({"models.js": "export function create() {}\n"
                                 "export class User { static create() {} }\n",
                    "views.js": "import { User } from './models';\n"
                                "function signup() { User.create(); }\n"})
    assert js == {("views.js:signup", "models.js:User.create"): 1.0}


# --- C-04: guesses never stand in for builtins or external packages ---


def test_builtin_and_js_global_names_are_not_guessed():
    py = edges_for({"store.py": "def open(p): pass\ndef read(): return open('x')\n",
                    "other.py": "def load(p):\n    return open(p)\n"})
    assert py == {("store.read", "store.open"): 1.0}  # its own file's open: still found
    js = edges_for({"util.js": "function fetch() {}\nfunction setTimeout() {}\n",
                    "app.js": "function go() { fetch('/x'); setTimeout(go, 1); }\n"})
    assert js == {}


def test_receiver_bound_to_an_external_package_or_a_builtin_type_is_not_guessed():
    edges = edges_for({"store.py": "class Store:\n    def join(self, x): pass\n"
                                   "    def fromkeys(self, x): pass\n",
                       "other.py": "import os\ndef read(p):\n    return os.path.join('a', p)\n"
                                   "def keys():\n    return dict.fromkeys([1])\n"
                                   "def mine(s):\n    return s.join(1)\n"})
    assert edges == {("other.mine", "store.Store.join"): 0.5}  # control: a plain receiver
