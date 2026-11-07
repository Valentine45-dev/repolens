"""Ruff rules RepoLens runs (code quality, category bug-quality). Generated once from `ruff rule
--all --output-format json` for the Ruff version in uv.lock (0.17.2); preview rules are not
selected. Ruff reads the code as data only: `--isolated` (no repo config), `--no-cache`,
`--no-fix`, `--ignore-noqa`, run on the redacted copy of each file."""
# ruff: noqa: E501

RUFF_SELECT = ["F811", "F821", "F822", "F823", "B006", "B015", "B023", "PLE"]
# PLE0704 (bare `raise` outside an except block) is not run: on flask all 3 hits were helpers that
# deliberately re-raise the active exception when called from an except block ("Re-raise if
# called with an active exception"), so it was wrong 3 of 3 times.
RUFF_IGNORE = ["PLE0704"]

# code: (Ruff rule name, Ruff summary with its placeholders shown as ...)
RUFF_CODES: dict[str, tuple[str, str]] = {
    "B006": ("mutable-argument-default", "Do not use mutable data structures for argument defaults"),
    "B015": ("useless-comparison", "Pointless comparison. Did you mean to assign a value? Otherwise, prepend `assert` or remove it"),
    "B023": ("function-uses-loop-variable", "Function definition does not bind loop variable `…`"),
    "F811": ("redefined-while-unused", "Redefinition of unused `…` from …"),
    "F821": ("undefined-name", "Undefined name `…`. …"),
    "F822": ("undefined-export", "Undefined name `…` in `__all__`"),
    "F823": ("undefined-local", "Local variable `…` referenced before assignment"),
    "PLE0100": ("yield-in-init", "`__init__` method is a generator"),
    "PLE0101": ("return-in-init", "Explicit return in `__init__`"),
    "PLE0115": ("nonlocal-and-global", "Name `…` is both `nonlocal` and `global`"),
    "PLE0116": ("continue-in-finally", "`continue` not supported inside `finally` clause"),
    "PLE0117": ("nonlocal-without-binding", "Nonlocal name `…` found without binding"),
    "PLE0118": ("load-before-global-declaration", "Name `…` is used prior to global declaration on …"),
    "PLE0237": ("non-slot-assignment", "Attribute `…` is not defined in class's `__slots__`"),
    "PLE0241": ("duplicate-bases", "Duplicate base `…` for class `…`"),
    "PLE0302": ("unexpected-special-method-signature", "The special method `…` expects …, … … given"),
    "PLE0303": ("invalid-length-return-type", "`__len__` does not return a non-negative integer"),
    "PLE0304": ("invalid-bool-return-type", "`__bool__` does not return `bool`"),
    "PLE0305": ("invalid-index-return-type", "`__index__` does not return an integer"),
    "PLE0307": ("invalid-str-return-type", "`__str__` does not return `str`"),
    "PLE0308": ("invalid-bytes-return-type", "`__bytes__` does not return `bytes`"),
    "PLE0309": ("invalid-hash-return-type", "`__hash__` does not return an integer"),
    "PLE0604": ("invalid-all-object", "Invalid object in `__all__`, must contain only strings"),
    "PLE0605": ("invalid-all-format", "Invalid format for `__all__`, must be `tuple` or `list`"),
    "PLE0643": ("potential-index-error", "Expression is likely to raise `IndexError`"),
    "PLE1132": ("repeated-keyword-argument", "Repeated keyword argument: `…`"),
    "PLE1142": ("await-outside-async", "`await` should be used within an async function"),
    "PLE1205": ("logging-too-many-args", "Too many arguments for `logging` format string"),
    "PLE1206": ("logging-too-few-args", "Not enough arguments for `logging` format string"),
    "PLE1300": ("bad-string-format-character", "Unsupported format character '…'"),
    "PLE1307": ("bad-string-format-type", "Format type does not match argument type"),
    "PLE1310": ("bad-str-strip-call", "String `…` call contains duplicate characters (did you mean `…`?)"),
    "PLE1507": ("invalid-envvar-value", "Invalid type for initial `os.getenv` argument; expected `str`"),
    "PLE1519": ("singledispatch-method", "`@singledispatch` decorator should not be used on methods"),
    "PLE1520": ("singledispatchmethod-function", "`@singledispatchmethod` decorator should not be used on non-method functions"),
    "PLE1700": ("yield-from-in-async-function", "`yield from` statement in async function; use `async for` instead"),
    "PLE2502": ("bidirectional-unicode", "Contains control characters that can permit obfuscated code"),
    "PLE2510": ("invalid-character-backspace", "Invalid unescaped character backspace, use '\b' instead"),
    "PLE2512": ("invalid-character-sub", "Invalid unescaped character SUB, use '\x1a' instead"),
    "PLE2513": ("invalid-character-esc", "Invalid unescaped character ESC, use '\x1b' instead"),
    "PLE2514": ("invalid-character-nul", "Invalid unescaped character NUL, use '\0' instead"),
    "PLE2515": ("invalid-character-zero-width-space", "Invalid unescaped character zero-width-space, use '\u200B' instead"),
}

# Undefined names and exports, a local read before it is set, and a loop variable captured
# by a closure are likely run-time errors or wrong results: medium. The rest is low.
MEDIUM = {"F821", "F822", "F823", "B023"}

# Text written for the rules people meet most; every other code gets the generic text.
SPECIFIC: dict[str, tuple[str, str]] = {
    "F821": (
        "A name that is used but never defined or imported in scope.",
        "Running that line raises NameError.",
    ),
    "F811": (
        "A name defined again before the first definition was used.",
        "The first definition is dead code or the wrong one is called.",
    ),
    "F822": (
        "A name listed in __all__ that the module does not define.",
        "`from module import *` and documentation tools fail or miss it.",
    ),
    "F823": (
        "A local variable read before it is assigned in the same function.",
        "Raises UnboundLocalError when that line runs.",
    ),
    "B006": (
        "A mutable value (list, dict, set) used as a default argument.",
        "The default is created once and shared by every call, so changes leak between calls.",
    ),
    "B015": (
        "A comparison whose result is thrown away, such as a line that only says x == 1.",
        "Usually a typo for an assignment, so nothing happens.",
    ),
    "B023": (
        "A function defined in a loop that uses the loop variable.",
        "Every such function sees the last value of the variable, not its own.",
    ),
}
