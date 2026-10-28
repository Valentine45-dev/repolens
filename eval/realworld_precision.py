"""Real-world precision on one public repo: RepoLens vs Bandit, by hand-labelled random samples.

    uv run --project backend --env-file .env python eval/realworld_precision.py \\
        --url https://github.com/adeyosemanputra/pygoat

Fixed before any run (28 Oct):
- The repo is analysed at its current commit (SHA recorded) by the normal pipeline: shallow
  clone with hooks off, parse only, workspace deleted. Nothing from the repo is executed.
- Bandit (pinned, all tests, default settings) runs on a second clone made the same way,
  only on the Python files RepoLens kept, then that clone is deleted. Bandit parses, never runs.
- Each tool's full default output is the population (no filtering by rule or severity; test
  code included). From each, up to N findings are drawn with random.Random(SEED), applied to
  the findings sorted by (path, line, rule), independently per tool.
- Labels, given by hand after this script ran and confirmed by the project owner before any
  number is computed:
    real issue  = the flagged line is a genuine instance of the weakness the rule names, in this
                  code's context (PyGoat's deliberate vulnerabilities count as real);
    false alarm = it is not (constant input, test-only assert, placeholder value, unrelated).
- Precision = real / labelled, per tool. Recall is not measured: there is no full answer key.

Code lines are shown from RepoLens's stored (redacted) file text, so no secret value is printed.
Output: eval/results/realworld_precision-<time>-<sha7>.json with labels left empty.
"""

import argparse
import json
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from runinfo import header, run_info, save_results  # also puts backend/ on sys.path

from app import config, db  # noqa: E402
from app.ingest import clone, pipeline  # noqa: E402

BANDIT = "bandit==1.9.4"
SEED = 20261028
N = 20


def snapshot_for(url: str) -> tuple[int, str]:
    """Analyse `url` at its current commit (or reuse a done analysis of that commit)."""
    url = clone.normalize_repo_url(url)
    sha = clone.resolve_sha(url, timeout=config.CLONE_TIMEOUT_S)
    with db.pool().connection() as conn, conn.transaction():
        repo_id = conn.execute(
            "INSERT INTO repos (url) VALUES (%s)"
            " ON CONFLICT (url) DO UPDATE SET url = EXCLUDED.url RETURNING id", (url,),
        ).fetchone()["id"]
        snapshot_id = conn.execute(
            "INSERT INTO snapshots (repo_id, commit_sha) VALUES (%s, %s)"
            " ON CONFLICT (repo_id, commit_sha) DO UPDATE SET commit_sha = EXCLUDED.commit_sha"
            " RETURNING id", (repo_id, sha),
        ).fetchone()["id"]
        latest = conn.execute("SELECT status FROM snapshot_status WHERE snapshot_id = %s",
                              (snapshot_id,)).fetchone()
        job_id = None
        if not (latest and latest["status"] == "done"):
            job_id = conn.execute("INSERT INTO jobs (snapshot_id) VALUES (%s) RETURNING id",
                                  (snapshot_id,)).fetchone()["id"]
    if job_id:
        pipeline.run_job(job_id, snapshot_id, url, sha)
    with db.pool().connection() as conn:
        st = conn.execute("SELECT status, error FROM snapshot_status WHERE snapshot_id = %s",
                          (snapshot_id,)).fetchone()
    if st["status"] != "done":
        raise SystemExit(f"analysis failed: {st['error']}")
    return snapshot_id, sha


def stored_files(snapshot_id: int) -> dict[str, dict]:
    with db.pool().connection() as conn:
        rows = conn.execute("SELECT path, language, content FROM files WHERE snapshot_id = %s",
                            (snapshot_id,)).fetchall()
    return {r["path"]: r for r in rows}


def repolens_findings(snapshot_id: int) -> list[dict]:
    with db.pool().connection() as conn:
        rows = conn.execute(
            "SELECT f.path, x.line, x.rule_id, x.severity, x.message, x.in_test"
            " FROM findings x JOIN files f ON f.id = x.file_id WHERE x.snapshot_id = %s",
            (snapshot_id,),
        ).fetchall()
    return [{"path": r["path"], "line": r["line"], "rule": r["rule_id"],
             "severity": r["severity"], "message": r["message"], "in_test": r["in_test"]}
            for r in rows]


