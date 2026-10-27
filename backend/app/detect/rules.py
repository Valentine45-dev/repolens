"""The rule catalogue. Every finding's rule_id is one of these; the API serves this list so the
UI labels always match real rules. Rules report possible issues: they can miss real ones and
flag safe code (the UI says so)."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rule:
    id: str
    language: str  # python | javascript (JS and TS) | any
    severity: str  # high | medium | low
    title: str  # short name shown in lists
    looks_for: str  # what the rule matches, in plain language
    why: str  # why it can be risky
    false_positive: str  # when a match is probably fine


@dataclass(frozen=True)
class Hit:
    rule_id: str
    line: int  # 1-based


SECRET_RULE = "hardcoded-secret"

RULES: dict[str, Rule] = {
    r.id: r
    for r in [
        Rule(
            SECRET_RULE, "any", "high", "Hardcoded secret",
            "Values that look like keys, tokens or passwords written into the code or config.",
            "Anyone who can read the repository can use the secret; it also stays in git history.",
            "the value is a placeholder, a test key, or loaded from the environment elsewhere. "
            "In test or example code this rule reports low severity.",
        ),
        Rule(
            "py-eval-exec", "python", "high", "Use of eval() or exec()",
            "Calls to Python's built-in eval() or exec().",
            "If any part of the input comes from a user, they can run arbitrary Python code.",
            "the argument is a constant or fully controlled by the program (for example a "
            "generated expression in a build script).",
        ),
        Rule(
            "py-subprocess-shell", "python", "high", "subprocess with shell=True",
            "subprocess calls (run, call, Popen, check_call, check_output) with shell=True.",
            "The command goes through a shell, so unescaped input can inject extra commands.",
            "the command is a fixed string with no outside input.",
        ),
        Rule(
            "py-sql-string", "python", "high", "SQL built from strings",
            "A SQL statement built with an f-string, +, % or .format() that includes a "
            "non-constant value.",
            "Values pasted into SQL text can change the query (SQL injection); query "
            "parameters avoid this.",
            "the inserted part is a constant such as a table name chosen by the program, or the "
            "string is only logged and never executed.",
        ),
        Rule(
            "py-bare-except", "python", "low", "Bare except",
            "except: clauses that do not name an exception type.",
            "They also catch KeyboardInterrupt and SystemExit and can hide real errors.",
            "the handler re-raises, or it is a deliberate last-resort guard that logs the error.",
        ),
        Rule(
            "js-eval", "javascript", "high", "Use of eval()",
            "Calls to the global eval().",
            "If any part of the input comes from a user, they can run arbitrary JavaScript.",
            "the argument is a constant, for example in a build or test script.",
        ),
        Rule(
            "js-new-function", "javascript", "high", "new Function()",
            "Functions created from strings with new Function(...) or Function(...).",
            "Like eval(), it runs code built at runtime; user input in it can run arbitrary code.",
            "all arguments are constants written by the program.",
        ),
        Rule(
            "js-child-process-exec", "javascript", "high", "child_process exec with dynamic input",
            "exec() or execSync() from child_process whose command is not a constant string.",
            "exec runs the command through a shell, so unescaped input can inject extra "
            "commands; execFile/spawn with an argument list avoid the shell.",
            "the dynamic part is a constant or validated value the program controls.",
        ),
        Rule(
            "js-inner-html", "javascript", "medium", "innerHTML with dynamic value",
            "Assignments to .innerHTML or .outerHTML whose value is not a constant string.",
            "Inserting untrusted text as HTML allows cross-site scripting (XSS); textContent or "
            "a sanitizer avoids it.",
            "the value is built only from trusted, already-escaped markup.",
        ),
        Rule(
            "js-sql-string", "javascript", "high", "SQL built from strings",
            "A SQL statement built with a template literal (${...}) or + that includes a "
            "non-constant value.",
            "Values pasted into SQL text can change the query (SQL injection); query "
            "parameters avoid this.",
            "the inserted part is a constant such as a table name chosen by the program, or the "
            "string is only logged and never executed.",
        ),
    ]
}

DETECTOR_RULES = [rule_id for rule_id in RULES if rule_id != SECRET_RULE]

# SQL-shaped text: the statement keywords in their usual order. To keep prose like
# "select an item from the list" out, the text must either start with the statement (any case)
# or spell the keywords in upper case.
_STATEMENT = (
    r"select\s.+?\sfrom\s|insert\s+into\s|update\s+[\w.\"`\[\]]+\s+set\s|delete\s+from\s"
)
_SQL_AT_START = re.compile(rf"^[\s(]*(?:{_STATEMENT})", re.IGNORECASE | re.DOTALL)
_SQL_UPPER = re.compile(
    r"\bSELECT\s.+?\sFROM\s|\bINSERT\s+INTO\s|\bUPDATE\s+[\w.\"`\[\]]+\s+SET\s|\bDELETE\s+FROM\s",
    re.DOTALL,
)


def looks_like_sql(text: str) -> bool:
    text += " "
    return bool(_SQL_AT_START.search(text) or _SQL_UPPER.search(text))
