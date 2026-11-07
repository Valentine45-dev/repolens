"""Count non-test Bandit findings on the fixed pool of Python repos (pre-registration section 6).

    uv run --project backend --env-file .env python eval/reachability_bandit_count.py

Counting only: no tier code, no sample, no labels. For each repo, in the pool's order, until four are
accepted or the pool is exhausted:
- skip it if it is in eval/results/reachability_exclusions.txt;
- resolve the default branch HEAD (the pinned SHA), shallow-clone it as CLAUDE.md requires, run the
  discover stage with the pipeline's limits (skip the repo if it hits the file limit);
- keep the Python files that are not test/example files and not under docs/ or doc/, write them as
  discover stores them (redacted) into a temporary directory, and run Bandit there, so no config of
  the repo can be found: `bandit -r <copy> -f json -q --ignore-nosec --exit-zero --skip B101,B404`;
- accept the repo if it has at least 40 findings.
Bandit parses files and never runs them. Only counts are kept: no snippets, no file text.
The script refuses to run if eval/reachability_prereg.md differs from the committed version.
"""

import argparse
import json
import os
import subprocess
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath

from runinfo import ROOT, run_info, save_results  # also puts backend/ on sys.path

from app import config  # noqa: E402
from app.ingest import clone  # noqa: E402
from app.ingest.discover import discover  # noqa: E402
from app.paths import is_test_path  # noqa: E402

BANDIT = "bandit==1.9.4"
SKIP_RULES = "B101,B404"  # assert statements and `import subprocess`: never actionable by themselves
MIN_FINDINGS = 40
TARGET = 4
POOL = [
    "benoitc/gunicorn", "celery/celery", "certbot/certbot", "getredash/redash", "ipython/ipython",
    "mitmproxy/mitmproxy", "OctoPrint/OctoPrint", "paramiko/paramiko", "psf/requests",
    "pytest-dev/pytest", "ranger/ranger", "scrapy/scrapy", "sphinx-doc/sphinx",
    "sqlmapproject/sqlmap", "tornadoweb/tornado", "urllib3/urllib3", "yt-dlp/yt-dlp",
]
EXCLUSIONS = ROOT / "eval" / "results" / "reachability_exclusions.txt"
PREREG = "eval/reachability_prereg.md"


def eligible_path(path: str) -> bool:
    """Not test/example code and not under docs/ or doc/."""
    return not is_test_path(path) and not ({"docs", "doc"} & set(PurePosixPath(path).parts[:-1]))


def run_bandit(files: dict[str, str], timeout: int = 900) -> tuple[list[dict], int]:
    """`files`: repo path -> text. Writes them to a temp directory that holds nothing else and runs
    Bandit there. Returns (findings without code, number of files Bandit could not parse)."""
    with tempfile.TemporaryDirectory(prefix="repolens-bandit-count-") as tmp:
        root = Path(tmp).resolve()
        for rel, text in files.items():
            target = (root / rel).resolve()
            if not target.is_relative_to(root):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
        cmd = ["uvx", "--from", BANDIT, "bandit", "-r", str(root), "-f", "json", "-q",
               "--ignore-nosec", "--exit-zero", "--skip", SKIP_RULES]
        env = {k: v for k, v in os.environ.items() if not k.startswith("BANDIT")}
        proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)
        data = json.loads(proc.stdout)
        found = [{
            "path": Path(r["filename"]).resolve().relative_to(root).as_posix(),
            "line": r["line_number"], "test_id": r["test_id"],
            "severity": r["issue_severity"], "confidence": r["issue_confidence"],
        } for r in data["results"]]
        return found, len(data.get("errors", []))


def summarize(found: list[dict]) -> dict:
    return {
        "total": len(found),
        "by_test_id": dict(sorted(Counter(f["test_id"] for f in found).items())),
        "by_severity": dict(Counter(f["severity"] for f in found)),
        "by_confidence": dict(Counter(f["confidence"] for f in found)),
        "files_with_findings": len({f["path"] for f in found}),
    }


def count_dir(root: Path) -> dict:
    """Discover (pipeline limits), keep eligible Python files, run Bandit on a redacted copy."""
    found = discover(root, config.MAX_FILES, config.MAX_FILE_BYTES)
    if found.hit_file_limit:
        return {"skipped": "over the file limit", "kept_files": len(found.files),
                "beyond_limit": found.beyond_limit}
    python = {f.path: f.content for f in found.files if f.language == "python"}
    scanned = {p: c for p, c in python.items() if eligible_path(p)}
    findings, parse_errors = run_bandit(scanned)
    return {"kept_files": len(found.files), "python_files": len(python),
            "python_files_scanned": len(scanned), "bandit_parse_errors": parse_errors,
            **summarize(findings)}


def gh(*args: str) -> dict:
    p = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(p.stderr[:200])
    return json.loads(p.stdout)


def count_repo(name: str) -> dict:
    meta = gh(f"repos/{name}")
    sha = gh(f"repos/{name}/commits/{meta['default_branch']}")["sha"]
    out = {"repo": name, "sha": sha, "licence": (meta.get("license") or {}).get("spdx_id"),
           "default_branch": meta["default_branch"], "archived": meta["archived"]}
    url = clone.normalize_repo_url(f"https://github.com/{name}")
    work = Path(tempfile.mkdtemp(prefix="repolens-bandit-clone-"))
    try:
        for attempt in (1, 2):
            try:
                clone.fetch_commit(url, sha, work / "repo", timeout=config.CLONE_TIMEOUT_S)
                break
            except Exception as e:  # CloneError: record, retry once
                if attempt == 2:
                    return {**out, "skipped": f"clone failed: {str(e)[:120]}"}
                clone.remove_workspace(work / "repo")
        out.update(count_dir(work / "repo"))
    finally:
        clone.remove_workspace(work)
    return out


def check_prereg_unchanged() -> str:
    status = subprocess.run(["git", "status", "--porcelain", "--", PREREG], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    if status:
        raise SystemExit(f"{PREREG} differs from the committed version; commit or revert it first.")
    return subprocess.run(["git", "log", "-1", "--format=%H", "--", PREREG], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def main() -> None:
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args()
    prereg_sha = check_prereg_unchanged()
    excluded = {line.strip().lower().rstrip("/") for line in EXCLUSIONS.read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    info = run_info(llm_used=False)
    info["tools"] = {"bandit": BANDIT, "skip": SKIP_RULES}
    records, accepted = [], 0
    for name in POOL:
        if accepted >= TARGET:
            break
        if f"https://github.com/{name}".lower() in excluded:
            records.append({"repo": name, "skipped": "in the exclusions file"})
            print(name, "excluded", flush=True)
            continue
        try:
            rec = count_repo(name)
        except Exception as e:
            rec = {"repo": name, "skipped": f"error: {str(e)[:150]}"}
        if "skipped" not in rec:
            rec["accepted"] = rec["total"] >= MIN_FINDINGS
            accepted += rec["accepted"]
        records.append(rec)
        print(name, {k: rec.get(k) for k in ("sha", "kept_files", "python_files_scanned", "total",
                                              "accepted", "skipped")}, flush=True)
    results = {"prereg_commit": prereg_sha, "min_findings": MIN_FINDINGS, "target": TARGET,
               "pool_order": POOL, "accepted": [r["repo"] for r in records if r.get("accepted")],
               "counted_after_stop": "repos after the fourth accepted are not counted",
               "repos": records}
    path = save_results("reachability_bandit_count", info, results)
    print("accepted", len(results["accepted"]), "of target", TARGET, "->", path)


if __name__ == "__main__":
    main()
