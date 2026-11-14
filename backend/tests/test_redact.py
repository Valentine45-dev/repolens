import time

import pytest

from app.ingest.redact import MAX_LINE, REDACTED, redact

# Fake secrets are assembled at runtime so the source never contains a full token
# (keeps GitHub push protection and secret scanners quiet).
AWS = "AKIA" + "Z" * 16
GITHUB = "ghp_" + "a1B2" * 9
PRIVATE_KEY = (
    "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    "MIIEowIBAAKCAQEA\n"
    "abcdefghijklmnop\n"
    "-----END RSA " + "PRIVATE KEY-----"
)


def test_no_secrets_returns_text_unchanged():
    text = "import os\n\nkey = os.environ['API_KEY']\npassword = os.getenv('PW')\n"
    assert redact(text) == (text, [])


def test_redacts_value_and_reports_line_and_kind():
    text = f"x = 1\naws = '{AWS}'\n"
    redacted, matches = redact(text)
    assert AWS not in redacted
    assert redacted == f"x = 1\naws = '{REDACTED}'\n"
    assert [(m.line, m.kind) for m in matches] == [(2, "aws-access-key")]


def test_match_never_holds_the_value():
    _, matches = redact(f"token = '{GITHUB}'\n")
    assert len(matches) == 1
    assert GITHUB not in repr(matches[0])


def test_multiline_private_key_keeps_line_numbers():
    text = f"a = 1\nKEY = '''{PRIVATE_KEY}'''\nb = 2\n"
    redacted, matches = redact(text)
    assert "MIIEowIBAAKCAQEA" not in redacted
    assert redacted.count("\n") == text.count("\n")
    assert redacted.splitlines()[-1] == "b = 2"
    assert [(m.line, m.kind) for m in matches] == [(2, "private-key")]


def test_assignment_redacts_only_the_value():
    text = 'DB_PASSWORD = "hunter2hunter2"\nconfig = {"api_key": "abc123xyz789"}\n'
    redacted, matches = redact(text)
    assert redacted == f'DB_PASSWORD = "{REDACTED}"\nconfig = {{"api_key": "{REDACTED}"}}\n'
    assert [(m.line, m.kind) for m in matches] == [
        (1, "secret-assignment"),
        (2, "secret-assignment"),
    ]


def test_url_password():
    text = "DSN = 'postgresql://app:s3cretpw@db:5432/app'\n"
    redacted, matches = redact(text)
    assert "s3cretpw" not in redacted
    assert "postgresql://app:" + REDACTED + "@db:5432/app" in redacted
    assert [m.kind for m in matches] == ["url-password"]


def test_overlapping_patterns_count_once():
    # A GitHub token inside a token assignment is one secret, reported by the specific rule.
    _, matches = redact(f'GITHUB_TOKEN = "{GITHUB}"\n')
    assert [m.kind for m in matches] == ["github-token"]


def test_fstring_placeholder_is_not_a_secret():
    # PyGoat dockerized_labs/sql_injection_lab/app.py:51, which was stored corrupted.
    text = (
        "sql = f\"SELECT * FROM users WHERE username='{username}' AND password='{password}'\"\n"
        "dsn = f\"postgresql://app:{db_password}@db:5432/app\"\n"
        "creds = {\"password\": \"{user}{pw}\"}\n"
    )
    assert redact(text) == (text, [])


def test_placeholder_mixed_with_a_literal_is_still_redacted():
    text = 'password = "{prefix}hunter2hunter2"\n'
    redacted, matches = redact(text)
    assert "hunter2" not in redacted and [m.kind for m in matches] == ["secret-assignment"]


def test_plain_words_are_not_secrets():
    text = 'error = "invalid token provided"\npassword_hint = "short"\n'
    assert redact(text) == (text, [])


# --- unquoted values in config files (YAML, INI/CFG, TOML, shell) -----------------------------

CONFIG_SECRETS = (
    "services:\n"
    "  db:\n"
    "    environment:\n"
    "      POSTGRES_PASSWORD: hunter2pass\n"   # 4: YAML
    "      - DB_PASSWORD=hunter2pass\n"        # 5: compose list form
    "[auth]\n"
    "password = hunter2pass  # prod\n"         # 7: INI, trailing comment kept
    "export API_TOKEN=abc123def456\n"          # 8: shell
)


