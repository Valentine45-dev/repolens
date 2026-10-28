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
    assert all(model.count_tokens([c.embed_text])[0] <= 256 for c in chunks)
