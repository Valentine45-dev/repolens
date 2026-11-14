"""Best-effort secret redaction (design section 13.4).

Matches are replaced with [REDACTED] before any text is stored. Newlines inside a match
are kept, so line numbers in the redacted text are the same as in the original.

Every pattern runs in time linear in the text (review S-08: a crafted line of `token-token-…`
or `a.a.a.…` used to take minutes to hours). The rules that keep it linear:
- a pattern that starts with a run of characters (`[\\w-]*name`, `scheme://`, `eyJ…`) may only
  start where such a run starts (a lookbehind), and the run's length is bounded, so a long run is
  scanned once, not once per position;
- no nested or adjacent unbounded repeats of the same characters;
- private keys are found by position (each BEGIN marker looks up the next END marker), not by a
  lazy scan to the end of the text;
- lines longer than MAX_LINE are never stored (see `_cap_long_lines`);
- line numbers are counted incrementally.
`tests/test_redact.py` times 100 KB of each known worst case.
"""

import bisect
import re
from dataclasses import dataclass

REDACTED = "[REDACTED]"

# No stored line is longer than this. A longer line (minified data, a generated table, a crafted
# file) is replaced by a marker, so the line count is unchanged and its text is never stored; the
# fixed-format token patterns still run on it, so a token in it is reported.
MAX_LINE = 5000

# Fixed-format tokens: a literal prefix and a bounded or self-delimiting body, safe on any input.
_TOKEN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("api-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}")),
    # starts only where a run of token characters starts: `eyJ-eyJ-eyJ-…` is scanned once
    ("jwt", re.compile(
        r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]

_KEY_BEGIN = re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY-----")
_KEY_END = re.compile(r"-----END [A-Z ]{0,40}PRIVATE KEY-----")
KEY_SPAN_MAX = 20_000  # an 8192-bit RSA key in PEM is about 6.5 KB

_KEYWORDS = r"(?:password|passwd|pwd|secret|token|api_?key|access_?key|private_?key)"

# (kind, pattern). If a pattern has a named group "secret", only that group is redacted.
# Earlier patterns win when two matches overlap.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    *_TOKEN_PATTERNS,
    (
        "url-password",
        # the scheme starts only where a scheme can start, and its parts are bounded
        re.compile(r"(?<![A-Za-z0-9+.-])[a-z][a-z0-9+.-]{0,30}://[^\s:/@'\"]{1,200}:"
                   r"(?P<secret>[^\s:/@'\"]{3,})@"),
    ),
    (
        "secret-assignment",
        re.compile(
            rf"(?i)(?<![\w-])[\w-]{{0,40}}?{_KEYWORDS}[\w-]{{0,40}}"
            r"[\"']?\s*[:=]\s*[\"'](?P<secret>[^\"'\s]{6,})[\"']"
        ),
    ),
]

_SECRET_NAME = rf"[\w.-]{{0,40}}?{_KEYWORDS}[\w.-]{{0,40}}"

# Config files only (YAML, INI/CFG, TOML, shell): an unquoted value on its own line, like
# `POSTGRES_PASSWORD: hunter2pass`, `password = hunter2pass`, `export API_TOKEN=abc123def`,
# `- DB_PASSWORD=hunter2pass`. Not used for code, where `password = get_password()` is common,
# nor for Markdown/text, where prose would match.
_CONFIG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "secret-assignment",
        re.compile(
            rf"(?im)^[ \t]*(?:-[ \t]+)?(?:export[ \t]+)?{_SECRET_NAME}[ \t]*[:=][ \t]*"
            r"(?P<secret>[^\s'\"#;]{6,})[ \t]*(?:#.*)?$"
        ),
    ),
]
CONFIG_SUFFIXES = {".yaml", ".yml", ".ini", ".cfg", ".toml", ".sh"}

# Unquoted config values that are not secrets: references filled in elsewhere (${VAR}, $VAR,
# {{ var }}, <your-key>, %(var)s, YAML aliases and tags), paths, URLs (a password inside a URL
# is the url-password pattern's job), numbers and booleans.
_CONFIG_NOT_SECRET = re.compile(
    r"^(?:[$<{*!&~./%]|https?:|\d+$|(?:true|false|yes|no|on|off|null|none)$)", re.IGNORECASE
)

# A value made only of f-string placeholders ("{password}", "{user}{pw}") is filled in at run
# time, so it is not a secret (found by the PyGoat eval: an f-string SQL query was redacted).
_PLACEHOLDER_ONLY = re.compile(r"(?:\{[^{}\s]*\})+")


