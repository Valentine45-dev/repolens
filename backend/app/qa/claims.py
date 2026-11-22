"""Claim check (Step 5 Part C, QA_CLAIM_CHECK): every cited claim must quote its evidence.

With the check on, the model writes each claim followed by `[path:start-end "exact quote"]`
(prompts/system_claims.md). A claim (the sentence a citation is attached to) is kept only if at
least one of its citations passes both checks:
1. the cited range lies inside one snippet that was sent (as citation validation does anyway);
2. the quote appears in those lines as they were sent (escaped like the prompt, without the
   `N| ` line prefixes), whitespace-normalised, case-sensitive, and is not trivial (>= 3 words or
   >= 15 characters).
This proves the quoted evidence exists in the cited lines. It does not prove that the evidence
supports the claim.

Parsing is tolerant: `[...]` or `(...)`, straight, curly or backtick quote marks, `#L` and `L`
forms, line prefixes inside a quote. A citation written without a quote (bare `path:N-M`) is a
citation attempt with no quote: it fails. Citations separated only by spaces, commas or semicolons
belong to the same claim. A bare citation followed later in the same sentence by a bracket belongs
to that bracket's claim.

Result: failed claims are removed with their citations; failing citations of kept claims are
dropped; quotes are stripped and kept citations written `(path:N-M)`, so citation validation, the
chips and the frozen eval scorer read them as before. Sentences without any citation are left
alone. If every claim fails, the answer is the "could not find" sentence. The note saying how many
statements were removed is returned on its own, never written into the answer text. Code fences are
not read for citations.
"""

import re
from dataclasses import dataclass, field

from app.qa.citations import citation_spans
from app.qa.prompt import COULD_NOT_FIND, _escape
from app.qa.retrieve import Snippet

_QUOTE = (r"(?:\"(?P<q1>[^\n]*?)\"|“(?P<q2>[^\n]*?)”|`(?P<q3>[^\n]*?)`)(?=\s*[\])])")
GROUP = re.compile(r"[\[(]\s*`?(?P<cite>[^\[\]()\"“”`\n]+?)`?\s*(?:[,:–—-]\s*)?"
                   + _QUOTE + r"?\s*[\])]")
_CITE = re.compile(r"(?:\./)?(?P<path>.+?)(?::L?(?P<s>\d{1,7})(?!\d)(?:\s*[-–—]\s*L?(?P<e>\d{1,7})"
                   r"(?!\d))?|#L(?P<as>\d{1,7})(?:-L?(?P<ae>\d{1,7}))?)")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})", re.M)
_PREFIX = re.compile(r"(?:^|(?<=\s))\d{1,7}\|\s?")
_BOUNDARY = re.compile(r"[.!?][\"”')\]*_`]*\s+")
_BULLET = re.compile(r"[ \t]*(?:[-*+]|\d+[.)]|#{1,6})[ \t]+")
MIN_WORDS, MIN_CHARS = 3, 15


@dataclass
class Item:
    start: int
    end: int
    path: str
    first: int
    last: int
    quote: str | None  # None: written without a quote (fails)
    ok: bool = False
    why: str = ""


@dataclass
class Claim:
    items: list[Item]
    start: int = 0
    end: int = 0

    @property
    def kept(self) -> bool:
        return any(i.ok for i in self.items)


@dataclass
class Checked:
    text: str
    claims: list[Claim] = field(default_factory=list)
    dropped: int = 0  # citations removed by this check (failed ones)

    def summary(self) -> dict:
        kept = sum(c.kept for c in self.claims)
        removed = len(self.claims) - kept
        note = None
        if removed:
            note = (f"{removed} statement{'s' if removed != 1 else ''} removed: the quoted evidence"
                    " was not found in the cited lines.")
        return {"total": len(self.claims), "kept": kept, "removed": removed, "note": note}


def _norm(text: str) -> str:
    return " ".join(text.split())


def clean_quote(quote: str) -> str:
    """The quote as compared: line-number prefixes (`12| `) removed, whitespace normalised."""
    return _norm(_PREFIX.sub(" ", quote))


def lines_as_sent(snippet: Snippet, first: int, last: int) -> str:
    """The cited lines as the model saw them (escaped like the prompt), whitespace-normalised."""
    lines = snippet.text.split("\n")[first - snippet.start_line:last - snippet.start_line + 1]
    return _norm(" ".join(_escape(line) for line in lines))


def _inside(snippets: list[Snippet], path: str, first: int, last: int) -> Snippet | None:
    if first < 1 or last < first:
        return None
    return next((s for s in snippets if s.path == path and s.start_line <= first
                 and last <= s.end_line), None)