def bandit_findings(url: str, sha: str, py_paths: list[str]) -> tuple[list[dict], dict]:
    work = Path(tempfile.mkdtemp(prefix="repolens-bandit-"))
    try:
        repo = work / "repo"
        clone.fetch_commit(url, sha, repo, timeout=config.CLONE_TIMEOUT_S)
        out = subprocess.run(
            ["uvx", "--from", BANDIT, "bandit", "-f", "json", "-q",
             *[str(repo / p) for p in py_paths]],
            capture_output=True, text=True, encoding="utf-8",
        )
        data = json.loads(out.stdout)
        found = [{"path": Path(r["filename"]).resolve().relative_to(repo.resolve()).as_posix(),
                  "line": r["line_number"], "rule": f"{r['test_id']} {r['test_name']}",
                  "severity": r["issue_severity"].lower(),
                  "confidence": r["issue_confidence"].lower(), "message": r["issue_text"]}
                 for r in data["results"]]
        errors = [{"path": Path(e["filename"]).name, "reason": e["reason"][:200]}
                  for e in data.get("errors", [])]
        return found, {"errors": errors}
    finally:
        clone.remove_workspace(work)
        shutil.rmtree(work, ignore_errors=True)


def draw(findings: list[dict], files: dict[str, dict]) -> list[dict]:
    ordered = sorted(findings, key=lambda f: (f["path"], f["line"] or 0, f["rule"]))
    picked = random.Random(SEED).sample(ordered, min(N, len(ordered)))
    for f in picked:
        lines = (files.get(f["path"], {}).get("content") or "").split("\n")
        i = (f["line"] or 1) - 1
        f["code"] = lines[i].strip()[:200] if 0 <= i < len(lines) else ""
        f["label"] = None
        f["reason"] = None
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", required=True)
    args = parser.parse_args()

    db.open_pool()
    snapshot_id, sha = snapshot_for(args.url)
    files = stored_files(snapshot_id)
    py_paths = sorted(p for p, f in files.items() if f["language"] == "python")
    rl = repolens_findings(snapshot_id)
    bd, bandit_meta = bandit_findings(clone.normalize_repo_url(args.url), sha, py_paths)

    info = run_info(llm_used=False)
    print(header(info))
    print(f"{args.url} @ {sha} | {len(files)} files kept, {len(py_paths)} Python")
    print(f"RepoLens {len(rl)} findings | Bandit {len(bd)} findings"
          f" ({len(bandit_meta['errors'])} files Bandit could not parse) | seed {SEED}, n {N}")

    samples = {"RepoLens": draw(rl, files), "Bandit": draw(bd, files)}
    for tool, picked in samples.items():
        print(f"\n== {tool} sample ({len(picked)})")
        for k, f in enumerate(picked, 1):
            print(f"{k:>2}. {f['path']}:{f['line']} [{f['rule']}] {f['code']}")

    def by_rule(found):
        counts: dict[str, int] = {}
        for f in found:
            counts[f["rule"]] = counts.get(f["rule"], 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    results = {
        "repo": {"url": clone.normalize_repo_url(args.url), "commit": sha,
                 "snapshot_id": snapshot_id, "files_kept": len(files),
                 "python_files": len(py_paths)},
        "tools": {"repolens": "this commit", "bandit": BANDIT},
        "sampling": {"seed": SEED, "n": N, "order": "path, line, rule"},
        "population": {"RepoLens": {"total": len(rl), "by_rule": by_rule(rl)},
                       "Bandit": {"total": len(bd), "by_rule": by_rule(bd), **bandit_meta}},
        "samples": samples,
        "labels_confirmed": False,
    }
    print("\nsaved", save_results("realworld_precision", info, results))


if __name__ == "__main__":
    main()