# Values that are clearly stand-ins, not credentials. Only wording and shapes that say "fill this
# in" are listed. Weak real passwords (admin, password123, secret, 123456) are NOT placeholders:
# a guessable credential in code is the finding. The name returned is the pattern that matched.
_PLACEHOLDER_MARKERS = re.compile(
    r"change[-_ ]?me|change[-_ ]?this|replace[-_ ]?me|placeholder|dummy|fake|example|redacted"
    r"|not[-_ ]?a[-_ ]?secret|todo|fixme",
    re.IGNORECASE,
)
_PLACEHOLDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # <your-key>, ${API_KEY}, $API_KEY, {{ token }}, %(token)s
    ("template", re.compile(r"^(?:<[^<>]*>|\$\{[^}]*\}|\$[A-Za-z_]\w*|\{\{.*\}\}|%\([^)]*\)s)$")),
    # your-api-key, YOUR_SECRET_HERE, insert-token-here, paste_key_here
    ("your-or-here", re.compile(
        r"^(?:your|insert|enter|paste|put)[-_. ]\w|^your(?:key|token|secret|pass|api)"
        r"|[-_.](?:here|goes[-_.]?here)$",
        re.IGNORECASE)),
    ("marker-word", _PLACEHOLDER_MARKERS),
    # xxxxxx, ******, aaaaaa, 000000 (six or more of one character)
    ("repeated-char", re.compile(r"^(.)\1{5,}$")),
    # xxxx-xxxx-xxxx, ****-****, ####
    ("mask", re.compile(r"^[xX*#._-]{4,}$")),
    # values copied from vendor documentation
    ("vendor-doc", re.compile(
        r"^(?:wJalrXUtnFEMI/|sk_test_" + "4eC39HqLyjWDarjtT1zdp7dc|"
        r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIi)")),
]


def placeholder_pattern(value: str) -> str | None:
    """Name of the placeholder pattern `value` matches, or None. Looks at the raw value in
    memory; the value is never stored or logged."""
    for name, pattern in _PLACEHOLDER_PATTERNS:
        if (pattern.search(value) if name == "marker-word" else pattern.match(value)):
            return name
    return None


@dataclass(frozen=True)
class SecretMatch:
    """Where a secret was found. Never holds the secret value."""

    line: int  # 1-based, in the original (and redacted) text
    kind: str
    placeholder: str | None = None  # name of the placeholder pattern, if the value is a stand-in


def _cap_long_lines(text: str) -> tuple[str, list[SecretMatch]]:
    """Replace every line longer than MAX_LINE by a marker. Returns the new text and one match per
    token kind found on such a line (the line itself is never stored)."""
    lines = text.split("\n")
    if max(map(len, lines)) <= MAX_LINE:
        return text, []
    found = []
    for i, line in enumerate(lines):
        if len(line) > MAX_LINE:
            for kind, pattern in _TOKEN_PATTERNS:
                if m := pattern.search(line):
                    found.append(SecretMatch(line=i + 1, kind=kind,
                                             placeholder=placeholder_pattern(m[0])))
            lines[i] = f"{REDACTED} (line of {len(line)} characters not stored)"
    return "\n".join(lines), found


def _private_keys(text: str) -> list[tuple[int, int]]:
    """BEGIN ... END spans. Each BEGIN looks up the next END by position (bisect), so many BEGIN
    markers without an END cost one lookup each, not a scan to the end of the text."""
    ends = [m.end() for m in _KEY_END.finditer(text)]
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _KEY_BEGIN.finditer(text):
        if m.start() < pos:
            continue  # inside the previous key
        i = bisect.bisect_left(ends, m.end())
        if i < len(ends) and ends[i] - m.start() <= KEY_SPAN_MAX:
            spans.append((m.start(), ends[i]))
            pos = ends[i]
    return spans


def redact(text: str, config: bool = False) -> tuple[str, list[SecretMatch]]:
    """Return (redacted text, matches). Line count is unchanged. `config` adds the unquoted
    config-value rule (for CONFIG_SUFFIXES files)."""
    text, long_line_matches = _cap_long_lines(text)
    spans: list[tuple[int, int, str]] = [(s, e, "private-key") for s, e in _private_keys(text)]
    starts = [s for s, _, _ in spans]
    for kind, pattern in _PATTERNS + (_CONFIG_PATTERNS if config else []):
        for m in pattern.finditer(text):
            if "secret" in pattern.groupindex:
                if _PLACEHOLDER_ONLY.fullmatch(m["secret"]):
                    continue
                if pattern in (p for _, p in _CONFIG_PATTERNS) and \
                        _CONFIG_NOT_SECRET.match(m["secret"]):
                    continue
                start, end = m.span("secret")
            else:
                start, end = m.span()
            # Earlier patterns win: skip a match that overlaps an accepted span. The accepted
            # spans never overlap, so sorted starts and a bisect find the only two neighbours.
            i = bisect.bisect_left(starts, start)
            if (i > 0 and spans[i - 1][1] > start) or (i < len(spans) and spans[i][0] < end):
                continue
            starts.insert(i, start)
            spans.insert(i, (start, end, kind))

    if not spans:
        return text, long_line_matches

    spans.sort()
    out: list[str] = []
    matches: list[SecretMatch] = list(long_line_matches)
    pos, line = 0, 1
    for start, end, kind in spans:
        out.append(text[pos:start])
        line += text.count("\n", pos, start)  # counted from the previous match: linear
        newlines = text.count("\n", start, end)
        out.append(REDACTED + "\n" * newlines)
        matches.append(SecretMatch(line=line, kind=kind,
                                   placeholder=placeholder_pattern(text[start:end])))
        line += newlines
        pos = end
    out.append(text[pos:])
    matches.sort(key=lambda m: m.line)
    return "".join(out), matches
