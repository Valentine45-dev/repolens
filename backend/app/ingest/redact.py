"""Best-effort secret redaction (design section 13.4).

Matches are replaced with [REDACTED] before any text is stored. Newlines inside a match
are kept, so line numbers in the redacted text are the same as in the original.
"""

import re
from dataclasses import dataclass

REDACTED = "[REDACTED]"

# (kind, pattern). If a pattern has a named group "secret", only that group is redacted.
# Earlier patterns win when two matches overlap.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private-key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
    ),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("stripe-key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}")),
    ("api-key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}")),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ),
    (
        "url-password",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@'\"]+:(?P<secret>[^\s:/@'\"]{3,})@"),
    ),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b[\w-]*(?:password|passwd|pwd|secret|token|api_?key|access_?key|private_?key)"
            r"[\w-]*[\"']?\s*[:=]\s*[\"'](?P<secret>[^\"'\s]{6,})[\"']"
        ),
    ),
]


# A value made only of f-string placeholders ("{password}", "{user}{pw}") is filled in at run
# time, so it is not a secret (found by the PyGoat eval: an f-string SQL query was redacted).
_PLACEHOLDER_ONLY = re.compile(r"(?:\{[^{}\s]*\})+")


@dataclass(frozen=True)
class SecretMatch:
    """Where a secret was found. Never holds the secret value."""

    line: int  # 1-based, in the original (and redacted) text
    kind: str


def redact(text: str) -> tuple[str, list[SecretMatch]]:
    """Return (redacted text, matches). Line count is unchanged."""
    spans: list[tuple[int, int, str]] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            if "secret" in pattern.groupindex:
                if _PLACEHOLDER_ONLY.fullmatch(m["secret"]):
                    continue
                start, end = m.span("secret")
            else:
                start, end = m.span()
            if not any(start < e and s < end for s, e, _ in spans):
                spans.append((start, end, kind))

    if not spans:
        return text, []

    spans.sort()
    out: list[str] = []
    matches: list[SecretMatch] = []
    pos = 0
    for start, end, kind in spans:
        out.append(text[pos:start])
        out.append(REDACTED + "\n" * text.count("\n", start, end))
        matches.append(SecretMatch(line=text.count("\n", 0, start) + 1, kind=kind))
        pos = end
    out.append(text[pos:])
    return "".join(out), matches
