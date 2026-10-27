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
