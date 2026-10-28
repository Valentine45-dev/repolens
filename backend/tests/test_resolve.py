from app.ingest.parse import ParsedImport
from app.ingest.resolve import PythonModules, Target, python_source_roots, resolve_python

PATHS = [
    "setup.py",
    "src/pkg/__init__.py",
    "src/pkg/core.py",
    "src/pkg/sub/__init__.py",
    "src/pkg/sub/util.py",
    "src/pkg/sub/util.pyi",
    "tests/test_core.py",
]
MODULES = PythonModules(PATHS)


def resolve(importer: str, spec: str, *names: tuple[str, str]) -> list[Target]:
    return resolve_python(importer, ParsedImport(spec, tuple(names), 1), MODULES)


def internal(path: str) -> Target:
    return Target("internal", path)


def test_source_roots_include_src_layout():
    assert python_source_roots(PATHS) == ["", "src"]
    assert python_source_roots(["backend/app/__init__.py", "backend/app/main.py"]) == [
        "", "backend",
    ]


def test_module_map_prefers_py_over_stub_and_registers_both_roots():
    assert MODULES.by_name["pkg.sub.util"] == "src/pkg/sub/util.py"
    assert MODULES.by_name["src.pkg.core"] == "src/pkg/core.py"
    assert MODULES.by_name["pkg"] == "src/pkg/__init__.py"


def test_plain_import():
    assert resolve("tests/test_core.py", "pkg.core", ("*", "pkg.core")) == [
        internal("src/pkg/core.py")
    ]
    assert resolve("setup.py", "os.path", ("*", "os.path")) == [Target("external", "os")]


def test_from_import_tries_submodule_first():
    assert resolve("tests/test_core.py", "pkg", ("core", "core"), ("helper", "helper")) == [
        internal("src/pkg/core.py"),
        internal("src/pkg/__init__.py"),
    ]
    assert resolve("setup.py", "setuptools", ("setup", "setup")) == [
        Target("external", "setuptools")
    ]


def test_relative_imports():
    assert resolve("src/pkg/core.py", ".sub.util", ("f", "f")) == [internal("src/pkg/sub/util.py")]
    assert resolve("src/pkg/sub/util.py", "..core", ("x", "x")) == [internal("src/pkg/core.py")]
    assert resolve("src/pkg/sub/util.py", "..", ("core", "core")) == [
        internal("src/pkg/core.py")
    ]
    # In a package __init__, '.' is the package itself.
    assert resolve("src/pkg/__init__.py", ".", ("core", "c")) == [internal("src/pkg/core.py")]


def test_missing_relative_and_internal_submodule_are_unresolved():
    assert resolve("src/pkg/core.py", ".gone", ("x", "x")) == [
        Target("unresolved", "src.pkg.gone")
    ]
    assert resolve("tests/test_core.py", "pkg.nothere", ("x", "x")) == [
        Target("unresolved", "pkg.nothere")
    ]
    # Going above the top of the repo.
    assert resolve("setup.py", "...x", ("y", "y")) == [Target("unresolved", "...x")]


def test_star_import():
    assert resolve("tests/test_core.py", "pkg.sub", ("*", "*")) == [
        internal("src/pkg/sub/__init__.py")
    ]


# --- JavaScript / TypeScript ---

from app.ingest.resolve import JsModules, package_name, read_tsconfig, resolve_js  # noqa: E402

JS_PATHS = [
    "src/app.ts",
    "src/lib/index.ts",
    "src/lib/math.ts",
    "src/legacy/util.js",
    "src/legacy/index.js",
    "src/view.tsx",
    "src/types.d.ts",
    "packages/ui/src/button.tsx",
]
TSCONFIG = """{
  // comments and trailing commas are allowed in tsconfig.json
  "compilerOptions": {
    "paths": {
      "@lib/*": ["src/lib/*"],
      "@ui/*": ["packages/ui/src/*"],
      "@multi/*": ["a/*", "b/*"],
      "@config": ["src/app.ts"], /* exact patterns are not supported */
    },
  },
}"""


def js(importer: str, spec: str, modules: JsModules) -> list[Target]:
    return resolve_js(importer, ParsedImport(spec, (), 1), modules)


def test_js_relative_extension_and_index_probing():
    m = JsModules(JS_PATHS)
    assert js("src/app.ts", "./lib", m) == [internal("src/lib/index.ts")]
    assert js("src/app.ts", "./lib/math", m) == [internal("src/lib/math.ts")]
    assert js("src/app.ts", "./lib/math.js", m) == [internal("src/lib/math.ts")]  # TS style
    assert js("src/app.ts", "./view.jsx", m) == [internal("src/view.tsx")]
    assert js("src/app.ts", "./types", m) == [internal("src/types.d.ts")]
    assert js("src/legacy/util.js", ".", m) == [internal("src/legacy/index.js")]
    assert js("src/lib/math.ts", "../legacy/util.js", m) == [internal("src/legacy/util.js")]


