"""Scorer self-check: the files listed in eval/locked/scorer.sha256 against the working tree.

    uv run --project backend python eval/scorer_selfcheck.py

Exit 1 if a scoring file (locked_metrics.py, score_claims.py) differs from the freeze. A changed
runner (locked_eval.py) is reported but allowed: v2.1 adds retrieval configurations to it and a
locked run then needs --runner-changed. Uses the runner's own check, so the rule is the same.
"""

import sys

import locked_eval as le

bad, runner_changed = le.manifest_problems(le.read_manifest(le.MANIFEST))
print("scoring files differ from the freeze:", ", ".join(bad) if bad else "none")
print("runner (eval/locked_eval.py) changed:", runner_changed)
sys.exit(1 if bad else 0)
