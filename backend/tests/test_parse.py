from pathlib import Path

from app.ingest.discover import discover
from app.ingest.parse import module_name, parse_python

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"


def parse_fixture(rel: str):
    source = (FIXTURE / rel).read_text(encoding="utf-8")
    return {s.qualified_name: s for s in parse_python(rel, source).symbols}


def test_module_name():
    assert module_name("pkg/sub/mod.py") == "pkg.sub.mod"
    assert module_name("pkg/__init__.py") == "pkg"
    assert module_name("setup.py") == "setup"


def test_classes_methods_and_decorators():
    syms = parse_fixture("sample_app/models.py")
    assert syms["sample_app.models"].kind == "module"
    assert syms["sample_app.models"].start_line == 1
    assert syms["sample_app.models.User"].kind == "class"
    assert syms["sample_app.models.User"].signature == "class User(Base)"
    # Decorated definitions start at the decorator line.
    assert syms["sample_app.models.User"].start_line == 9
    prop = syms["sample_app.models.User.display_name"]
    assert prop.kind == "method"
    assert (prop.start_line, prop.end_line) == (14, 16)
    assert prop.signature == "def display_name(self) -> str"
    assert syms["sample_app.models.User.Meta"].kind == "class"
    assert syms["sample_app.models.User.Meta.describe"].kind == "method"
    assert syms["sample_app.models.Base.save"].kind == "method"


def test_functions_async_nested_and_conditional():
    syms = parse_fixture("sample_app/service.py")
    assert syms["sample_app.service.create_user"].kind == "function"
    assert syms["sample_app.service.create_user"].signature == (
        "def create_user(name: str, email: str) -> User"
    )
    assert syms["sample_app.service.fetch_user"].signature == "async def fetch_user(user_id: int)"
    assert syms["sample_app.service.fetch_user._key"].kind == "function"
    # Definitions inside `if __name__ == "__main__":` are still found.
    assert "sample_app.service.main" in syms


def test_package_init_is_module_symbol():
    syms = parse_fixture("sample_app/__init__.py")
    assert list(syms) == ["sample_app"]


def test_syntax_error_does_not_stop_parsing():
    syms = parse_fixture("sample_app/broken.py")
    assert "sample_app.broken.ok" in syms
    assert "sample_app.broken.StillFound.method" in syms


def test_python_imports():
    source = (
        "import os, os.path as osp\n"
        "import a.b\n"
        "from . import models as m\n"
        "from ..pkg.mod import x, y as z\n"
        "from lib import *\n"
        "def f():\n"
        "    import json\n"
    )
    imports = [(i.specifier, i.names, i.line) for i in parse_python("p/q.py", source).imports]
    assert imports == [
        ("os", (("*", "os"),), 1),
        ("os.path", (("*", "osp"),), 1),
        ("a.b", (("*", "a.b"),), 2),
        (".", (("models", "m"),), 3),
        ("..pkg.mod", (("x", "x"), ("y", "z")), 4),
        ("lib", (("*", "*"),), 5),
        ("json", (("*", "json"),), 7),
    ]


def test_python_calls_have_caller_and_receiver():
    source = (FIXTURE / "sample_app/service.py").read_text(encoding="utf-8")
    calls = {(c.caller, c.name, c.receiver) for c in parse_python("sample_app/service.py",
                                                                   source).calls}
    assert ("sample_app.service", "getLogger", "logging") in calls
    assert ("sample_app.service.create_user", "User", None) in calls
    assert ("sample_app.service.create_user", "save", "user") in calls
    assert ("sample_app.service.fetch_user", "_key", None) in calls
    assert ("sample_app.service.fetch_user", "info", "log") in calls
    assert ("sample_app.service.main", "create_user", None) in calls


def test_python_receiver_is_empty_for_non_names():
    calls = parse_python("m.py", "get().run()\nself.a.b()\nx[0].y()\n").calls
    assert [(c.name, c.receiver) for c in calls] == [
        ("run", ""), ("get", None), ("b", "self.a"), ("y", ""),
    ]


def test_fixture_repo_discovers_and_reports_secret():
    result = discover(FIXTURE, max_files=100, max_file_bytes=1_000_000)
    by_path = {f.path: f for f in result.files}
    assert sorted(by_path) == [
        "sample_app/__init__.py",
        "sample_app/broken.py",
        "sample_app/models.py",
        "sample_app/service.py",
        "sample_app/settings.py",
        "tsconfig.json",
        "web/src/app.ts",
        "web/src/legacy.cjs",
        "web/src/lib/index.ts",
        "web/src/lib/math.ts",
        "web/src/server.js",
        "web/src/util.js",
        "web/src/view.tsx",
    ]
    settings = by_path["sample_app/settings.py"]
    assert "fixture-not-a-real-password" not in settings.content
    assert [(s.line, s.kind) for s in settings.secrets] == [(5, "secret-assignment")]
