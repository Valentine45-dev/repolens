"""The Ruff runner: isolated, repo comments cannot silence it, a failure is reported not hidden."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.detect import ruff as ruff_module
from app.detect.ruff import MAX_PER_FILE, RuffError, run_ruff
from app.detect.rules import RULES
from app.subproc import run_bounded

SOURCE = """\
def f(items=[]):
    return undefined_name  # noqa: F821


x = 1
x == 2
"""


def test_findings_use_catalogued_rules_and_real_line_numbers():
    hits = run_ruff({"pkg/m.py": SOURCE})
    assert {(h.line, h.rule_id) for h in hits} == {
        (1, "ruff-B006"), (2, "ruff-F821"), (6, "ruff-B015"),
    }
    assert all(h.rule_id in RULES and RULES[h.rule_id].category == "quality" for h in hits)
    assert {h.path for h in hits} == {"pkg/m.py"}
    assert "undefined_name" in next(h.message for h in hits if h.rule_id == "ruff-F821")


def test_noqa_comments_in_the_repository_do_not_silence_rules():
    # line 2 carries `# noqa: F821` and is still reported (see the test above); a blanket one too
    hits = run_ruff({"a.py": "y = zzz  # noqa\n# ruff: noqa\nw = qqq\n"})
    assert {h.line for h in hits} == {1, 3}


def test_only_selected_rules_run():
    # unused import (F401), line length (E501) and a missing docstring are not selected
    assert run_ruff({"a.py": "import os\n" + "z = '" + "x" * 200 + "'\n"}) == []


def test_bare_raise_in_a_helper_is_not_reported():
    # PLE0704 is switched off: flask re-raises the active exception from such helpers on purpose
    source = "def helper(e):\n    if e is None:\n        raise\n    raise e\n"
    assert run_ruff({"a.py": source}) == []


def test_syntax_errors_and_non_python_files_are_ignored():
    assert run_ruff({"bad.py": "def g(:\n", "notes.md": "x == 1\n", "a.js": "x == 1;"}) == []


def test_no_files_runs_nothing(monkeypatch):
    monkeypatch.setattr(ruff_module, "run_bounded", lambda *a, **k: pytest.fail("ran ruff"))
    assert run_ruff({}) == []


def test_paths_that_climb_out_of_the_copy_are_not_written(tmp_path):
    hits = run_ruff({"../../escaped.py": "x = nope\n", "ok.py": "y = nope2\n"})
    assert {h.path for h in hits} == {"ok.py"}


def test_a_file_is_capped():
    source = "\n".join(f"v{i} = missing{i}" for i in range(MAX_PER_FILE + 30)) + "\n"
    assert len(run_ruff({"gen.py": source})) == MAX_PER_FILE


def test_timeout_is_reported_not_hidden():
    with pytest.raises(RuffError, match="timed out"):
        run_ruff({"a.py": "x = 1\n"}, timeout=0.001)


SECRETS_IN_API_ENV = {
    "LLM_API_KEY": "sk-not-a-real-key", "DATABASE_URL": "postgresql://u:pw@db/repolens",
    "TEST_DATABASE_URL": "postgresql://u:pw@db/repolens_test",
    "HTTPS_PROXY": "http://user:proxypw@proxy.invalid:3128",
    "HTTP_PROXY": "http://user:proxypw@proxy.invalid:3128", "RUFF_CONFIG": "evil.toml",
    "PYTHONPATH": "/somewhere", "GIT_ASKPASS": "/bin/evil",
}


def _capture_command(monkeypatch) -> dict:
    seen = {}

    def fake_run(cmd, *, cwd, env, timeout):
        seen.update(cmd=cmd, cwd=Path(cwd), env=env, cwd_listing=sorted(os.listdir(cwd)))
        raise subprocess.TimeoutExpired(cmd, 1)

    for name, value in SECRETS_IN_API_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(ruff_module, "run_bounded", fake_run)
    with pytest.raises(RuffError, match="timed out"):
        run_ruff({"pkg/a.py": "x = 1\n"})
    return seen


def test_command_is_isolated_and_cannot_fix_or_cache(monkeypatch):
    seen = _capture_command(monkeypatch)
    for flag in ("--isolated", "--no-cache", "--no-fix", "--ignore-noqa", "--ignore"):
        assert flag in seen["cmd"]


def test_the_ruff_binary_is_run_directly_from_an_empty_directory(monkeypatch):
    seen = _capture_command(monkeypatch)
    cmd = seen["cmd"]
    assert cmd[0] == ruff_module.ruff_binary() and Path(cmd[0]).is_file()
    assert Path(cmd[0]).stem.lower() == "ruff"  # never the Python interpreter
    assert "-m" not in cmd
    src = Path(cmd[-1])
    assert cmd[-2] == "--" and src.is_absolute()
    assert seen["cwd"] != src and not seen["cwd"].is_relative_to(src)
    assert seen["cwd_listing"] == []  # nothing for anything to pick up from the working directory


def test_child_environment_is_the_allowlist(monkeypatch):
    seen = _capture_command(monkeypatch)
    assert seen["env"] == {k: os.environ[k] for k in ruff_module.ENV_ALLOWLIST if k in os.environ}
    assert not set(seen["env"]) & set(SECRETS_IN_API_ENV)


# Every module name a planted file could take over under `python -m ruff` (review S-01, measured
# in the security batch: the launcher's imports on Windows and Linux), plus Ruff itself.
SHADOWING_FILES = [
    "ruff.py", "ruff/__init__.py", "ruff/__main__.py", "subprocess.py", "__future__.py",
    "fnmatch.py", "importlib.py", "sysconfig.py", "types.py",
    "_sysconfigdata__linux_x86_64-linux-gnu.py",
]


def test_repository_files_are_never_executed(tmp_path):
    marker_dir = tmp_path / "markers"
    marker_dir.mkdir()
    files = {
        path: (f"open({str(marker_dir / path.replace('/', '_'))!r} + '.marker', 'w').close()\n"
               "print('[]')\n")
        for path in SHADOWING_FILES
    }
    files["app.py"] = "x = undefined_name\n"
    hits = run_ruff(files)
    assert sorted(p.name for p in marker_dir.iterdir()) == []
    assert ("app.py", 1, "ruff-F821") in {(h.path, h.line, h.rule_id) for h in hits}


def test_copy_errors_become_the_did_not_run_note(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("path too long")

    monkeypatch.setattr(ruff_module.Path, "write_text", fail)
    with pytest.raises(RuffError, match="did not run"):
        run_ruff({"a.py": "x = 1\n"})


def test_a_missing_ruff_binary_is_reported_not_raised(monkeypatch):
    def missing():
        raise FileNotFoundError("no ruff")

    monkeypatch.setattr(ruff_module, "ruff_binary", missing)
    with pytest.raises(RuffError, match="could not be started"):
        run_ruff({"a.py": "x = 1\n"})


GRANDCHILD = """
import sys, time
path = sys.argv[1]
for i in range(600):
    with open(path, "w") as f:
        f.write(str(i))
    time.sleep(0.05)
"""
PARENT = """
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2]])  # inherits stdout/stderr
time.sleep(30)
"""


def test_timeout_kills_the_whole_process_tree(tmp_path):
    # The grandchild holds the output pipe: plain subprocess.run(timeout=...) would wait for it
    # on Windows and leave it running on Linux (review S-05).
    beat = tmp_path / "heartbeat"
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded([sys.executable, "-c", PARENT, GRANDCHILD, str(beat)], cwd=tmp_path,
                    env=dict(os.environ), timeout=2)
    assert time.monotonic() - started < 15
    assert beat.exists()  # the grandchild did start
    time.sleep(0.5)
    first = beat.read_text()
    time.sleep(1)
    assert beat.read_text() == first, "the grandchild is still running"
