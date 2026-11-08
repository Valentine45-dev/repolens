"""Setup of the reachability study (pre-registration sections 6 to 8 and Amendment 1): for each accepted
repo, the Bandit list on the stored (redacted) text of the analysed snapshot, the tier and entry class
of every finding, the labelled pool, the blind sheet, the second-judge sheet and the key.

    uv run --project backend --env-file .env python eval/reachability_setup.py

Run after eval/reachability_ingest.py. Prints and commits COUNTS ONLY (tier shares, entry-class
shares, hashes): no code, no paths, no labels. The sheets and the key.json are written outside git
(ASSETS); the key stays unopened until the labelled sheet's SHA-256 is committed. Nothing here proposes
a label, and the sheets show neither the tool, the rule id, the severity, the tier nor the rank.
"""

import csv
import glob
import hashlib
import json
import math
import random
import string
from collections import Counter
from pathlib import Path

import reachability_guard
from blind_sheet import CATEGORIES as BASE_CATEGORIES
from blind_sheet import mask
from reachability_bandit_count import eligible_path, run_bandit
from runinfo import ROOT, header, run_info, save_results

from app import db
from app.detect.rules import RULE_IDS_BY_CATEGORY
from app.reach.load import build

SEED = 20261108
POOL_CAP = 60
JUDGE2_SHARE = 0.20
CONTEXT = 3
ASSETS = Path(r"C:\projects\repolens-eval-assets\reachability")
TIERS = ("solid", "guess", "not_checked", "none")

# Bandit rules that appear in the counting run and are not in blind_sheet.CATEGORIES. Neutral
# wording: one category per weakness, whichever tool names it.
CATEGORIES = {
    **BASE_CATEGORIES,
    "B102": "eval/exec",
    "B103": "overly permissive file permissions",
    "B108": "hardcoded temporary directory",
    "B202": "unsafe archive extraction",
    "B303": "weak hash",
    "B310": "URL opened without a scheme check",
    "B318": "XML library use",
    "B408": "XML library use",
    "B501": "TLS certificate validation switched off",
    "B605": "process started through a shell",
    "B606": "process started without a shell",
    "B607": "process started with a partial executable path",
}


def category_of(rule: str) -> str:
    return CATEGORIES.get(rule, "other (read the code)")


def latest_count_run() -> dict:
    path = sorted(glob.glob(str(ROOT / "eval" / "results" / "reachability_bandit_count-*.json")))[-1]
    return json.load(open(path, encoding="utf-8"))


def snippet(content: str, line: int | None) -> str:
    lines = content.split("\n")
    i = (line or 1) - 1
    lo, hi = max(0, i - CONTEXT), min(len(lines), i + CONTEXT + 1)
    shown = [f"{'>' if n == i else ' '} {n + 1:>4}  {lines[n]}" for n in range(lo, hi)]
    return mask("\n".join(shown))


def describe(items: list[dict]) -> dict:
    """Counts only: by tier, by entry class, and tier x entry class."""
    return {
        "n": len(items),
        "tier": dict(Counter(i["tier"] for i in items)),
        "entry_class": dict(Counter(str(i["entry_class"]) for i in items)),
        "tier_x_entry_class": dict(Counter(f"{i['tier']}|{i['entry_class']}" for i in items)),
    }


def snapshot_for(conn, repo: str, sha: str) -> int:
    row = conn.execute(
        "SELECT s.id, st.status FROM snapshots s JOIN repos r ON r.id = s.repo_id"
        " JOIN snapshot_status st ON st.snapshot_id = s.id"
        " WHERE lower(r.url) = lower(%s) AND s.commit_sha = %s",
        (f"https://github.com/{repo}", sha),
    ).fetchone()
    if row is None or row["status"] != "done":
        raise SystemExit(f"{repo} @ {sha[:7]} is not analysed; run reachability_ingest.py first.")
    return row["id"]


