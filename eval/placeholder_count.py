"""Count how many secret matches the placeholder classifier would flag, per pattern, on pinned
commits of the local test repos. Throwaway-style: clones into a temp folder (deleted afterwards),
writes nothing to any database, and prints COUNTS ONLY. No secret value is printed or saved.

usage (cwd = backend/): uv run python ../eval/placeholder_count.py <out.json>
"""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, ".")
from app.ingest.clone import fetch_commit, remove_workspace  # noqa: E402
from app.ingest.discover import discover  # noqa: E402
from app.paths import is_doc_path, is_nonrunning_path, is_test_path  # noqa: E402

REPOS = [
    ("https://github.com/pallets/itsdangerous", "672971d"),
    ("https://github.com/adeyosemanputra/pygoat", "46fef96"),
    ("https://github.com/expressjs/express", "1c6f1b0"),
    ("https://github.com/pallets/flask", "49943b5"),
    ("https://github.com/psf/black", "b4f1fca"),
]

result = {}
for url, short in REPOS:
    tmp = Path(tempfile.mkdtemp(prefix="repolens-count-"))
    try:
        from app import db  # noqa: E402

        db.open_pool()
        with db.pool().connection() as conn:
            row = conn.execute(
                "SELECT s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
                " WHERE lower(r.url) = lower(%s) AND s.commit_sha LIKE %s",
                (url, short + "%"),
            ).fetchone()
        sha = row["commit_sha"]
        fetch_commit(url, sha, tmp / "w", 120)
        found = discover(tmp / "w", 2000, 1_000_000)
    finally:
        remove_workspace(tmp)
    by_pattern: Counter = Counter()
    by_pattern_split: Counter = Counter()
    total = 0
    for f in found.files:
        for s in f.secrets:
            total += 1
            by_pattern[s.placeholder or "(not a placeholder)"] += 1
            place = "doc" if is_doc_path(f.path) else "test" if is_test_path(f.path) else "other"
            if s.placeholder is None:
                outcome = "not a placeholder"
            elif is_nonrunning_path(f.path):
                outcome = "placeholder, demoted to low (docs / example file)"
            else:
                outcome = "template value, severity kept (code / runtime config)"
            by_pattern_split[f"{place}: {outcome}"] += 1
    result[url.split("github.com/")[1] + "@" + short] = {
        "secret_matches": total,
        "by_pattern": dict(by_pattern),
        "by_location_and_class": dict(by_pattern_split),
    }
    print(url.split("github.com/")[1], total, dict(by_pattern), dict(by_pattern_split))
json.dump(result, open(sys.argv[1], "w"), indent=1, sort_keys=True)
