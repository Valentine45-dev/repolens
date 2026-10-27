"""Detectors against committed fixtures. Each fixture marks the lines it expects with
`# expect: <rule-id>`; a file without marks must produce no findings."""

import re
from pathlib import Path

import pytest

from app.detect.javascript import detect_javascript
from app.detect.python import detect_python
from app.detect.rules import RULES, looks_like_sql
from app.ingest.parse import parse_python
from app.ingest.parse_js import parse_js

FIXTURES = Path(__file__).parent / "fixtures" / "detectors"
EXPECT = re.compile(r"(?:#|//)\s*expect:\s*([\w-]+)")


def expected(source: str) -> list[tuple[int, str]]:
    return sorted(
        (i, m.group(1))
        for i, line in enumerate(source.splitlines(), start=1)
        for m in EXPECT.finditer(line)
    )


def run_python(name: str):
    source = (FIXTURES / name).read_text(encoding="utf-8")
    hits = detect_python(source, parse_python(name, source).imports)
    return sorted((h.line, h.rule_id) for h in hits), expected(source)


@pytest.mark.parametrize("name", ["py_positive.py", "py_negative.py"])
def test_python_fixtures(name):
    got, want = run_python(name)
    assert got == want


@pytest.mark.parametrize("name", ["js_positive.js", "ts_positive.ts", "js_negative.js"])
def test_javascript_fixtures(name):
    source = (FIXTURES / name).read_text(encoding="utf-8")
    hits = detect_javascript(name, source, parse_js(name, source).imports)
    assert sorted((h.line, h.rule_id) for h in hits) == expected(source)


def test_child_process_exec_needs_child_process():
    # An unrelated exec() (e.g. a regex or a DB driver) is not child_process.
    source = 'const re = /a/;\nre.exec(input);\ndb.exec(sql);\nexec(cmd);\n'
    assert detect_javascript("a.js", source, parse_js("a.js", source).imports) == []


def test_every_expected_rule_exists():
    for name in FIXTURES.iterdir():
        for _, rule_id in expected(name.read_text(encoding="utf-8")):
            assert rule_id in RULES, (name.name, rule_id)


@pytest.mark.parametrize(
    "text, sql",
    [
        ("SELECT * FROM t WHERE id=", True),
        ("insert into log (a) values (", True),
        ("UPDATE accounts SET x = ", True),
        ("delete from sessions where", True),
        ("Hello, select an item from the list", False),  # prose: not at the start, lower case
        ("  (SELECT id FROM t", True),
        ("rows = SELECT id FROM t", True),  # upper case anywhere
        ("Update the settings", False),
        ("selected from", False),
        ("SELECT", False),
    ],
)
def test_sql_shape(text, sql):
    assert looks_like_sql(text) is sql
