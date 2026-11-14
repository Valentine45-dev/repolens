"""Best-effort secret redaction (design section 13.4).

Matches are replaced with [REDACTED] before any text is stored. Newlines inside a match
are kept, so line numbers in the redacted text are the same as in the original.

Every pattern runs in time linear in the text (review S-08: a crafted line of `token-token-…`
or `a.a.a.…` used to take minutes to hours). The rules that keep it linear:
- a pattern that starts with a run of characters (a name, `scheme://`, `eyJ…`) may only start
  where such a run starts (a lookbehind), and the run's length is bounded, so a long run is
  scanned once, not once per position;
- no nested or adjacent unbounded repeats of the same characters;
- private keys are found by position (each BEGIN marker looks up the next END marker), not by a
  lazy scan to the end of the text;
- lines longer than MAX_LINE are never stored (see `_cap_long_lines`);
- overlaps are merged after one sort, and line numbers are counted incrementally.
`tests/test_redact.py` times 100 KB of each known worst case.

What counts as a named secret (review S-03) is decided in two steps: a regex finds
`name <operator> "value"` candidates, then plain Python checks the name and the value. The
tables of what must and must not be redacted are in `tests/test_redact.py`.
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

# the scheme starts only where a scheme can start, and its parts are bounded
_URL_PASSWORD = re.compile(
    r"(?<![A-Za-z0-9+.-])[a-z][a-z0-9+.-]{0,30}://[^\s:/@'\"]{1,200}:(?P<secret>[^\s:/@'\"]{3,})@")

# PEM keys and PGP key blocks
_KEY_BEGIN = re.compile(r"-----BEGIN [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----")
_KEY_END = re.compile(r"-----END [A-Z ]{0,40}PRIVATE KEY(?: BLOCK)?-----")
KEY_SPAN_MAX = 20_000  # an 8192-bit RSA key in PEM is about 6.5 KB
# A key with no END line (cut short in a doc or a string): the header and the body after it.
_KEY_HEADER_TAIL = re.compile(r"(?:\\n|[A-Za-z0-9+/=])*")  # rest of the header line, `\n` escapes
_KEY_BODY_LINE = re.compile(r"[ \t\"'`]*[A-Za-z0-9+/=]{16,}(?:\\n)?[ \t\"'`,;]*\n")

# `name <operator> "value"`. The name starts only where a name can start and is bounded; an
# optional closing quote or bracket (`"password":`, `["password"]`), an optional type annotation
# (`password: str =`, `apiKey: string =`), an optional b/r/u/f prefix, and a value in double or
# single quotes that may hold spaces, the other quote and backslash escapes, but not a newline.
_ASSIGN = re.compile(
    r"(?<![\w$.\-])(?P<name>-{0,2}[A-Za-z_$][\w$.\-]{0,79})"
    r"(?:[\"']\]?|\])?\s*"
    r"(?:"
    r":\s*(?=[bBrRuUfF]{0,2}[\"'])"                    # key: "value" (dict, JSON, YAML, JS)
    r"|(?::[ \t]*[\w.\[\], |]{1,60}?[ \t]*)?"           # optional annotation, then
    r"(?:=|:=|\?\?=|\|\|=)(?!=)\s*"                     # an assignment (not ==)
    r")"
    r"[bBrRuUfF]{0,2}"
    r"(?:\"(?P<dq>(?:[^\"\\\n]|\\.){6,})\"|'(?P<sq>(?:[^'\\\n]|\\.){6,})')"
)

# Config files only (YAML, INI/CFG, TOML, shell): an unquoted value on its own line, like
# `POSTGRES_PASSWORD: hunter2pass`, `password = hunter2pass`, `export API_TOKEN=abc123def`,
# `- DB_PASSWORD=hunter2pass`. Not used for code, where `password = get_password()` is common,
# nor for Markdown/text, where prose would match.
_CONFIG_ASSIGN = re.compile(
    r"(?im)^[ \t]*(?:-[ \t]+)?(?:export[ \t]+)?(?P<name>[\w.-]{1,80})[ \t]*[:=][ \t]*"
    r"(?P<secret>[^\s'\"#;]{6,})[ \t]*(?:#.*)?$"
)
CONFIG_SUFFIXES = {".yaml", ".yml", ".ini", ".cfg", ".toml", ".sh"}

# --- which names hold a secret -----------------------------------------------------------------
# Matched anywhere in the name's last segment, as before this check existed
# (`adminpassword`, `GITHUB_TOKEN`, `client_secret`) ...
_KEYWORDS = re.compile(
    r"password|passwd|passphrase|pwd|secret|token|api_?key|access_?key|private_?key|credential")
# ... except inside these ordinary words
_NOT_KEYWORDS = re.compile(r"tokeni[sz]|secretar")
# Short keywords count only as a whole name part (`DB_PASS`, `dbPass`), never in bypass/compass.
_WHOLE_PART_KEYWORDS = {"pass", "creds"}
# When the last part of the name says what the value is about, the value is not the secret:
# `password_field = "password"`, `TOKEN_URL`, `SECRET_KEY_FILE`, `PASSWORD_MIN_LENGTH`.
_DESCRIPTOR_PARTS = {
    "file", "files", "path", "dir", "folder", "url", "uri", "endpoint", "host", "env", "var",
    "name", "names", "field", "fields", "label", "hint", "help", "text", "msg", "message",
    "messages", "error", "errors", "err", "prompt", "title", "placeholder", "type", "kind",
    "mode", "length", "len", "min", "max", "size", "count", "regex", "pattern", "policy",
    "rule", "rules", "format", "id", "ids", "header", "param", "column", "col", "attr",
    "option", "flag", "enabled", "required", "ttl", "expiry", "expires", "timeout",
    "lifetime", "age", "version", "prefix", "suffix", "location", "backend", "provider",
    "class", "module", "algorithm", "algo", "scheme", "scope", "scopes", "audience",
    "issuer", "widget", "input", "selector", "route", "view", "template", "lookup",
}
_NAME_PARTS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _name_kind(name: str) -> str | None:
    """'keyword' or 'short' (matched by a short whole-part keyword) if `name` holds a secret,
    else None. Only the last segment counts: `settings.SECRET_KEY` yes,
    `send_password_mock.return_value` no."""
    name = re.split(r"[.\[\]]", name)[-1].lstrip("-$")
    parts = [p.lower() for p in _NAME_PARTS.findall(name)]
    if parts and parts[-1] in _DESCRIPTOR_PARTS:
        return None
    low = name.lower()
    hit = _KEYWORDS.search(low)
    if hit and not _NOT_KEYWORDS.search(low, max(0, hit.start() - 3), hit.end() + 4):
        return "keyword"
    return "short" if any(p in _WHOLE_PART_KEYWORDS for p in parts) else None


# --- which values are secrets ------------------------------------------------------------------
# A value made only of f-string placeholders ("{password}", "{user}{pw}") is filled in at run
# time, so it is not a secret (found by the PyGoat eval: an f-string SQL query was redacted).
_PLACEHOLDER_ONLY = re.compile(r"(?:\{[^{}\s]*\})+")
# Words that make a value with spaces read as a message about the secret, not the secret.
_PROSE_WORDS = re.compile(r"(?i)\b(?:password|passphrase|token|secret|key|pass|credentials?)\b")
_TEMPLATE = re.compile(r"^(?:\$\{\{.*\}\}|\$\{[^}]*\}|\{\{.*\}\}|<[^<>]*>|%\([^)]*\)s)$")
_CONSTANT_NAME = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


def _secret_value(value: str, name_kind: str) -> bool:
    if value == REDACTED or _PLACEHOLDER_ONLY.fullmatch(value):
        return False
    if name_kind == "short" and _CONSTANT_NAME.match(value):
        return False  # PASS = "PASS_THROUGH"
    if not re.search(r"[\s\"']", value):
        return True  # a value of the shape this rule always matched keeps its old treatment
    # Shapes added by the S-03 fix (spaces, the other quote): leave out what reads as text.
    if (value != value.strip()  # " world": a streamed word, not a credential
            or not re.search(r"[A-Za-z0-9]", value)  # punctuation tables
            or _TEMPLATE.match(value)):  # "${{ secrets.TOKEN }}"
        return False
    words = value.split()
    if len(words) == 1:
        return True  # "it's-my-pass-123"
    return not (len(words) > 8 or value[-1] in ".!?:" or _PROSE_WORDS.search(value)
                or "%s" in value or "{}" in value)


# Unquoted config values that are references filled in elsewhere, not secrets: ${VAR},
# ${{ x }}, $VAR (one case), {{ var }}, <your-key>, %(var)s, YAML aliases, anchors and lower-case
# tags (`!vault_lookup`); paths, URLs (a password inside a URL is the url-password rule's job),
# numbers and booleans. `$ecretPass99` and `!Passw0rd2026` are not references.
_CONFIG_REFERENCE = re.compile(
    r"^(?:\$\{\{.*\}\}|\$\{[^}]*\}|\$[A-Z_][A-Z0-9_]*|\$[a-z_][a-z0-9_]*|\{\{.*\}\}|<[^<>]*>"
    r"|%\([^)]*\)s|\*[\w.-]+|&[\w.-]+|!!?[a-z][a-z_]*|(?:\.{1,2}/|/|~/)\S*|https?:\S*|\d+"
    r"|(?i:true|false|yes|no|on|off|null|none))$"
)


# --- placeholders (values that are stand-ins, not credentials) ---------------------------------
# Only wording and shapes that say "fill this in" are listed. Weak real passwords (admin,
# password123, secret, 123456) are NOT placeholders: a guessable credential in code is the
# finding. The name returned is the pattern that matched.
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


# --- finding spans -----------------------------------------------------------------------------

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
    """Key spans. Each BEGIN looks up the next END by position (bisect), so many BEGIN markers
    cost one lookup each, not a scan to the end of the text. With no END within KEY_SPAN_MAX the
    header and the base64 body that follows it are taken."""
    ends = [m.end() for m in _KEY_END.finditer(text)]
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in _KEY_BEGIN.finditer(text):
        if m.start() < pos:
            continue  # inside the previous key
        i = bisect.bisect_left(ends, m.end())
        if i < len(ends) and ends[i] - m.start() <= KEY_SPAN_MAX:
            end = ends[i]
        else:
            end = _KEY_HEADER_TAIL.match(text, m.end()).end()
            newline = text.find("\n", end)
            if newline != -1 and not text[end:newline].strip(" \t\"'`,;"):
                end = newline + 1
                while (body := _KEY_BODY_LINE.match(text, end)) and \
                        body.end() - m.start() <= KEY_SPAN_MAX:
                    end = body.end()
                if text[end - 1] == "\n":
                    end -= 1  # the newline after the body is not part of the key
        spans.append((m.start(), end))
        pos = end
    return spans


def _assignments(text: str) -> list[tuple[int, int]]:
    spans = []
    pos = 0
    while (m := _ASSIGN.search(text, pos)) is not None:
        group = "dq" if m["dq"] is not None else "sq"
        name_kind = _name_kind(m["name"])
        if name_kind is None or not _secret_value(m[group], name_kind):
            pos = m.end("name")  # rejected: a nested `key = "value"` may start after the name
            continue
        spans.append(m.span(group))
        pos = m.end()
    return spans


def _config_assignments(text: str) -> list[tuple[int, int]]:
    spans = []
    for m in _CONFIG_ASSIGN.finditer(text):
        value = m["secret"]
        name_kind = _name_kind(m["name"])
        if name_kind is None or value.startswith(REDACTED) or _CONFIG_REFERENCE.match(value):
            continue
        if _PLACEHOLDER_ONLY.fullmatch(value) or (name_kind == "short"
                                                   and _CONSTANT_NAME.match(value)):
            continue
        spans.append(m.span("secret"))
    return spans


# Order says which kind is reported when matches overlap: the more specific one.
_KIND_ORDER = {"private-key": 0, **{k: i + 1 for i, (k, _) in enumerate(_TOKEN_PATTERNS)},
               "url-password": 50, "secret-assignment": 60}


def redact(text: str, config: bool = False) -> tuple[str, list[SecretMatch]]:
    """Return (redacted text, matches). Line count is unchanged. `config` adds the unquoted
    config-value rule (for CONFIG_SUFFIXES files)."""
    text, long_line_matches = _cap_long_lines(text)
    spans: list[tuple[int, int, str]] = [(s, e, "private-key") for s, e in _private_keys(text)]
    for kind, pattern in _TOKEN_PATTERNS:
        spans += [(*m.span(), kind) for m in pattern.finditer(text)]
    for m in _URL_PASSWORD.finditer(text):
        if not _PLACEHOLDER_ONLY.fullmatch(m["secret"]):
            spans.append((*m.span("secret"), "url-password"))
    spans += [(s, e, "secret-assignment") for s, e in _assignments(text)]
    if config:
        spans += [(s, e, "secret-assignment") for s, e in _config_assignments(text)]
    if not spans:
        return text, long_line_matches

    # Overlapping matches are merged into their union (an AWS key at the start of a longer value
    # must not leave the rest of the value behind); the more specific kind is reported.
    spans.sort(key=lambda s: (s[0], _KIND_ORDER[s[2]]))
    merged: list[list] = []
    for start, end, kind in spans:
        if merged and start < merged[-1][1]:
            last = merged[-1]
            last[1] = max(last[1], end)
            if _KIND_ORDER[kind] < _KIND_ORDER[last[2]]:
                last[2] = kind
        else:
            merged.append([start, end, kind])

    out: list[str] = []
    matches: list[SecretMatch] = list(long_line_matches)
    pos, line = 0, 1
    for start, end, kind in merged:
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
