"""Ingest the accepted evaluation repos of the reachability study at their pinned commits, with the
normal pipeline (clone, discover, parse, edges, detect, search). Nothing here reads a finding.

    uv run --project backend --env-file .env python eval/reachability_ingest.py

The repos and SHAs come from the counting run (eval/results/reachability_bandit_count-*.json). The
script refuses to run unless the pre-registration (with Amendment 1) is committed and the tier code
is the frozen commit. Run it with the API stopped or idle: it uses the same database.
"""

import glob
import json
import time

import reachability_guard
from runinfo import ROOT

from app import config, db
from app.ingest import clone, pipeline


def accepted_repos() -> list[dict]:
    latest = sorted(glob.glob(str(ROOT / "eval" / "results" / "reachability_bandit_count-*.json")))[-1]
    data = json.load(open(latest, encoding="utf-8"))
    return [r for r in data["repos"] if r.get("accepted")]


def main() -> None:
    facts = reachability_guard.check()
    print("guard ok:", facts)
    db.open_pool()
    for repo in accepted_repos():
        url = clone.normalize_repo_url(f"https://github.com/{repo['repo']}")
        sha = repo["sha"]
        with db.pool().connection() as conn, conn.transaction():
            repo_id = conn.execute(
                "INSERT INTO repos (url) VALUES (%s) ON CONFLICT ((lower(url))) DO UPDATE SET"
                " url = repos.url RETURNING id", (url,)).fetchone()["id"]
            snapshot_id = conn.execute(
                "INSERT INTO snapshots (repo_id, commit_sha) VALUES (%s, %s)"
                " ON CONFLICT (repo_id, commit_sha) DO UPDATE SET commit_sha = EXCLUDED.commit_sha"
                " RETURNING id", (repo_id, sha)).fetchone()["id"]
            latest = conn.execute(
                "SELECT status FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
            ).fetchone()
            if latest and latest["status"] == "done":
                print(repo["repo"], "already analysed, snapshot", snapshot_id)
                continue
            job_id = conn.execute(
                "INSERT INTO jobs (snapshot_id) VALUES (%s) RETURNING id", (snapshot_id,)
            ).fetchone()["id"]
        started = time.monotonic()
        print(repo["repo"], sha[:7], "snapshot", snapshot_id, "job", job_id, "starting", flush=True)
        pipeline.run_job(job_id, snapshot_id, url, sha)
        with db.pool().connection() as conn:
            row = conn.execute(
                "SELECT status, stage, error, search_state, search_error FROM snapshot_status"
                " WHERE snapshot_id = %s", (snapshot_id,)).fetchone()
        print(repo["repo"], f"{time.monotonic() - started:.0f}s", dict(row), flush=True)
    db.close_pool()
    print("ingest finished; MAX_ANALYSIS_S", config.MAX_ANALYSIS_S)


if __name__ == "__main__":
    main()
