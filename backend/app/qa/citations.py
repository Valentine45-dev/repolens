"""Citation validation. The model's citations are claims; only the ones that point inside a
snippet we actually sent survive. Everything else is removed from the text and counted.

Accepted forms: `path:N`, `path:N-M`, with a hyphen, en dash or em dash, an optional `L`
before the numbers, optionally in backticks. A range is valid only when it lies inside one
sent snippet: the same file is not enough, and neither is a range spanning two snippets.
"""

import re
from dataclasses import dataclass

from app.qa.retrieve import Snippet

# A path is word characters, dots, slashes, @, + and -, ending in a file extension.
CITATION = re.compile(
    r"(?P<tick>`?)(?P<path>(?:\./)?[\w@+\-./]*\w\.\w+)"
    r":L?(?P<start>\d+)(?:\s*[-–—]\s*L?(?P<end>\d+))?(?P=tick)"
)


@dataclass(frozen=True)
class Citation:
    path: str
    start_line: int
    end_line: int
    file_id: int
    symbol_id: int


@dataclass
class Validated:
    text: str
    citations: list[Citation]
    dropped: int


def find_citations(text: str) -> list[tuple[str, int, int]]:
    out = []
    for m in CITATION.finditer(text):
        start = int(m["start"])
        out.append((m["path"].removeprefix("./"), start, int(m["end"] or start)))
    return out


def _inside(snippets: list[Snippet], path: str, start: int, end: int) -> Snippet | None:
    if start < 1 or end < start:
        return None
    for s in snippets:
        if s.path == path and s.start_line <= start and end <= s.end_line:
            return s
    return None


_GONE = "\x00"  # marks a removed citation until the text around it is tidied


def _tidy(text: str) -> str:
    """Clean up only around removed citations (code elsewhere keeps its spacing): the space
    before it, a separator next to it, and brackets left empty."""
    text = re.sub(r"[ \t]*\x00", _GONE, text)
    text = re.sub(r"[(\[][ \t]*\x00(?:[ \t]*[,;]?[ \t]*\x00)*[ \t]*[)\]]", "", text)
    text = re.sub(r"\x00[ \t]*[,;][ \t]*", _GONE, text)
    text = re.sub(r"[ \t]*[,;][ \t]*\x00", _GONE, text)
    return text.replace(_GONE, "").strip()


def validate(text: str, snippets: list[Snippet]) -> Validated:
    citations: dict[tuple[str, int, int], Citation] = {}  # ordered by first use
    dropped = 0

    def check(m: re.Match) -> str:
        nonlocal dropped
        path = m["path"].removeprefix("./")
        start = int(m["start"])
        end = int(m["end"] or start)
        snippet = _inside(snippets, path, start, end)
        if snippet is None:
            dropped += 1
            return _GONE
        citations.setdefault(
            (path, start, end), Citation(path, start, end, snippet.file_id, snippet.symbol_id)
        )
        return m[0]

    cleaned = CITATION.sub(check, text)
    return Validated(_tidy(cleaned) if dropped else text, list(citations.values()), dropped)
