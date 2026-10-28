"""Chunking for retrieval: one chunk per function, method and class, plus module-level chunks for
top-level code. Text comes only from the redacted file content. Every chunk keeps its own line
range (cited as path:start-end), and every embedded text fits the model's input limit, counted
with the model's own tokenizer: longer units are split into overlapping line windows."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from app.ingest.parse import ParsedSymbol

OVERLAP_LINES = 3
CODE_KINDS = ("function", "method", "class")

CountTokens = Callable[[list[str]], list[int]]


@dataclass(frozen=True)
class Chunk:
    path: str
    qualified_name: str  # the symbol the chunk belongs to (module for top-level code)
    start_line: int  # 1-based, inclusive
    end_line: int
    text: str  # the code lines (redacted), what the LLM is shown
    embed_text: str  # prefix + code, what is embedded
    token_count: int  # tokens of embed_text, special tokens included
    window: bool  # part of a unit that had to be split
    unit_start: int  # first line of that unit (same for all its windows)


def prefix(path: str, qualified_name: str) -> str:
    """Path and name first, so a question that names a symbol or file can match the chunk."""
    return f"{path} {qualified_name}\n"


def _doc_start(lines: list[str], start: int, floor: int) -> int:
    """First line of the comment that documents the unit starting at `start` (1-based): a block
    comment (`/** ... */`) or a run of `//` / `#` lines directly above it, one blank line
    between them allowed (Express puts one after its JSDoc). Never above `floor`; `start` if
    there is no such comment. Python docstrings are inside the def already."""
    i = start - 1
    if i >= floor and not lines[i - 1].strip():
        i -= 1  # one blank line
    if i < floor:
        return start
    above = lines[i - 1].strip()
    if above.endswith("*/"):
        # The opening line starts with /* ("text/*" inside a JSDoc example is not one).
        j = i
        while j >= floor and not lines[j - 1].strip().startswith("/*"):
            j -= 1
        return j if j >= floor else start
    if above.startswith(("//", "#")) and not above.startswith("#!"):
        j = i
        while j - 1 >= floor and lines[j - 2].strip().startswith(("//", "#")):
            j -= 1
        return j
    return start


def _units(symbols: list[ParsedSymbol], lines: list[str]) -> list[tuple[ParsedSymbol, int, int]]:
    """(symbol, start, end) for every chunk-worthy unit: classes (header up to the first
    method), methods, functions not nested in another function, and runs of top-level code.
    A unit starts at the comment that documents it, so the comment is embedded and cited with
    the code it describes instead of becoming a separate top-level chunk."""
    n_lines = len(lines)
    module = next((s for s in symbols if s.kind == "module"), None)
    code = [s for s in symbols if s.kind in CODE_KINDS]

    def inside(inner: ParsedSymbol, outer: ParsedSymbol) -> bool:
        return outer is not inner and outer.start_line <= inner.start_line \
            and inner.end_line <= outer.end_line

    def floor(s: ParsedSymbol) -> int:
        """The comment search stops at the end of the code before s, or inside its parent."""
        limit = 1
        for o in code:
            if o is s:
                continue
            if o.end_line < s.start_line:
                limit = max(limit, o.end_line + 1)
            elif o.start_line < s.start_line <= o.end_line:
                limit = max(limit, o.start_line + 1)
        return limit

    start_of = {id(s): _doc_start(lines, s.start_line, floor(s)) for s in code}

    units = []
    for s in code:
        if any(inside(s, o) and o.kind in ("function", "method") for o in code):
            continue  # a nested helper is part of its enclosing function's chunk
        start, end = start_of[id(s)], s.end_line
        if s.kind == "class":
            methods = [m for m in code if m.kind == "method" and inside(m, s)]
            if methods:
                end = min(start_of[id(m)] for m in methods) - 1
        if end >= start:
            units.append((s, start, end))

    # Top-level code: lines outside every function/method/class (and their comments).
    covered = [False] * (n_lines + 2)
    for s in code:
        for i in range(start_of[id(s)], min(s.end_line, n_lines) + 1):
            covered[i] = True
    if module is not None:
        run_start = None
        for i in range(1, n_lines + 2):
            free = i <= n_lines and not covered[i]
            if free and run_start is None:
                run_start = i
            elif not free and run_start is not None:
                units.append((module, run_start, i - 1))
                run_start = None
    return units


def _windows(lines: list[str], line_tokens: list[int], budget: int) -> list[tuple[int, int]]:
    """Split lines (0-based) into windows whose token sum stays within budget, each overlapping
    the previous by OVERLAP_LINES lines."""
    windows, start, n = [], 0, len(lines)
    while start < n:
        end, used = start, 0
        while end < n and (used + line_tokens[end] <= budget or end == start):
            used += line_tokens[end]
            end += 1
        windows.append((start, end))  # end exclusive
        if end >= n:
            break
        start = max(end - OVERLAP_LINES, start + 1)
    return windows


def build_chunks(
    path: str,
    content: str,
    symbols: list[ParsedSymbol],
    count_tokens: CountTokens,
    max_tokens: int,
) -> list[Chunk]:
    all_lines = content.split("\n")
    chunks: list[Chunk] = []
    for symbol, start, end in _units(symbols, all_lines):
        lines = all_lines[start - 1:end]
        # Trim blank lines at the edges; skip units that are only whitespace.
        while lines and not lines[0].strip():
            lines, start = lines[1:], start + 1
        while lines and not lines[-1].strip():
            lines, end = lines[:-1], end - 1
        if not lines:
            continue
        head = prefix(path, symbol.qualified_name)
        whole = head + "\n".join(lines)
        (whole_tokens,) = count_tokens([whole])
        if whole_tokens <= max_tokens:
            chunks.append(Chunk(path, symbol.qualified_name, start, end, "\n".join(lines),
                                whole, whole_tokens, False, start))
            continue

        # Too long: overlapping windows. Per-line counts (without special tokens) give the
        # split; the exact count of each window is then checked and the window shrunk if needed.
        (head_tokens,) = count_tokens([head])
        per_line = [max(t - 2, 1) for t in count_tokens([ln or " " for ln in lines])]
        budget = max(max_tokens - head_tokens - 4, 8)
        for w_start, w_end in _windows(lines, per_line, budget):
            while True:
                text = "\n".join(lines[w_start:w_end])
                (tokens,) = count_tokens([head + text])
                if tokens <= max_tokens or w_end - w_start == 1:
                    break
                w_end -= 1
            if tokens > max_tokens:  # a single huge line: cut it to fit
                text = _truncate(head, text, count_tokens, max_tokens)
                (tokens,) = count_tokens([head + text])
            chunks.append(Chunk(path, symbol.qualified_name, start + w_start, start + w_end - 1,
                                text, head + text, tokens, True, start))
    return chunks


def _truncate(head: str, text: str, count_tokens: CountTokens, max_tokens: int) -> str:
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        (t,) = count_tokens([head + text[:mid]])
        lo, hi = (mid, hi) if t <= max_tokens else (lo, mid - 1)
    return text[:lo]


_IDENT_PARTS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def search_words(chunk: Chunk) -> str:
    """Words for the keyword index: identifiers split into parts (getUserById -> get user by id,
    get_user_by_id -> get user by id), plus the path and name."""
    words = []
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", f"{chunk.path} {chunk.qualified_name} "
                                                       f"{chunk.text}"):
        parts = [p.lower() for p in _IDENT_PARTS.findall(token)]
        words.extend(parts)
        if len(parts) > 1:
            words.append(token.lower())
    return " ".join(words)
