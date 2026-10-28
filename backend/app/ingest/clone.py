"""Fetch stage: validate the URL, resolve the commit, shallow-fetch it safely.

Design section 13.3. Nothing in the clone is ever executed: hooks are disabled, submodules
and LFS content are not fetched, symlinks are checked out as plain files, and git never
prompts for credentials.
"""

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

_GITHUB_URL = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"
    r"/(?P<repo>[A-Za-z0-9._-]{1,100})/?$"
)
_SHA = re.compile(r"^[0-9a-f]{40}$")

# -c options applied to every git command.
_SAFE_CONFIG = [
    "-c", f"core.hooksPath={os.devnull}",
    "-c", "core.symlinks=false",
    "-c", "core.fsmonitor=false",
    "-c", "submodule.recurse=false",
    "-c", "credential.helper=",
    "-c", "protocol.allow=never",
    "-c", "protocol.https.allow=always",
]


class InvalidRepoUrl(ValueError):
    pass


class CloneError(RuntimeError):
    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        # True for timeouts and connection trouble, where one more try may succeed.
        self.transient = transient


# git's wording for network failures (curl and transport errors), not for missing repos.
_NETWORK_ERRORS = re.compile(
    r"could not resolve host|failed to connect|couldn't connect|connection (timed out|reset|"
    r"refused)|operation timed out|early eof|unexpected disconnect|remote end hung up|"
    r"rpc failed|ssl|gnutls|network is unreachable",
    re.IGNORECASE,
)


def normalize_repo_url(url: str) -> str:
    """Accept only https://github.com/<owner>/<repo>; return https://github.com/<owner>/<repo>
    with the capitalisation as given (GitHub names are case-insensitive, so the database matches
    repos on lower(url), and the display keeps e.g. "Valentine45-dev/JARVIS")."""
    m = _GITHUB_URL.match(url.strip())
    if not m:
        raise InvalidRepoUrl("Only https://github.com/<owner>/<repo> URLs are accepted.")
    repo = m["repo"].removesuffix(".git")
    if repo in ("", ".", ".."):
        raise InvalidRepoUrl("Only https://github.com/<owner>/<repo> URLs are accepted.")
    return f"https://github.com/{m['owner']}/{repo}"


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_LFS_SKIP_SMUDGE="1",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,  # ignore the host user's git config and credentials
    )
    env.pop("GIT_ASKPASS", None)
    env.pop("SSH_ASKPASS", None)
    return env


def _git(args: list[str], timeout: int, cwd: Path | None = None) -> str:
    try:
        proc = subprocess.run(
            ["git", *_SAFE_CONFIG, *args],
            cwd=cwd,
            env=_git_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as e:
        raise CloneError(f"git {args[0]} timed out after {timeout}s", transient=True) from e
    if proc.returncode != 0:
        detail = proc.stderr.strip().splitlines()[-1:] or ["unknown error"]
        raise CloneError(
            f"git {args[0]} failed: {detail[0][:300]}",
            transient=bool(_NETWORK_ERRORS.search(proc.stderr)),
        )
    return proc.stdout


def is_full_sha(value: str) -> bool:
    return bool(_SHA.match(value))


def resolve_sha(url: str, timeout: int) -> str:
    """Resolve the default branch's commit with `git ls-remote` (no clone)."""
    try:
        out = _git(["ls-remote", url, "HEAD"], timeout=timeout)
    except CloneError as e:
        raise CloneError("Repository not found or not public.") from e
    sha = out.split()[0] if out.strip() else ""
    if not _SHA.match(sha):
        raise CloneError("Repository not found or empty.")
    return sha


def fetch_commit(url: str, sha: str, dest: Path, timeout: int) -> None:
    """Shallow-fetch exactly `sha` into `dest` and check it out."""
    if not _SHA.match(sha):
        raise CloneError("Invalid commit SHA.")
    dest.mkdir(parents=True, exist_ok=False)
    _git(["init", "--quiet", "--template=", str(dest)], timeout=timeout)
    _git(
        ["fetch", "--quiet", "--depth", "1", "--no-tags", "--no-recurse-submodules", url, sha],
        timeout=timeout,
        cwd=dest,
    )
    _git(["checkout", "--quiet", "--detach", "FETCH_HEAD"], timeout=timeout, cwd=dest)


def remove_workspace(path: Path) -> None:
    """Delete a clone folder. Git marks pack files read-only, which Windows refuses to delete."""

    def make_writable_and_retry(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onexc=make_writable_and_retry)
