"""Citation validation. The model's citations are claims; only the ones that point inside a
snippet we actually sent survive. Everything else is removed from the text and counted.

Accepted forms: `path:N`, `path:N-M`, with a hyphen, en dash or em dash, an optional `L`
before the numbers, and GitHub's `path#L12` / `path#L12-L14`; optionally in backticks. A range
is valid only when it lies inside one sent snippet: the same file is not enough, and neither is
a range spanning two snippets.

Matching (review of 14 Nov, A-02..A-04):
1. The paths that were sent are matched first, longest first, exactly as sent (so `app/[id]/x.tsx`,
   `app/(shop)/y.ts` and `src/my file.py` work), also with backslashes for slashes; a sent path
   inside a longer name (`xsrc/app.py`, `lib/src/app.py`) is not that path.
2. Everything else shaped like `name.ext:N` is a citation attempt, checked and counted, whatever
   the extension (`lib/router.go:10` is dropped, not left as text), unless it looks like a host or
   a version: no slash and a host suffix (`db.internal:5432`, `api.example.com:443`), digits and
   dots only (`127.0.0.1:8000`, `2.1:3`), or a `//host` after a URL scheme.
3. Line numbers have at most 7 digits and are not followed by another digit, so a huge digit run is
   plain text, never an error.
A valid citation written as `#L` or with backslashes is shown as `path:N-M`; the others stay as
written.
"""

import re
from dataclasses import dataclass

from app.qa.retrieve import Snippet

_NUM = r"\d{1,7}(?!\d)"
_LINES = rf"(?::L?(?P<start>{_NUM})(?:\s*[-–—]\s*L?(?P<end>{_NUM}))?" \
         rf"|#L(?P<astart>{_NUM})(?:-L?(?P<aend>{_NUM}))?)"
# A path is word characters, dots, slashes, @, + and -, ending in a file extension.
CITATION = re.compile(rf"(?P<tick>`?)(?P<path>(?:\./)?[\w@+\-./]*\w\.\w+){_LINES}(?P=tick)")
# Not preceded by a character that could continue a path, so a sent path is never the tail of
# a longer one.
_NOT_AFTER_PATH = r"(?<![\w@+\-./\\])"


@dataclass(frozen=True)
class Citation:
    path: str
    start_line: int
    end_line: int
    file_id: int
    symbol_id: int | None  # None for documentation
    in_test: bool  # the Explorer hides test files unless asked, so the chip says so
    source: str = "code"  # "doc": the chip says documentation and opens the doc panel


@dataclass
class Validated:
    text: str
    citations: list[Citation]
    dropped: int


def _lines(m: re.Match) -> tuple[int, int]:
    start = int(m["start"] or m["astart"])
    return start, int(m["end"] or m["aend"] or start)


def find_citations(text: str) -> list[tuple[str, int, int]]:
    """The generic citation shapes in a text (no host filtering, no sent paths)."""
    return [(m["path"].removeprefix("./"), *_lines(m)) for m in CITATION.finditer(text)]


# `name.suffix:port` with no slash and one of these suffixes is a host, not a file. File
# extensions that are also country domains (.py, .md, .rs, .sh, ...) are deliberately not here.
HOST_SUFFIXES = {
    "com", "org", "net", "io", "ai", "app", "dev", "co", "edu", "gov", "mil", "int", "info", "biz",
    "cloud", "local", "localhost", "internal", "lan", "home", "corp", "test", "example", "invalid",
    "uk", "de", "fr", "jp", "cn", "ru", "in", "us", "eu", "ca", "au", "nl",
}


def _is_attempt(path: str) -> bool:
    """A generic `name.ext:N` match that the model meant as a source (A-02)."""
    if path.startswith("//"):
        return False  # https://host:port
    if re.fullmatch(r"[\d.]+", path):
        return False  # an IP address or a version
    suffix = path.rsplit(".", 1)[1].lower()
    if suffix.isdigit():
        return False
    return "/" in path or suffix not in HOST_SUFFIXES


def _sent_pattern(paths: set[str]) -> re.Pattern | None:
    if not paths:
        return None
    alts = "|".join(re.escape(p).replace("/", r"[/\\]")
                    for p in sorted(paths, key=lambda p: (-len(p), p)))
    return re.compile(rf"(?P<tick>`?){_NOT_AFTER_PATH}(?P<path>(?:\./)?(?:{alts})){_LINES}"
                      rf"(?P=tick)")


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
    # The space before an emptied bracket goes too, or "response (x)." becomes "response .".
    text = re.sub(r"[ \t]*[(\[][ \t]*\x00(?:[ \t]*[,;]?[ \t]*\x00)*[ \t]*[)\]]", "", text)
    text = re.sub(r"\x00[ \t]*[,;][ \t]*", _GONE, text)
    text = re.sub(r"[ \t]*[,;][ \t]*\x00", _GONE, text)
    return text.replace(_GONE, "").strip()


_KEPT = "\x01"  # wraps the index of a citation already checked, so the generic pass skips it


def validate(text: str, snippets: list[Snippet]) -> Validated:
    citations: dict[tuple[str, int, int], Citation] = {}  # ordered by first use
    dropped = 0
    kept: list[str] = []  # final text of each checked citation, by index

    def check(m: re.Match) -> str:
        nonlocal dropped
        path = m["path"].removeprefix("./").replace("\\", "/")
        start, end = _lines(m)
        snippet = _inside(snippets, path, start, end)
        if snippet is None:
            dropped += 1
            return _GONE
        citations.setdefault(
            (path, start, end),
            Citation(path, start, end, snippet.file_id, snippet.symbol_id, snippet.in_test,
                     snippet.source),
        )
        shown = m[0]
        if m["astart"] or "\\" in m["path"]:  # shown in the usual form
            shown = f"{m['tick']}{path}:{start}{f'-{end}' if end != start else ''}{m['tick']}"
        kept.append(shown)
        return f"{_KEPT}{len(kept) - 1}{_KEPT}"

    def generic(m: re.Match) -> str:
        if not _is_attempt(m["path"].removeprefix("./")):
            return m[0]  # `db.internal:5432`, `127.0.0.1:8000`: not a citation, left as written
        return check(m)

    sent = _sent_pattern({s.path for s in snippets})
    marked = sent.sub(check, text) if sent else text
    marked = CITATION.sub(generic, marked)
    if dropped:
        marked = _tidy(marked)
    final = re.sub(rf"{_KEPT}(\d+){_KEPT}", lambda m: kept[int(m[1])], marked)
    return Validated(final, list(citations.values()), dropped)
