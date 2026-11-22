"""Documentation chunks (Step 5 Part A): README and docs text, cut at headings, for Ask.

Which stored files (app.ingest.discover keeps them already; nothing here changes what is stored):
- README* with any extension, any *.md or *.rst, and *.txt only under a `docs/` folder or named
  README*; never a code file (one with a language);
- not CHANGELOG*, CHANGES*, HISTORY*, LICENSE*, COPYING*, NOTICE* (any case), not under `.github/`,
  node_modules, vendor or a build-output folder (discover's skip list), not over MAX_DOC_BYTES
  (left out with a note, not an error).

Sections: a section runs from a heading to the next heading of any level (subsections are their
own chunks, so no text is repeated); text before the first heading is a section too. Markdown:
ATX headings (`#` .. `######`) and setext underlines (`===`, `---`), never inside a fenced code
block. reStructuredText: a title line underlined (optionally also overlined) with one repeated
punctuation character at least as long as the title; levels in order of first use, as RST
defines them. A `.txt` file is one section. A heading with nothing under it but the next heading
makes no chunk of its own (its title is in its subsections' names). Long sections are split into
the same 256-token windows as code (app.qa.chunks.unit_chunks). A chunk's name is its heading
trail ("Usage > Install"), which is embedded with the path, as a code chunk's symbol name is.

Fresh analyses (pipeline.search_first) and the backfill (app.ingest.docchunks) both call
build_doc_chunks on (path, redacted content) pairs, so they make the same chunks.
"""

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.ingest.discover import SKIP_DIRS
from app.ingest.redact import redact
from app.qa.chunks import Chunk, CountTokens, unit_chunks

MAX_DOC_BYTES = 200_000
EXCLUDED_NAMES = ("changelog", "changes", "history", "license", "copying", "notice")
EXCLUDED_DIRS = {d.lower() for d in SKIP_DIRS} | {"vendor", ".github"}
CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def is_searchable_doc(path: str) -> bool:
    """Whether a stored file is documentation that Ask may search (size checked separately)."""
    p = PurePosixPath(path)
    name, suffix = p.name.lower(), p.suffix.lower()
    if suffix in CODE_SUFFIXES:
        return False
    if any(part.lower() in EXCLUDED_DIRS for part in p.parts[:-1]):
        return False
    if name.startswith(EXCLUDED_NAMES):
        return False
    if name.startswith("readme") or suffix in (".md", ".rst"):
        return True
    return suffix == ".txt" and any(part.lower() == "docs" for part in p.parts[:-1])


@dataclass
class DocSelection:
    files: list[tuple[str, str]] = field(default_factory=list)  # (path, content) to chunk
    too_large: list[str] = field(default_factory=list)  # doc files over MAX_DOC_BYTES


def select_docs(files: list[tuple[str, str]]) -> DocSelection:
    """Doc files to chunk, in path order, from (path, content) pairs of stored files."""
    out = DocSelection()
    for path, content in sorted(files):
        if not is_searchable_doc(path):
            continue
        if len((content or "").encode("utf-8")) > MAX_DOC_BYTES:
            out.too_large.append(path)
        else:
            out.files.append((path, content or ""))
    return out


# --- headings ---------------------------------------------------------------------------------

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$")
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_RST_ADORN = re.compile(r"^([!-/:-@\[-`{-~])\1+[ \t]*$")  # one repeated punctuation character


@dataclass(frozen=True)
class Heading:
    start: int  # first line of the heading (1-based), overline or title
    end: int  # last line of the heading (underline, or the title for ATX)
    level: int
    title: str


def _markdown_headings(lines: list[str]) -> list[Heading]:
    out: list[Heading] = []
    fence: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _FENCE.match(line)
        if m:
            mark = m[1]
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence) and not line.strip()[len(mark):]:
                fence = None
            i += 1
            continue
        if fence is not None:
            i += 1
            continue
        a = _ATX.match(line)
        if a:
            title = re.sub(r"[ \t]+#+$", "", a[2] or "").strip()
            out.append(Heading(i + 1, i + 1, len(a[1]), title))
            i += 1
            continue
        if (line.strip() and i + 1 < len(lines) and _SETEXT.match(lines[i + 1])
                and not line.lstrip().startswith(("-", "*", "+", ">", "|"))
                and (i == 0 or not lines[i - 1].strip() or (out and out[-1].end == i))):
            level = 1 if lines[i + 1].strip()[0] == "=" else 2
            out.append(Heading(i + 1, i + 2, level, line.strip()))
            i += 2
            continue
        i += 1
    return out


def _rst_headings(lines: list[str]) -> list[Heading]:
    out: list[Heading] = []
    levels: list[tuple[str, bool]] = []  # (character, overlined) in order of first use
    i = 0
    while i < len(lines):
        title = lines[i]
        if (title.strip() and not title[0].isspace() and not _RST_ADORN.match(title)
                and i + 1 < len(lines) and _RST_ADORN.match(lines[i + 1])
                and len(lines[i + 1].rstrip()) >= len(title.rstrip())):
            char = lines[i + 1].strip()[0]
            over = (i > 0 and _RST_ADORN.match(lines[i - 1]) is not None
                    and lines[i - 1].strip()[0] == char
                    and len(lines[i - 1].rstrip()) == len(lines[i + 1].rstrip()))
            style = (char, over)
            if style not in levels:
                levels.append(style)
            start = i if over else i + 1  # 1-based: the overline is line i
            out.append(Heading(start, i + 2, levels.index(style) + 1, title.strip()))
            i += 2
            continue
        i += 1
    return out