def repo_lists(conn, repo: dict, expected: int) -> dict:
    sha = repo["sha"]
    snapshot_id = snapshot_for(conn, repo["repo"], sha)
    files = {r["path"]: r for r in conn.execute(
        "SELECT id, path, language, content FROM files WHERE snapshot_id = %s", (snapshot_id,))}
    scanned = {p: f["content"] or "" for p, f in files.items()
               if f["language"] == "python" and eligible_path(p)}
    found, parse_errors = run_bandit(scanned)
    reach = build(snapshot_id)

    ordered = sorted(found, key=lambda f: (f["path"], f["line"], f["test_id"]))
    seen: Counter = Counter()
    bandit = []
    for f in ordered:
        slot = (f["path"], f["line"], f["test_id"])
        occurrence = seen[slot]
        seen[slot] += 1
        file_id = files[f["path"]]["id"]
        symbol = reach.symbol_at(file_id, f["line"])
        bandit.append({
            "tool": "bandit", "path": f["path"], "line": f["line"], "rule": f["test_id"],
            "severity": f["severity"], "confidence": f["confidence"], "occurrence": occurrence,
            "category": category_of(f["test_id"]),
            "tier": reach.tier(file_id, f["line"]),
            "entry_class": reach.entry_class(file_id, f["line"]),
            "unit": symbol, "unit_name": reach.symbols[symbol].name if symbol in reach.symbols else None,
        })

    # RepoLens's own Security-category findings outside tests, docs and placeholders, in Python
    # files and in non-code files (their secrets are "not checked"). JS/TS is out: this study is
    # Python only. The number left out is recorded.
    rows = conn.execute(
        "SELECT f.id, fi.id AS file_id, fi.path, fi.language, f.line, f.rule_id, f.severity"
        " FROM findings f JOIN files fi ON fi.id = f.file_id"
        " WHERE f.snapshot_id = %s AND f.rule_id = ANY(%s) AND NOT f.in_test AND NOT f.in_docs"
        " AND NOT f.placeholder ORDER BY fi.path COLLATE \"C\", f.line, f.id",
        (snapshot_id, RULE_IDS_BY_CATEGORY["security"]),
    ).fetchall()
    repolens, js_left_out = [], 0
    for r in rows:
        if r["language"] in ("javascript", "typescript"):
            js_left_out += 1
            continue
        symbol = reach.symbol_at(r["file_id"], r["line"])
        repolens.append({
            "tool": "repolens", "finding_id": r["id"], "path": r["path"], "line": r["line"],
            "rule": r["rule_id"], "severity": r["severity"], "category": category_of(r["rule_id"]),
            "tier": reach.tier(r["file_id"], r["line"]),
            "entry_class": reach.entry_class(r["file_id"], r["line"]),
            "unit": symbol, "unit_name": reach.symbols[symbol].name if symbol in reach.symbols else None,
        })

    def pool_of(items: list[dict], stream: str) -> list[dict]:
        if len(items) <= POOL_CAP:
            return list(items)
        picked = random.Random(stream).sample(range(len(items)), POOL_CAP)
        return [items[i] for i in sorted(picked)]

    name = repo["repo"]
    return {
        "repo": name, "sha": sha, "snapshot_id": snapshot_id, "files": files,
        "bandit": bandit, "bandit_parse_errors": parse_errors,
        "matches_counting_run": len(bandit) == expected,
        "bandit_pool": pool_of(bandit, f"{SEED}-{name}"),
        "repolens": repolens, "repolens_js_left_out": js_left_out,
        "repolens_pool": pool_of(repolens, f"{SEED}-{name}-repolens"),
    }


def build_rows(lists: list[dict]) -> list[dict]:
    """One row per (repo, path, line, category); a row two findings share is shown once."""
    groups: dict[tuple, dict] = {}
    for rl in lists:
        for finding in rl["bandit_pool"] + rl["repolens_pool"]:
            key = (rl["repo"], finding["path"], finding["line"], finding["category"])
            group = groups.setdefault(key, {
                "repo": rl["repo"], "path": finding["path"], "line": finding["line"],
                "category": finding["category"], "findings": []})
            group["findings"].append(finding)
        for group in groups.values():
            if group["repo"] == rl["repo"] and "snippet" not in group:
                content = rl["files"][group["path"]]["content"] or ""
                group["snippet"] = snippet(content, group["line"])
    return sorted(groups.values(), key=lambda g: (g["repo"], g["path"], g["line"], g["category"]))


def assign_ids(rows: list[dict]) -> None:
    rng = random.SystemRandom()
    used: set[str] = set()
    for row in rows:
        while True:
            rid = "r-" + "".join(rng.choice(string.ascii_lowercase) for _ in range(5))
            if rid not in used:
                used.add(rid)
                row["id"] = rid
                break