def test_js_require_of_repo_root_finds_root_index():
    # express: examples/auth/index.js does require('../..')
    m = JsModules(["index.js", "lib/express.js", "examples/auth/index.js"])
    assert js("examples/auth/index.js", "../..", m) == [internal("index.js")]
    assert js("lib/express.js", "..", m) == [internal("index.js")]
    assert js("lib/express.js", "..", JsModules(["lib/express.js"])) == [
        Target("unresolved", ".")
    ]


def test_js_missing_relative_and_outside_repo_are_unresolved():
    m = JsModules(JS_PATHS)
    assert js("src/app.ts", "./missing", m) == [Target("unresolved", "src/missing")]
    assert js("src/app.ts", "../../x", m) == [Target("unresolved", "../../x")]
    assert js("src/app.ts", "/abs/path", m) == [Target("unresolved", "/abs/path")]


def test_js_assets_are_skipped():
    m = JsModules(JS_PATHS)
    assert js("src/app.ts", "./styles.css", m) == []
    assert js("src/app.ts", "./logo.svg?url", m) == []
    assert js("src/app.ts", "../package.json", m) == []


def test_js_packages_are_external():
    m = JsModules(JS_PATHS)
    assert js("src/app.ts", "react", m) == [Target("external", "react")]
    assert js("src/app.ts", "lodash/fp", m) == [Target("external", "lodash")]
    assert js("src/app.ts", "@scope/pkg/sub/x", m) == [Target("external", "@scope/pkg")]
    assert js("src/app.ts", "node:fs", m) == [Target("external", "fs")]
    assert package_name("fs") == "fs"
    # Not a valid npm name and no alias: unresolved, not external.
    assert js("src/app.ts", "@/components/x", m) == [Target("unresolved", "@/components/x")]
    assert js("src/app.ts", "~/x", m) == [Target("unresolved", "~/x")]


def test_tsconfig_paths_without_base_url_resolve_from_tsconfig_dir():
    m = JsModules(JS_PATHS, TSCONFIG)
    assert m.base_url is None
    assert js("src/view.tsx", "@lib/math", m) == [internal("src/lib/math.ts")]
    assert js("src/view.tsx", "@lib/index", m) == [internal("src/lib/index.ts")]
    assert js("src/app.ts", "@ui/button", m) == [internal("packages/ui/src/button.tsx")]
    assert js("src/app.ts", "@lib/nothere", m) == [Target("unresolved", "@lib/nothere")]
    # Not simple (two targets, or no '*'): unresolved.
    assert js("src/app.ts", "@multi/x", m) == [Target("unresolved", "@multi/x")]
    assert js("src/app.ts", "@config", m) == [Target("unresolved", "@config")]
    # An exact pattern does not swallow longer names.
    assert js("src/app.ts", "@configs/x", m) == [Target("external", "@configs/x")]


def test_tsconfig_paths_with_base_url():
    tsconfig = '{"compilerOptions": {"baseUrl": "src", "paths": {"#/*": ["lib/*"]}}}'
    m = JsModules(JS_PATHS, tsconfig)
    assert m.base_url == "src"
    assert js("src/app.ts", "#/math", m) == [internal("src/lib/math.ts")]
    # baseUrl also makes bare names resolve inside it before falling back to packages.
    assert js("src/view.tsx", "lib/math", m) == [internal("src/lib/math.ts")]
    assert js("src/view.tsx", "react", m) == [Target("external", "react")]


def test_tsconfig_dot_slash_targets():
    # Without baseUrl, TypeScript wants targets relative to the tsconfig: "./src/lib/*".
    m = JsModules(JS_PATHS, '{"compilerOptions": {"paths": {"@lib/*": ["./src/lib/*"]}}}')
    assert m.base_url is None
    assert js("src/view.tsx", "@lib/math", m) == [internal("src/lib/math.ts")]
    # "@lib" alone does not match "@lib/*" and is not a valid npm name either.
    assert js("src/view.tsx", "@lib", m) == [Target("unresolved", "@lib")]
    # With baseUrl, "./" is relative to it.
    m = JsModules(
        JS_PATHS, '{"compilerOptions": {"baseUrl": "./src", "paths": {"#/*": ["./lib/*"]}}}'
    )
    assert js("src/app.ts", "#/math", m) == [internal("src/lib/math.ts")]


def test_bad_tsconfig_is_ignored():
    assert read_tsconfig("{ not json") == (None, [])
    assert read_tsconfig(None) == (None, [])
    assert read_tsconfig('{"compilerOptions": {"baseUrl": "."}}') == ("", [])
    # Wrong shapes used to raise outside the try and fail the edges stage.
    for source in ('{"compilerOptions": [1]}', '{"compilerOptions": "x"}', "[]", '"x"',
                   "[" * 5000 + "]" * 5000):
        assert read_tsconfig(source) == (None, []), source[:30]