def test_config_files_redact_unquoted_values():
    redacted, matches = redact(CONFIG_SECRETS, config=True)
    assert "hunter2pass" not in redacted and "abc123def456" not in redacted
    assert f"POSTGRES_PASSWORD: {REDACTED}\n" in redacted
    assert f"password = {REDACTED}  # prod\n" in redacted
    assert f"export API_TOKEN={REDACTED}\n" in redacted
    assert redacted.count("\n") == CONFIG_SECRETS.count("\n")
    assert [(m.line, m.kind) for m in matches] == [
        (4, "secret-assignment"), (5, "secret-assignment"),
        (7, "secret-assignment"), (8, "secret-assignment"),
    ]


def test_unquoted_rule_is_for_config_files_only():
    # Code and prose keep the quoted rule only (`password = get_password()` is not a secret).
    assert redact(CONFIG_SECRETS) == (CONFIG_SECRETS, [])
    assert redact("password = get_password_from_vault\n") == (
        "password = get_password_from_vault\n", [])


def test_config_placeholders_and_plain_values_are_not_secrets():
    text = (
        "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-repolens}\n"
        "password: $DB_PASSWORD\n"
        "api_key: {{ vault_api_key }}\n"
        "token: <your-token-here>\n"
        "password = %(db_password)s\n"
        "secret: *default_secret\n"
        "secret: !vault_lookup\n"
        "password_file: /run/secrets/db_password\n"
        "token_file: ./secrets/token\n"
        "token_url: https://auth.example.com/token\n"
        "token_ttl: 360000\n"
        "require_password: false\n"
        "password: short\n"
        "password: has spaces in it\n"
    )
    assert redact(text, config=True) == (text, [])


# --- running time (review S-08) -----------------------------------------------------------------
# Each unit repeated to 100 KB is a measured worst case of one pattern before the fix (a 4 KB line
# of `token-` took over 30 s, 64 KB of `a.a.` 15 s, `eyJ-` 9 s, BEGIN markers without an END 5 s).
_KEY_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----\n"
WORST_CASES = {
    "a-": "a-", "token-": "token-", "password": "password", "password.": "password.",
    "a.": "a.", "eyJ-": "eyJ-", "key headers without END": _KEY_HEADER, "BEGIN A A": None,
    "ghp_": "ghp_", "xoxb-": "xoxb-", "sk-": "sk-", "sk_live_": "sk_live_", "AKIA": "AKIA",
    "AIza": "AIza", "a: ": "a: ", "x = 'x' ": "x = 'x' ", "p=": "p=", "pass: ": "pass: ",
    "$a": "$a", "-": "-", "--a ": "--a ", 'a="': 'a="', "password: str": "password: str",
    '["': '["', "{a}": "{a}", "many matches": 'password = "hunter2hunter2"\n',
    "url user": "a://a:a",
}
SIZE = 100_000


def _worst(name: str, lined: bool) -> str:
    unit = WORST_CASES[name]
    if unit is None:
        text = ("-----BEGIN " + "A " * SIZE)[:SIZE]
    else:
        text = (unit * (SIZE // len(unit) + 1))[:SIZE]
    return "\n".join(text[i:i + 100] for i in range(0, len(text), 100)) if lined else text


@pytest.mark.parametrize("lined", [False, True], ids=["one-line", "100-char-lines"])
@pytest.mark.parametrize("name", list(WORST_CASES))
def test_redaction_time_is_bounded(name, lined):
    text = _worst(name, lined)
    for config in (False, True):
        started = time.perf_counter()
        redacted, _ = redact(text, config=config)
        assert time.perf_counter() - started < 1.0, f"{name} config={config}"
        assert redacted.count("\n") == text.count("\n")


def test_overlong_lines_are_never_stored_and_tokens_on_them_are_reported():
    aws = "AKIA" + "Q" * 16
    long_line = "x = [" + "1, " * (MAX_LINE // 3) + f"'{aws}']"
    text = f"a = 1\n{long_line}\nb = 2\n"
    redacted, matches = redact(text)
    lines = redacted.split("\n")
    assert lines[0] == "a = 1" and lines[2] == "b = 2" and len(lines) == 4
    assert lines[1] == f"{REDACTED} (line of {len(long_line)} characters not stored)"
    assert aws not in redacted and "1, 1, " not in redacted
    assert [(m.line, m.kind) for m in matches] == [(2, "aws-access-key")]


def test_a_line_at_the_limit_is_kept():
    line = "y" * MAX_LINE
    assert redact(line + "\n") == (line + "\n", [])


def test_line_numbers_of_many_matches():
    text = "".join(f"x{i} = 1\npassword = \"hunter2hunter{i}\"\n" for i in range(300))
    _, matches = redact(text)
    assert [m.line for m in matches] == list(range(2, 601, 2))
