"""Checks shared by the evaluation scripts of the reachability study: the pre-registration (with its
amendment) is committed and unchanged, and the tier code is exactly the frozen commit."""

import subprocess

from runinfo import ROOT

FROZEN_TIER_COMMIT = "cfd4835dc50b5497a189ca34ca410df19767bc52"  # amendment 1, section 13.1
TIER_CODE_PATHS = ["backend/app/reach", "backend/app/api/reach.py", "docs/reachability-design.md"]
PREREG = "eval/reachability_prereg.md"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def check() -> dict:
    """Raises SystemExit unless the study's fixed inputs are as pre-registered. Returns facts to
    record in the result file."""
    if _git("status", "--porcelain", "--", PREREG).stdout.strip():
        raise SystemExit(f"{PREREG} differs from the committed version.")
    if "Amendment 1" not in (ROOT / PREREG).read_text(encoding="utf-8"):
        raise SystemExit("The pre-registration has no Amendment 1.")
    if _git("merge-base", "--is-ancestor", FROZEN_TIER_COMMIT, "HEAD").returncode != 0:
        raise SystemExit("The frozen tier commit is not an ancestor of HEAD.")
    if _git("diff", "--quiet", FROZEN_TIER_COMMIT, "HEAD", "--", *TIER_CODE_PATHS).returncode != 0:
        raise SystemExit("The tier code differs from the frozen commit.")
    return {
        "frozen_tier_commit": FROZEN_TIER_COMMIT,
        "prereg_commit": _git("log", "-1", "--format=%H", "--", PREREG).stdout.strip(),
        "head": _git("rev-parse", "HEAD").stdout.strip(),
    }
