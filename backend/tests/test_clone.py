import os

import pytest

from app.ingest.clone import (
    CloneError,
    InvalidRepoUrl,
    fetch_commit,
    normalize_repo_url,
    remove_workspace,
    resolve_sha,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/pallets/itsdangerous", "https://github.com/pallets/itsdangerous"),
        ("https://github.com/Pallets/ItsDangerous/", "https://github.com/pallets/itsdangerous"),
        ("https://github.com/psf/requests.git", "https://github.com/psf/requests"),
        ("  https://github.com/a-b/c.d_e  ", "https://github.com/a-b/c.d_e"),
    ],
)
def test_normalize_accepts_github_repo_urls(url, expected):
    assert normalize_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://gitlab.com/a/b",
        "https://github.com.evil.com/a/b",
        "https://user:pw@github.com/a/b",
        "https://github.com/a",
        "https://github.com/a/b/tree/main",
        "https://github.com/a/b?x=1",
        "https://github.com/a/..",
        "https://github.com/-a/b",
        "git@github.com:a/b.git",
        "file:///etc/passwd",
        "https://localhost/a/b",
    ],
)
def test_normalize_rejects_everything_else(url):
    with pytest.raises(InvalidRepoUrl):
        normalize_repo_url(url)


def test_fetch_rejects_bad_sha(tmp_path):
    with pytest.raises(CloneError):
        fetch_commit("https://github.com/a/b", "main", tmp_path / "x", timeout=5)


@pytest.mark.skipif(not os.environ.get("RUN_NETWORK_TESTS"), reason="set RUN_NETWORK_TESTS=1")
def test_resolve_and_fetch_real_repo(tmp_path):
    url = "https://github.com/pallets/itsdangerous"
    sha = resolve_sha(url, timeout=60)
    dest = tmp_path / "clone"
    try:
        fetch_commit(url, sha, dest, timeout=120)
        assert (dest / "src" / "itsdangerous" / "__init__.py").exists()
        # --template= means no sample hooks are copied into the clone.
        assert not list((dest / ".git").glob("hooks/*"))
    finally:
        remove_workspace(dest)
    assert not dest.exists()


@pytest.mark.skipif(not os.environ.get("RUN_NETWORK_TESTS"), reason="set RUN_NETWORK_TESTS=1")
def test_resolve_missing_repo_fails_fast():
    with pytest.raises(CloneError):
        resolve_sha("https://github.com/this-owner-does-not-exist-xyz/nope", timeout=30)
