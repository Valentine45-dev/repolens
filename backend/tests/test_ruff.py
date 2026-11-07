"""The Ruff runner: isolated, repo comments cannot silence it, a failure is reported not hidden."""

import pytest

from app.detect import ruff as ruff_module
from app.detect.ruff import MAX_PER_FILE, RuffError, run_ruff
from app.detect.rules import RULES

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


def test_syntax_errors_and_non_python_files_are_ignored():
    assert run_ruff({"bad.py": "def g(:\n", "notes.md": "x == 1\n", "a.js": "x == 1;"}) == []


def test_no_files_runs_nothing(monkeypatch):
    monkeypatch.setattr(ruff_module.subprocess, "run", lambda *a, **k: pytest.fail("ran ruff"))
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


def test_command_is_isolated_and_cannot_fix_or_cache(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["env"] = cmd, kwargs["env"]
        raise ruff_module.subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setenv("RUFF_CONFIG", "evil.toml")
    monkeypatch.setattr(ruff_module.subprocess, "run", fake_run)
    with pytest.raises(RuffError):
        run_ruff({"a.py": "x = 1\n"})
    for flag in ("--isolated", "--no-cache", "--no-fix", "--ignore-noqa"):
        assert flag in seen["cmd"]
    assert not any(k.startswith("RUFF") for k in seen["env"])
