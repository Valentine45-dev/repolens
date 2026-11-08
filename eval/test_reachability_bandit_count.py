"""Checks for the Bandit counting script (run before the counting run, pre-registration section 6):
repo config and `# nosec` cannot change the count, B101/B404 are skipped, B603 is not, and tests and
docs are left out.

    uv run --project backend python -m pytest -q -p no:cacheprovider eval/test_reachability_bandit_count.py
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402
from reachability_bandit_count import BANDIT, count_dir, eligible_path, run_bandit  # noqa: E402

MODULE = """\
import subprocess


def f(x):
    assert x
    eval(x)  # nosec
    subprocess.call(x)
    subprocess.call("ls", shell=True)
"""


@pytest.fixture
def seeded_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "docs").mkdir()
    (repo / "pkg" / "mod.py").write_text(MODULE)
    (repo / "tests" / "test_a.py").write_text("def test_it(x):\n    eval(x)\n")
    (repo / "docs" / "conf.py").write_text("def g(x):\n    eval(x)\n")
    # every config file Bandit could read, all trying to switch everything off
    (repo / ".bandit").write_text("[bandit]\nexclude = /pkg\nskips = B307,B602,B603\n")
    (repo / "pyproject.toml").write_text('[tool.bandit]\nexclude_dirs = ["pkg"]\nskips = ["B307", "B602", "B603"]\n')
    (repo / "setup.cfg").write_text("[bandit]\nskips = B307,B602,B603\n")
    (repo / "tox.ini").write_text("[bandit]\nskips = B307,B602,B603\n")
    return repo


def test_repo_config_and_nosec_do_not_change_the_count(seeded_repo):
    result = count_dir(seeded_repo)
    assert result["python_files_scanned"] == 1  # tests/ and docs/ left out
    # eval (nosec ignored), shell=True, a call with a variable, and the partial path "ls" (B607)
    assert result["by_test_id"] == {"B307": 1, "B602": 1, "B603": 1, "B607": 1}
    assert result["total"] == 4


def test_assert_and_subprocess_import_are_skipped_but_calls_are_not():
    found, errors = run_bandit({"m.py": MODULE})
    ids = {f["test_id"] for f in found}
    assert not ids & {"B101", "B404"}
    assert "B603" in ids
    assert errors == 0


def test_control_bandit_does_honour_nosec_without_the_flag(seeded_repo):
    # without --ignore-nosec the `# nosec` line is silenced: the flag is what makes the difference
    out = subprocess.run(["uvx", "--from", BANDIT, "bandit", "-r", str(seeded_repo / "pkg"),
                          "-f", "json", "-q", "--exit-zero"], capture_output=True, text=True,
                         encoding="utf-8").stdout
    assert '"B307"' not in out


def test_eligible_paths():
    assert eligible_path("pkg/mod.py")
    for bad in ("tests/test_a.py", "pkg/tests/x.py", "pkg/test_x.py", "pkg/conftest.py",
                "examples/run.py", "docs/conf.py", "src/doc/conf.py"):
        assert not eligible_path(bad), bad
