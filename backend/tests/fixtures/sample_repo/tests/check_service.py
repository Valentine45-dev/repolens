"""Test-like file for the exclude_tests graph filter. Named so pytest never collects it."""

from sample_app.service import create_user


def check_create_user():
    return create_user("a", "a@example.com")