def check_item(item: Item, snippets: list[Snippet]) -> None:
    snippet = _inside(snippets, item.path, item.first, item.last)
    if snippet is None:
        item.why = "range not inside a sent snippet"
        return
    if item.quote is None:
        item.why = "no quote"
        return
    q = clean_quote(item.quote)
    if len(q.split()) < MIN_WORDS and len(q) < MIN_CHARS:
        item.why = "quote too short"
        return
    if q not in lines_as_sent(snippet, item.first, item.last):
        item.why = "quote not in the cited lines"
        return
    item.ok = True


def _fenced(text: str) -> list[tuple[int, int]]:
    """Character ranges of fenced code blocks."""
    out, start, fence = [], 0, None
    for m in _FENCE.finditer(text):
        if fence is None:
            fence, start = m[1], m.start()
        elif m[1][0] == fence[0] and len(m[1]) >= len(fence):
            end = text.find("\n", m.end())
            out.append((start, len(text) if end < 0 else end))
            fence = None
    if fence is not None:
        out.append((start, len(text)))
    return out


def find_items(text: str, sent_paths: set[str]) -> list[Item]:
    fences = _fenced(text)

    def in_fence(i: int) -> bool:
        return any(a <= i < b for a, b in fences)

    items: list[Item] = []
    masked = list(text)
    for m in GROUP.finditer(text):
        c = _CITE.fullmatch(m["cite"].strip())
        if not c or in_fence(m.start()):
            continue
        first = int(c["s"] or c["as"])
        last = int(c["e"] or c["ae"] or first)
        quote = next((m[g] for g in ("q1", "q2", "q3") if m[g] is not None), None)
        items.append(Item(m.start(), m.end(), c["path"].strip().replace("\\", "/"), first, last,
                          quote))
        masked[m.start():m.end()] = "\x02" * (m.end() - m.start())
    for start, end, path, first, last in citation_spans("".join(masked), sent_paths):
        if not in_fence(start):
            items.append(Item(start, end, path, first, last, None))
    return sorted(items, key=lambda i: i.start)


def _claims(text: str, items: list[Item]) -> list[Claim]:
    claims: list[Claim] = []
    for it in items:
        if claims:
            prev = claims[-1]
            gap = text[prev.items[-1].end:it.start]
            same = "\n" not in gap and not gap.strip(" \t,;")
            # a bare citation in the middle of a sentence that then gets its bracket
            bare_then_bracket = (prev.items[-1].quote is None and len(prev.items) == 1
                                 and "\n" not in gap and not _BOUNDARY.search(gap + " ")
                                 and it.quote is not None)
            if same or bare_then_bracket:
                prev.items.append(it)
                continue
        claims.append(Claim([it]))
    prev_end = 0
    for c in claims:
        first = c.items[0]
        line_start = text.rfind("\n", 0, first.start) + 1
        floor = max(line_start, prev_end)
        before = text[floor:first.start].rstrip()
        if before and before[-1] in ".!?":
            before = before[:-1]
        starts = [m.end() for m in _BOUNDARY.finditer(before)]
        c.start = floor + (starts[-1] if starts else 0)
        if c.start == line_start:
            b = _BULLET.match(text, c.start)
            if b:
                c.start = b.end()
        end = c.items[-1].end
        if end < len(text) and text[end] in ".!?;,":
            end += 1
        c.end = prev_end = end
    return claims


def _tidy(text: str) -> str:
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = re.sub(r"[ \t]+([.,;:!?)])", r"\1", line)
        line = re.sub(r"\([ \t]*\)", "", line).rstrip()
        if re.fullmatch(r"\s*(?:[-*+]|\d+[.)])?\s*[.,;:]?\s*", line) and line.strip():
            continue  # a bullet or a stray mark left with nothing after it
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _cite(it: Item) -> str:
    return f"({it.path}:{it.first}{f'-{it.last}' if it.last != it.first else ''})"


def check_claims(text: str, snippets: list[Snippet]) -> Checked:
    items = find_items(text, {s.path for s in snippets})
    if not items:
        return Checked(text)
    for it in items:
        check_item(it, snippets)
    claims = _claims(text, items)
    out, pos, dropped = [], 0, 0
    for c in claims:
        out.append(text[pos:c.start])
        if c.kept:
            cur = c.start
            for it in c.items:
                out.append(text[cur:it.start])
                if it.ok:
                    out.append(_cite(it))
                else:
                    dropped += 1
                cur = it.end
            out.append(text[cur:c.end])
        else:
            dropped += len(c.items)
        pos = c.end
    out.append(text[pos:])
    if not any(c.kept for c in claims):
        return Checked(COULD_NOT_FIND, claims, dropped)
    return Checked(_tidy("".join(out)), claims, dropped)
