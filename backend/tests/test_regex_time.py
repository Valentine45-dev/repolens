"""Detector and reachability text checks run in bounded time and keep their results (review S-08
class: repository text must not be able to stall the API). The former regexes are kept here as
the reference the new code must agree with."""

import random
import re
import time

import pytest

from app.detect.rules import looks_like_sql
from app.reach.entries import _NODE_RUN, _strip_as_view, url_handler_names

# --- the former implementations, as references -------------------------------------------------
_OLD_STATEMENT = (
    r"select\s.+?\sfrom\s|insert\s+into\s|update\s+[\w.\"`\[\]]+\s+set\s|delete\s+from\s"
)
_OLD_SQL_AT_START = re.compile(rf"^[\s(]*(?:{_OLD_STATEMENT})", re.IGNORECASE | re.DOTALL)
_OLD_SQL_UPPER = re.compile(
    r"\bSELECT\s.+?\sFROM\s|\bINSERT\s+INTO\s|\bUPDATE\s+[\w.\"`\[\]]+\s+SET\s|\bDELETE\s+FROM\s",
    re.DOTALL,
)
_OLD_NODE_RUN = re.compile(
    r"\b(?:node|nodemon|ts-node|tsx|babel-node|bun|deno run)\s+(?:--?[\w-]+(?:=\S+)?\s+)*"
    r"(['\"]?)([\w./@-]+\.(?:[mc]?js|jsx|tsx?))\1")
_OLD_AS_VIEW = re.compile(r"\.as_view\s*\(.*\)\s*$", re.DOTALL)


def _old_looks_like_sql(text: str) -> bool:
    text += " "
    return bool(_OLD_SQL_AT_START.search(text) or _OLD_SQL_UPPER.search(text))


def _random_texts(pieces: list[str], n: int = 20000, seed: int = 7) -> list[str]:
    rng = random.Random(seed)
    return ["".join(rng.choice(pieces) for _ in range(rng.randint(0, 12))) for _ in range(n)]


def test_sql_check_agrees_with_the_former_regex():
    pieces = ["select ", "SELECT ", "from ", " FROM ", "x", " ", "\n", "(", "insert into ",
              "UPDATE t SET ", "delete from ", "Select", "fromage", "a.b ", "SET ", "\t"]
    assert [looks_like_sql(t) for t in _random_texts(pieces)] == \
        [_old_looks_like_sql(t) for t in _random_texts(pieces)]
    assert looks_like_sql("SELECT * FROM users WHERE id = ")
    assert not looks_like_sql("SELECT FROM")
    assert not looks_like_sql("select an item")


def test_node_script_pattern_agrees_with_the_former_regex():
    pieces = ["node ", "--a ", "-b ", "--c=1 ", "x.js", "'y.ts'", '"z.mjs"', " ", "tsx ", "a",
              "deno run ", "--inspect=0.0.0.0:9229 "]
    for text in _random_texts(pieces):
        assert [m.groups() for m in _NODE_RUN.finditer(text)] == \
            [m.groups() for m in _OLD_NODE_RUN.finditer(text)]


def test_as_view_strip_agrees_with_the_former_regex():
    pieces = [".as_view(", ")", " ", "x", "(", "\n", ".as_view (", "Home", "."]
    for text in _random_texts(pieces):
        assert _strip_as_view(text) == _OLD_AS_VIEW.sub("", text)


def test_url_handlers_still_found():
    text = ("urlpatterns = [\n    path('', views.index),\n"
            "    url(r'^about$', views.About.as_view(), name='about'),\n"
            "    path('api/', include('api.urls')),\n]\n")
    assert url_handler_names(text) == ["index", "About"]


# --- running time ------------------------------------------------------------------------------
SIZE = 100_000


def _rep(unit: str) -> str:
    return (unit * (SIZE // len(unit) + 1))[:SIZE]


@pytest.mark.parametrize("label, run", [
    ("SELECT SELECT", lambda: looks_like_sql(_rep("SELECT "))),
    ("select x x", lambda: looks_like_sql("select " + _rep("x "))),
    ("UPDATE UPDATE", lambda: looks_like_sql(_rep("UPDATE "))),
    ("node with 5000 flags", lambda: list(_NODE_RUN.finditer("node " + "--a " * 5000 + "!"))),
    ("node --a node --a", lambda: list(_NODE_RUN.finditer(_rep("node --a ")))),
    (".as_view( repeated", lambda: _strip_as_view(_rep("x.as_view("))),
    ("unclosed path( calls", lambda: url_handler_names(_rep("path ("))),
    ("unclosed path( with quotes", lambda: url_handler_names(_rep("path('a', \""))),
])
def test_text_checks_run_in_bounded_time(label, run):
    started = time.perf_counter()
    run()
    assert time.perf_counter() - started < 1.0, label
