"""The broken-internal-import rule on in-memory repos: real breaks are reported, the expected
misses (optional dependencies, type-only imports, generated or compiled modules, namespace
packages, bundler aliases, JSON modules) are not."""

import json

from app.detect.imports import broken_imports
from app.ingest.parse import parse_python
from app.ingest.parse_js import parse_js


def run(files: dict[str, str], tsconfig: dict | None = None) -> set[tuple[str, int, str]]:
    parsed = {}
    for path, source in files.items():
        language = "python" if path.endswith((".py", ".pyi")) else "javascript"
        parser = parse_python if language == "python" else parse_js
        parsed[path] = (language, parser(path, source).imports)
    found = broken_imports(parsed, json.dumps(tsconfig) if tsconfig else None)
    return {(b.path, b.line, b.target) for b in found}


# --- Python -------------------------------------------------------------------------------

PY_REPO = {
    "pkg/__init__.py": "",
    "pkg/core.py": "x = 1\n",
    "ns/sub/mod.py": "y = 2\n",  # a namespace package: no __init__.py anywhere
}


def test_python_real_breaks_are_found():
    files = {
        **PY_REPO,
        "pkg/a.py": "from .gone import thing\nfrom pkg.missing import other\nimport pkg.nothere\n",
    }
    assert run(files) == {
        ("pkg/a.py", 1, "pkg.gone"),
        ("pkg/a.py", 2, "pkg.missing"),
        ("pkg/a.py", 3, "pkg.nothere"),
    }


def test_python_working_imports_are_not_reported():
    files = {
        **PY_REPO,
        "pkg/a.py": (
            "from . import core\nfrom .core import x\nimport pkg.core\nimport os\n"
            "import requests\nimport ns.sub\nfrom ns.sub import mod\nimport ns.sub.mod\n"
        ),
    }
    assert run(files) == set()


def test_python_guarded_and_type_only_imports_are_skipped():
    files = {
        **PY_REPO,
        "pkg/a.py": (
            "from typing import TYPE_CHECKING\n"
            "try:\n    from .optional import fast\nexcept ImportError:\n    fast = None\n"
            "try:\n    from .other import slow\nexcept:\n    slow = None\n"
            "if TYPE_CHECKING:\n    from .stubs import Typed\n"
        ),
    }
    assert run(files) == set()


def test_python_unrelated_exception_does_not_guard():
    files = {**PY_REPO, "pkg/a.py": "try:\n    from .gone import x\nexcept KeyError:\n    x = 1\n"}
    assert run(files) == {("pkg/a.py", 3 - 1, "pkg.gone")}


def test_python_generated_and_compiled_modules_are_skipped():
    files = {
        **PY_REPO,
        "pkg/a.py": (
            "from ._version import version\nfrom . import _speedups\nfrom .api_pb2 import Msg\n"
            "from ._speedups import fast\nfrom .gone import x\n"
        ),
    }
    assert run(files) == {("pkg/a.py", 5, "pkg.gone")}


def test_python_stub_files_are_not_checked():
    assert run({**PY_REPO, "pkg/a.pyi": "from .gone import x\n"}) == set()


# --- JavaScript / TypeScript ----------------------------------------------------------------

JS_REPO = {
    "src/util.js": "module.exports = {};\n",
    "src/lib/index.ts": "export const a = 1;\n",
    "src/data.json": "{}",  # the JSON file itself is not a code file; only the paths matter here
}


def test_js_relative_breaks_are_found():
    files = {
        **JS_REPO,
        "src/app.js": "const a = require('./util');\nconst b = require('./missing');\n"
                      "import c from './lib';\nimport d from './lib/nothere';\n",
    }
    assert run(files) == {("src/app.js", 2, "src/missing"), ("src/app.js", 4, "src/lib/nothere")}


def test_js_json_node_and_assets_are_not_reported():
    files = {
        **JS_REPO,
        "src/app.js": "require('./data');\nrequire('./addon.node');\nrequire('./style.css');\n"
                      "require('./data.json');\n",
    }
    # the probe list is built from code files, so ./data would be missing without the JSON
    # allowance; the stand-in below declares the JSON file as a path the repo has
    parsed = {"src/app.js": ("javascript", parse_js("src/app.js", files["src/app.js"]).imports),
              "src/data.json": ("javascript", [])}
    assert {(b.path, b.line) for b in broken_imports(parsed)} == {("src/app.js", 2)}


def test_js_guarded_bundler_alias_and_generated_paths_are_skipped():
    files = {
        **JS_REPO,
        "src/app.js": (
            "try { require('./optional'); } catch (e) {}\n"
            "import a from '@/components/x';\nimport b from '~/y';\nimport c from 'lodash';\n"
            "import d from './generated/schema';\nimport e from '../../outside';\n"
        ),
    }
    assert run(files) == set()


def test_js_type_only_imports_are_skipped():
    files = {**JS_REPO, "src/app.ts": "import type { T } from './types';\n"}
    assert run(files) == set()


def test_js_simple_tsconfig_alias_misses_are_found_and_hits_are_not():
    tsconfig = {"compilerOptions": {"paths": {"@lib/*": ["./src/lib/*"]}}}
    files = {
        **JS_REPO,
        "src/app.ts": "import a from '@lib/index';\nimport b from '@lib/nope';\n",
    }
    assert run(files, tsconfig) == {("src/app.ts", 2, "src/lib/nope")}


def test_js_non_simple_alias_is_not_judged():
    tsconfig = {"compilerOptions": {"paths": {"@x/*": ["./a/*", "./b/*"]}}}
    assert run({**JS_REPO, "src/app.ts": "import a from '@x/foo';\n"}, tsconfig) == set()
