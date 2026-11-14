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


# --- coverage (review S-03): what must and must not be redacted ---------------------------------
_K = "PRIVATE " + "KEY-----"
_AKIA = "AKIA" + "ABCDEFGHIJKLMNOP"
MUST_REDACT = [  # (id, text, config, a fragment of the secret that must be gone)
    ("py annotated", 'password: str = "hunter2-Real-Pass"\n', False, "hunter2"),
    ("ts annotated", 'const apiKey: string = "abcd1234efgh5678";\n', False, "abcd1234"),
    ("Optional annotation", 'token: Optional[str] = "tok-Real-9876"\n', False, "tok-Real"),
    ("bytes prefix", "SECRET_KEY = b'0123456789abcdef-real'\n", False, "0123456789"),
    ("raw prefix", 'SECRET_KEY = r"0123456789abcdef-real"\n', False, "0123456789"),
    ("u prefix", "api_key = u'abcdef123456'\n", False, "abcdef123456"),
    ("rb prefix", "secret = rb'abcdef123456'\n", False, "abcdef123456"),
    ("f-string with a literal", 'token = f"tok_{env}_abcdef123456"\n', False, "abcdef123456"),
    ("value with spaces", 'password = "correct horse battery staple"\n', False, "horse"),
    ("other quote inside", 'password = "it\'s-my-pass-123"\n', False, "my-pass"),
    ("escaped quote inside", 'password = "ab\\"cdef-123"\n', False, "cdef"),
    ("subscript", 'config["password"] = "hunter2-Real-Pass"\n', False, "hunter2"),
    ("flask config", "app.config['SECRET_KEY'] = 'dev-real-key-123'\n", False, "dev-real"),
    ("environ subscript", 'os.environ["API_KEY"] = "abc123xyz789"\n', False, "abc123"),
    ("attribute", 'settings.SECRET_KEY = "abc123xyz789"\n', False, "abc123"),
    ("DB_PASS", 'DB_PASS = "hunter2-Real-Pass"\n', False, "hunter2"),
    ("dbPass", 'const dbPass = "hunter2-Real-Pass";\n', False, "hunter2"),
    ("passphrase", 'passphrase = "hunter2-Real-Pass"\n', False, "hunter2"),
    ("credentials", 'credentials = "user:hunter2-Real"\n', False, "hunter2"),
    ("powershell env", '$env:FLASK_SECRET_KEY = "abc123xyz789"\n', False, "abc123"),
    ("nested in a string", 'body = b\'{"status": "ok", "token": "abc123def456"}\'\n', False,
     "abc123def456"),
    ("json value on the next line", '{"password":\n  "hunter2hunter2"}\n', False, "hunter2"),
    ("yaml value starting with $", "DB_PASSWORD: $ecretPass99\n", True, "ecretPass99"),
    ("yaml value starting with !", "db_password: !Passw0rd2026\n", True, "Passw0rd"),
    ("overlap tail", f'api_key = "{_AKIA}+tailSECRETpart"\n', False, "tailSECRET"),
    ("key without END",
     f"-----BEGIN RSA {_K}\nMIIEowIBAAKCAQEAabcdefgh\nqrstuvwxyz0123456789ABCD\n", False, "MIIEow"),
    ("key without END, escaped newlines", f'"-----BEGIN {_K}\\nMIIEvQIBADANBgkqhkiG9w0B\\nab"\n',
     False, "MIIEvQ"),
    ("PGP key block", "-----BEGIN PGP PRIVATE KEY BLOCK-----\nlQOYBGXabcdefghijklmnopq\n"
     "-----END PGP PRIVATE KEY BLOCK-----\n", False, "lQOYBG"),
    # shapes that worked before and must keep working
    ("config unquoted", "password = hunter2pass\n", True, "hunter2pass"),
    ("json", '"password": "hunter2hunter2"\n', False, "hunter2"),
    ("keyword argument", 'connect(password="hunter2hunter2")\n', False, "hunter2"),
    ("url", "DSN = 'postgres://app:s3cretpw@db/app'\n", False, "s3cretpw"),
    ("cli flag", 'mysql --password="hunter2hunter2"\n', False, "hunter2"),
    ("keyword inside a word", 'adminpassword = "hunter2hunter2"\n', False, "hunter2"),
    ("template value in code", 'API_KEY = "${API_KEY}"\n', False, "${API_KEY}"),
    ("mask value", 'password = "********"\n', False, "********"),
    ("key with END", f"K = '''-----BEGIN RSA {_K}\nMIIEowIBAAKCAQEA\n-----END RSA {_K}'''\n",
     False, "MIIEow"),
]
MUST_NOT_REDACT = [  # (id, text, config)
    ("descriptor field", 'password_field = "password"\n', False),
    ("min length", "PASSWORD_MIN_LENGTH = 8\n", False),
    ("getter", "password = get_password()\n", False),
    ("docs prose", 'Set `password = "your password here"` in the config.\n', False),
    ("error message", 'INVALID_PASSWORD = "Invalid password, try again."\n', False),
    ("help text", 'password_help_text = "Your password must contain 8 characters"\n', False),
    ("token url", 'TOKEN_URL = "https://auth.example.com/oauth/token"\n', False),
    ("token uri", '"token_uri": "https://oauth2.googleapis.com/token",\n', False),
    ("api key url", 'APIKEY_URL = "https://secure.example.com/apikey"\n', False),
    ("password env", 'password_env = "DB_PASSWORD"\n', False),
    ("secret file", 'SECRET_KEY_FILE = "/run/secrets/django_key"\n', False),
    ("password title", 'password_title = "Password"\n', False),
    ("secret placeholder constant", 'SECRET_PLACEHOLDER = "--------"\n', False),
    ("token type", 'jsonify(token_type="Bearer", expires_in=300)\n', False),
    ("token name", 'self.token_name = "api-token"\n', False),
    ("tokenizer", 'tokenizer_name = "bert-base-uncased"\n', False),
    ("secretary", 'secretary_email = "office@example.com"\n', False),
    ("bypass", 'bypass_mode = "always-allow"\n', False),
    ("compass", 'compass_dir = "north-east"\n', False),
    ("passenger", 'passenger_name = "Jane Doe"\n', False),
    ("keyword in an earlier segment", 'send_password_mock.return_value = "sent-ok"\n', False),
    ("constant name for a short keyword", 'PASS = "PASS_THROUGH"\n', False),
    ("comparison", 'if password == "hunter2hunter2":\n', False),
    ("short value", 'password = "abc"\n', False),
    ("streamed word", 'data: {"token": "Gunicorn\'s "}\n', False),
    ("leading space", 'data: {"token": " world"}\n', False),
    ("punctuation table", 'RFC_TOKEN_SPECIALS = r"!#$%&\'*+-.^_`|~"\n', False),
    ("github actions expression", 'password: "${{ secrets.DOCKER_PASSWORD }}"\n', False),
    ("github actions expression, unquoted", "token: ${{secrets.ANACONDA_TOKEN}}\n", True),
    ("fstring placeholder", 'sql = f"SELECT * FROM u WHERE password=\'{password}\'"\n', False),
    ("placeholder dict", 'creds = {"password": "{user}{pw}"}\n', False),
    ("config tag with an argument", "password: !secret db_password\n", True),
    ("config lower-case tag", "secret: !vault_lookup\n", True),
    ("config $VAR", "password: $DB_PASSWORD\n", True),
    ("markdown prose", "The token: it expires after one hour.\n", False),
]


@pytest.mark.parametrize("case", MUST_REDACT, ids=[c[0] for c in MUST_REDACT])
def test_must_redact(case):
    _, text, config, fragment = case
    redacted, matches = redact(text, config=config)
    assert fragment not in redacted
    assert redacted.count("\n") == text.count("\n")
    assert matches


@pytest.mark.parametrize("case", MUST_NOT_REDACT, ids=[c[0] for c in MUST_NOT_REDACT])
def test_must_not_redact(case):
    _, text, config = case
    assert redact(text, config=config) == (text, [])


def test_overlap_is_redacted_as_one_span_of_the_specific_kind():
    redacted, matches = redact(f'api_key = "{_AKIA}+tailSECRETpart"\n')
    assert redacted == f'api_key = "{REDACTED}"\n'
    assert [m.kind for m in matches] == ["aws-access-key"]