def headings(path: str, text: str) -> list[Heading]:
    suffix = PurePosixPath(path).suffix.lower()
    lines = text.split("\n")
    if suffix == ".rst":
        return _rst_headings(lines)
    if suffix == ".md" or (PurePosixPath(path).name.lower().startswith("readme")
                           and suffix not in (".txt",)):
        return _markdown_headings(lines)
    return []  # .txt: one section


@dataclass(frozen=True)
class Section:
    start: int
    end: int
    trail: str  # "Title > Subtitle"; "" for text before the first heading or a heading-less file
    heading_end: int  # last heading line inside the section (start - 1 when there is none)


def sections(path: str, text: str) -> list[Section]:
    lines = text.split("\n")
    hs = headings(path, text)
    out: list[Section] = []
    first = hs[0].start if hs else len(lines) + 1
    if first > 1:
        out.append(Section(1, first - 1, "", 0))
    stack: list[Heading] = []
    for n, h in enumerate(hs):
        while stack and stack[-1].level >= h.level:
            stack.pop()
        stack.append(h)
        end = hs[n + 1].start - 1 if n + 1 < len(hs) else len(lines)
        out.append(Section(h.start, end, " > ".join(s.title for s in stack if s.title), h.end))
    return out


# --- secrets in configuration examples ---------------------------------------------------------
# Stored documentation is redacted like code: quoted values and known token formats only (README
# "Redaction is pattern-based"). Doc chunks are sent to the LLM, so configuration examples inside
# them also get the unquoted config-value rule that .ini/.yaml/.toml/.sh files get: Markdown fences
# tagged with one of these languages or untagged, and RST code blocks in one of them. Line count is
# unchanged, so ranges and citations stay right. The stored file text is not changed.
CONFIG_LANGS = {"", "ini", "cfg", "conf", "toml", "yaml", "yml", "env", "dotenv", "properties",
                "sh", "bash", "shell", "console", "zsh", "powershell", "ps1", "bat", "cmd", "text",
                "txt", "none", "docker", "dockerfile", "nginx", "apache", "systemd"}
_RST_CODE = re.compile(r"^(\s*)\.\.\s+(?:code-block|code|sourcecode)::\s*([\w+-]*)\s*$")


def _config_blocks(path: str, lines: list[str]) -> list[tuple[int, int]]:
    """0-based [start, end) line ranges of configuration examples."""
    out: list[tuple[int, int]] = []
    if PurePosixPath(path).suffix.lower() == ".rst":
        i = 0
        while i < len(lines):
            m = _RST_CODE.match(lines[i])
            if m and m[2].lower() in CONFIG_LANGS:
                indent, j = len(m[1]), i + 1
                while j < len(lines) and (not lines[j].strip()
                                          or len(lines[j]) - len(lines[j].lstrip()) > indent):
                    j += 1
                out.append((i + 1, j))
                i = j
                continue
            i += 1
        return out
    fence: str | None = None
    start = 0
    for i, line in enumerate(lines):
        m = _FENCE.match(line)
        if not m:
            continue
        if fence is None:
            info = line.strip()[len(m[1]):].strip().split(" ")[0].lower()
            fence, start = m[1], i + 1
            if info not in CONFIG_LANGS:
                fence = "skip" + m[1]  # a code fence of another language: track it, do not redact
        elif m[1][0] == fence.removeprefix("skip")[0] and not line.strip()[len(m[1]):]:
            if not fence.startswith("skip"):
                out.append((start, i))
            fence = None
    return out


def redact_config_examples(path: str, text: str) -> str:
    lines = text.split("\n")
    for start, end in _config_blocks(path, lines):
        if end > start:
            block, _ = redact("\n".join(lines[start:end]), config=True)
            lines[start:end] = block.split("\n")
    return "\n".join(lines)


def build_doc_chunks(path: str, content: str, count_tokens: CountTokens,
                     max_tokens: int) -> list[Chunk]:
    content = redact_config_examples(path, content)
    lines = content.split("\n")
    chunks: list[Chunk] = []
    for s in sections(path, content):
        body = lines[s.heading_end:s.end] if s.heading_end >= s.start else lines[s.start - 1:s.end]
        if s.heading_end >= s.start and not any(ln.strip() for ln in body):
            continue  # a heading with nothing under it before the next heading
        chunks += unit_chunks(path, s.trail, lines, s.start, s.end, count_tokens, max_tokens)
    return chunks


def build_all_doc_chunks(files: list[tuple[str, str]], count_tokens: CountTokens,
                         max_tokens: int) -> tuple[list[Chunk], DocSelection]:
    """Doc chunks for every selected doc file of (path, content) pairs; the selection says which
    files were left out for size."""
    picked = select_docs(files)
    chunks: list[Chunk] = []
    for path, content in picked.files:
        chunks += build_doc_chunks(path, content, count_tokens, max_tokens)
    return chunks, picked
