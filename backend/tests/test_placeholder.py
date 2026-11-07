"""The placeholder classifier: clear stand-ins are marked, weak real credentials are not."""

import pytest

from app.ingest.redact import placeholder_pattern, redact

# Values assembled at runtime where they look like real credential formats.
AWS_DOC = "AKIA" + "IOSFODNN7" + "EXAMPLE"


@pytest.mark.parametrize(
    "value, pattern",
    [
        ("<your-api-key>", "template"),
        ("${API_KEY}", "template"),
        ("$API_KEY", "template"),
        ("{{ token }}", "template"),
        ("%(password)s", "template"),
        ("your-secret-key", "your-or-here"),
        ("YOUR_API_KEY_HERE", "your-or-here"),
        ("insert-token-here", "your-or-here"),
        ("paste_key_here", "your-or-here"),
        ("changeme", "marker-word"),
        ("CHANGE_ME_please", "marker-word"),
        ("replace-me-now", "marker-word"),
        ("placeholder-token", "marker-word"),
        ("dummy-password", "marker-word"),
        ("fake_secret_key", "marker-word"),
        (AWS_DOC, "marker-word"),
        ("xxxxxx", "repeated-char"),
        ("xxxx-xxxx-xxxx", "mask"),
        ("******", "repeated-char"),
        ("aaaaaaaa", "repeated-char"),
        ("000000", "repeated-char"),
        ("sk_test_" + "4eC39HqLyjWDarjtT1zdp7dc", "vendor-doc"),
    ],
)
def test_placeholders_are_recognised(value, pattern):
    assert placeholder_pattern(value) == pattern


@pytest.mark.parametrize(
    "value",
    [
        "admin", "admin123", "password", "password123", "secret", "123456", "hunter2pass",
        "mysecretkey", "dev-secret-key", "s3cr3t", "abc123def456", "letmein", "qwerty123",
        "putty1234", "entertain", "abababab", "aaaaab", "correct-horse-battery-staple",
    ],
)
def test_weak_real_passwords_are_not_placeholders(value):
    assert placeholder_pattern(value) is None


def test_redact_marks_placeholder_and_keeps_the_value_out():
    text = 'API_KEY = "changeme-please"\nPASSWORD = "admin123"\nTOKEN = "<your-token-here>"\n'
    redacted, matches = redact(text)
    assert "changeme" not in redacted and "admin123" not in redacted
    assert [(m.line, m.placeholder is not None) for m in matches] == [
        (1, True), (2, False), (3, True),
    ]
    # SecretMatch carries the pattern's name, never the value.
    assert all("changeme" not in repr(m) and "admin123" not in repr(m) for m in matches)