def write_sheet(path: Path, rows: list[dict]) -> None:
    shuffled = list(rows)
    random.SystemRandom().shuffle(shuffled)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "repo", "path", "line", "flagged for", "code", "label (real / not real / unsure)",
                    "note"])
        for r in shuffled:
            w.writerow([r["id"], r["repo"], r["path"], r["line"], r["category"], r["snippet"], "", ""])


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    facts = reachability_guard.check()
    count_run = latest_count_run()
    repos = [r for r in count_run["repos"] if r.get("accepted")]
    db.open_pool()
    lists = []
    with db.pool().connection() as conn:
        for repo in repos:
            lists.append(repo_lists(conn, repo, repo["total"]))
    db.close_pool()

    rows = build_rows(lists)
    assign_ids(rows)
    judge2: list[dict] = []
    for rl in lists:
        mine = [r for r in rows if r["repo"] == rl["repo"]]
        n = math.ceil(JUDGE2_SHARE * len(mine))
        judge2 += random.Random(f"{SEED}-judge2-{rl['repo']}").sample(mine, n)

    ASSETS.mkdir(parents=True, exist_ok=True)
    sheet, sheet2, key = ASSETS / "sheet-blank.csv", ASSETS / "sheet-blank-judge2.csv", ASSETS / "key.json"
    write_sheet(sheet, rows)
    write_sheet(sheet2, judge2)
    key_rows = [{k: v for k, v in r.items() if k != "snippet"} for r in rows]
    key.write_text(json.dumps({
        "seed": SEED, "pool_cap": POOL_CAP, "rows": key_rows,
        "judge2_ids": sorted(r["id"] for r in judge2),
        "bandit_lists": {rl["repo"]: rl["bandit"] for rl in lists},
        "repolens_lists": {rl["repo"]: rl["repolens"] for rl in lists},
    }, indent=1) + "\n", encoding="utf-8")

    info = run_info(llm_used=False)
    print(header(info))
    per_repo = {}
    for rl in lists:
        mine = [r for r in rows if r["repo"] == rl["repo"]]
        merged = sum(1 for r in mine if len({f["tool"] for f in r["findings"]}) > 1)
        per_repo[rl["repo"]] = {
            "sha": rl["sha"], "snapshot_id": rl["snapshot_id"],
            "bandit_total": len(rl["bandit"]), "matches_counting_run": rl["matches_counting_run"],
            "bandit_parse_errors": rl["bandit_parse_errors"],
            "bandit_list": describe(rl["bandit"]),
            "bandit_pool": {"size": len(rl["bandit_pool"]),
                            "sampled": len(rl["bandit"]) > POOL_CAP, **describe(rl["bandit_pool"])},
            "repolens_list": describe(rl["repolens"]),
            "repolens_pool": {"size": len(rl["repolens_pool"]),
                              "sampled": len(rl["repolens"]) > POOL_CAP,
                              **describe(rl["repolens_pool"])},
            "repolens_js_ts_findings_left_out": rl["repolens_js_left_out"],
            "sheet_rows": len(mine), "rows_shared_by_both_tools": merged,
            "judge2_rows": sum(1 for r in judge2 if r["repo"] == rl["repo"]),
        }
        d = per_repo[rl["repo"]]
        print(f"\n{rl['repo']} @ {rl['sha'][:7]} (snapshot {rl['snapshot_id']})")
        print(f"  Bandit list {d['bandit_total']} (counting run {'matches' if rl['matches_counting_run'] else 'DIFFERS'}), "
              f"pool {d['bandit_pool']['size']}{' (sampled)' if d['bandit_pool']['sampled'] else ' (all)'}")
        for title, part in (("list", d["bandit_list"]), ("pool", d["bandit_pool"])):
            print(f"  Bandit {title}: tier {part['tier']}  entry class {part['entry_class']}")
        print(f"  RepoLens security list {d['repolens_list']['n']} (JS/TS left out {rl['repolens_js_left_out']}), "
              f"pool {d['repolens_pool']['size']}: tier {d['repolens_list']['tier']}")
        print(f"  sheet rows {d['sheet_rows']} ({merged} shared), judge-2 rows {d['judge2_rows']}")

    results = {
        "guard": facts, "seed": SEED, "pool_cap": POOL_CAP, "judge2_share": JUDGE2_SHARE,
        "bandit": {"pin": "bandit==1.9.4", "skip": "B101,B404",
                   "count_run": count_run["run"].get("commit", None)},
        "repos": per_repo,
        "sheet_rows_total": len(rows), "judge2_rows_total": len(judge2),
        "choices_not_spelled_out_in_the_preregistration": [
            "RepoLens secondary pool = Security-category findings in Python files and in non-code files; "
            "JS/TS findings left out (Python-only study); sample stream f'{SEED}-{repo}-repolens'",
            "judge-2 rows = ceil(20%) of each repo's sheet rows (Bandit and RepoLens rows together), "
            "random.Random(f'{SEED}-judge2-{repo}') over rows sorted by (path, line, category)",
            "sheet columns: id, repo, path, line, 'flagged for' (neutral category), code (3 lines of "
            "context, stored redacted text, blind_sheet.mask()), label, note",
        ],
        "files_sha256": {"sheet-blank.csv": sha256(sheet), "sheet-blank-judge2.csv": sha256(sheet2),
                         "key.json": sha256(key)},
        "files_location": str(ASSETS),
        "labels_received": False,
    }
    print("\nsaved", save_results("reachability_setup", info, results))
    print("sheets:", sheet, "|", sheet2, "\nkey (do not open until the labelled sheet's hash is committed):", key)


if __name__ == "__main__":
    main()
