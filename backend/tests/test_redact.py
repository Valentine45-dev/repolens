from app.ingest.redact import REDACTED, redact

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
