"""Chunking: units, line ranges, token windows. Uses the stub tokenizer (no model download);
one test runs against the real model only when RUN_MODEL_TESTS=1 and it is installed."""

import os

import pytest

from app.ingest.parse import parse_python
from app.ingest.parse_js import parse_js
from app.qa.chunks import OVERLAP_LINES, build_chunks, prefix, search_words
from app.qa.embed import StubEmbedder

STUB = StubEmbedder()

SOURCE = '''import os

LIMIT = 10


class Store:
    """A store."""
    retries = 3

    def get(self, key):
        return key

    def put(self, key, value):
        def _check(v):
            return v is not None
        return _check(value)


def main():
    return Store().get("a")


if __name__ == "__main__":
    main()
'''


def chunks_of(source: str, path: str = "pkg/store.py", max_tokens: int = 256):
    parsed = parse_python(path, source) if path.endswith(".py") else parse_js(path, source)
    return build_chunks(path, source, parsed.symbols, STUB.count_tokens, max_tokens)


def test_units_and_ranges():
    got = [(c.qualified_name, c.start_line, c.end_line, c.window) for c in chunks_of(SOURCE)]
    assert got == [
        ("pkg.store.Store", 6, 8, False),  # class header up to the first method
        ("pkg.store.Store.get", 10, 11, False),
        ("pkg.store.Store.put", 13, 16, False),  # nested _check stays inside put
        ("pkg.store.main", 19, 20, False),
        ("pkg.store", 1, 3, False),  # top-level code, blank edges trimmed
        ("pkg.store", 23, 24, False),
    ]


def test_text_matches_lines_and_prefix():
    lines = SOURCE.split("\n")
    for c in chunks_of(SOURCE):
        assert c.text == "\n".join(lines[c.start_line - 1:c.end_line])
        assert c.embed_text == prefix(c.path, c.qualified_name) + c.text
        assert c.embed_text.startswith("pkg/store.py ")


def test_long_function_splits_into_overlapping_windows_within_budget():
    body = "\n".join(
        f"    total = total + compute_value_{i}(alpha, beta, gamma)" for i in range(60)
    )
    source = f"def big(alpha, beta, gamma):\n    total = 0\n{body}\n    return total\n"
    chunks = chunks_of(source, "big.py", max_tokens=96)
    assert len(chunks) > 1 and all(c.window for c in chunks)
    assert {c.unit_start for c in chunks} == {1}  # one split unit, however many windows
    assert all(c.token_count <= 96 for c in chunks)
    assert all(STUB.count_tokens([c.embed_text])[0] == c.token_count for c in chunks)
    assert chunks[0].start_line == 1 and chunks[-1].end_line == 63  # nothing lost at the ends
    for a, b in zip(chunks, chunks[1:], strict=False):
        assert b.start_line == a.end_line - OVERLAP_LINES + 1  # overlapping, never a gap


def test_js_chunks():
    source = (
        'const x = require("x");\n\nfunction f(a) {\n  return a;\n}\n\n'
        "class C {\n  m() {}\n}\n"
    )
    got = [(c.qualified_name, c.start_line, c.end_line) for c in chunks_of(source, "s/a.js")]
    # The class's closing brace (line 9) belongs to the class, so it is not top-level code.
    assert got == [("s/a.js:f", 3, 5), ("s/a.js:C", 7, 7), ("s/a.js:C.m", 8, 8),
                   ("s/a.js", 1, 1)]


def test_leading_comments_belong_to_the_code_they_document():
    source = (
        "var x = require('x');\n"  # 1
        "\n"  # 2
        "/**\n"  # 3
        " * Send a response.\n"  # 4
        " */\n"  # 5
        "\n"  # 6  one blank line, Express style
        "function send(body) {\n"  # 7
        "  return body;\n"  # 8
        "}\n"  # 9
        "// counts things\n"  # 10
        "// twice\n"  # 11
        "function count(a) {\n"  # 12
        "  return a;\n"  # 13
        "}\n"  # 14
        "\n"  # 15
        "\n"  # 16
        "/* too far away */\n"  # 17
        "\n"  # 18
        "\n"  # 19
        "function far() {}\n"  # 20
        "class C {\n"  # 21
        "  /** a method doc */\n"  # 22
        "  m() {}\n"  # 23
        "}\n"  # 24
    )
    got = [(c.qualified_name, c.start_line, c.end_line) for c in chunks_of(source, "s/a.js")]
    assert ("s/a.js:send", 3, 9) in got  # JSDoc + blank line + function
    assert ("s/a.js:count", 10, 14) in got  # run of // lines, right after the previous code
    assert ("s/a.js:far", 20, 20) in got  # two blank lines: not attached
    assert ("s/a.js:C.m", 22, 23) in got  # method doc stays with the method
    assert ("s/a.js:C", 21, 21) in got  # so the class header ends before it
    module = [(s, e) for name, s, e in got if name == "s/a.js"]
    assert module == [(1, 1), (17, 17)]  # the doc comments are no longer top-level chunks
    lines = source.split("\n")
    for c in chunks_of(source, "s/a.js"):
        assert c.text == "\n".join(lines[c.start_line - 1:c.end_line])


def test_jsdoc_containing_slash_star_still_attaches():
    # express lib/request.js: the req.accepts JSDoc mentions "Accept: text/*".
    source = (
        "/**\n * // Accept: text/*, application/json\n * @public\n */\n\n"
        "req.accepts = function(){\n  return 1;\n};\n"
    )
    got = [(c.qualified_name, c.start_line, c.end_line) for c in chunks_of(source, "r.js")]
    assert got == [("r.js:req.accepts", 1, 8)]


def test_python_comment_attaches_and_docstring_stays_inside():
    source = (
        "import os\n"
        "\n"
        "# Builds the key.\n"
        "def key(a):\n"
        '    """Docstring."""\n'
        "    return a\n"
        "x = 1  # not a leading comment\n"
        "def other():\n"
        "    return 2\n"
    )
    got = [(c.qualified_name, c.start_line, c.end_line) for c in chunks_of(source, "k.py")]
    assert ("k.key", 3, 6) in got
    assert ("k.other", 8, 9) in got  # a trailing comment on code is not a leading comment
    assert ("k", 1, 1) in got and ("k", 7, 7) in got


def test_search_words_split_identifiers():
    (c,) = [c for c in chunks_of("def getUserById(user_id):\n    return user_id\n", "a.py")]
    words = search_words(c).split()
    assert {"get", "user", "by", "id", "getuserbyid", "user_id"} <= set(words)


@pytest.mark.skipif(os.environ.get("RUN_MODEL_TESTS") != "1", reason="set RUN_MODEL_TESTS=1")
def test_real_model_limit_and_windows():
    pytest.importorskip("sentence_transformers")
    from app import config
    from app.qa.embed import SentenceTransformerEmbedder

    model = SentenceTransformerEmbedder(config.EMBED_MODEL, config.EMBED_MODEL_REVISION)
    assert (model.max_tokens, model.dim) == (256, 384)
    body = "\n".join(f"    result.append(transform_record_{i}(record, options))" for i in range(80))
    source = f"def run(record, options):\n    result = []\n{body}\n    return result\n"
    parsed = parse_python("r.py", source)
    chunks = build_chunks("r.py", source, parsed.symbols, model.count_tokens, model.max_tokens)
    assert len(chunks) > 1
    # Checked with the tokenizer directly, special tokens ([CLS], [SEP]) included.
    assert all(len(model.tokenizer(c.embed_text)["input_ids"]) <= 256 for c in chunks)


def test_a_failed_model_load_is_remembered(monkeypatch):
    from app import config
    from app.qa import embed

    loads = []

    class Broken:
        def __init__(self, *args):
            loads.append(args)
            raise OSError("model files missing")

    monkeypatch.setattr(config, "EMBEDDER", "sentence-transformers")
    monkeypatch.setattr(embed, "SentenceTransformerEmbedder", Broken)
    monkeypatch.setattr(embed, "_load_error", None)
    embed.get_embedder.cache_clear()
    try:
        with pytest.raises(OSError):
            embed.get_embedder()
        with pytest.raises(embed.EmbedderUnavailable, match="OSError"):
            embed.get_embedder()
        assert len(loads) == 1  # the second call did not try to load the model again
    finally:
        embed.get_embedder.cache_clear()
