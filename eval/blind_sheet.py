"""Blind labelling sheet for the PyGoat precision re-run (v1 re-baseline, 31 Oct).

    uv run --project backend --env-file .env python eval/blind_sheet.py

Same procedure as realworld_precision.py (same analysed snapshot of PyGoat @ 46fef96, Bandit
1.9.4 on the Python files RepoLens kept, seed 20261028, 20 findings per tool, sorted by
(path, line, rule)), with these differences, all about blinding the labeller:
- Each finding is shown only as path, line, category and a code snippet. Rule ids and messages
  are not shown. Categories come from one table (CATEGORIES) shared by both tools.
- The snippet is built the same way for every row, from the source at the pinned commit (a fresh
  clone, deleted afterwards): the flagged line with 3 lines of context each side, secrets
  masked by one rule (mask()) that does not look at which tool flagged the line. The tools' own
  stored or masked snippets are never used.
- Rows two findings share (same path, line and category, from either tool) are shown once and
  the label applies to every finding on the row. The count of merged rows is recorded.
- Rows are shuffled and given random ids. The key (id -> tool, rule, message) and the full
  samples are written next to the sheet, outside git, and not opened until labelling is done.
- Labels are the owner's: real / not real ("real" = a reviewer should act on it), plus a free
  note. Nothing here proposes a label.

Remaining leak (a limit of the blinding): some categories exist for only one tool (for example
"server binds to all interfaces", "Flask debug mode"), so the category column can hint at the
tool. Categories are not merged to hide this.
"""

import csv
import hashlib
import json
import random
import re
import secrets
import shutil
import tempfile
from pathlib import Path

import realworld_precision as rp
from runinfo import header, run_info, save_results

from app import config, db
from app.ingest import clone
from app.ingest.redact import redact

URL = "https://github.com/adeyosemanputra/pygoat"
ASSETS = Path(r"C:\projects\repolens-eval-assets\pygoat-blind")
CONTEXT = 3

BROAD_EXCEPT = "broad or silenced exception handling"
CATEGORIES = {
    "hardcoded-secret": "hardcoded secret or password",
    "B105": "hardcoded secret or password",
    "B106": "hardcoded secret or password",
    "py-bare-except": BROAD_EXCEPT,
    "B110": BROAD_EXCEPT,
    "py-eval-exec": "eval/exec",
    "B307": "eval/exec",
    "B102": "eval/exec",
    "py-subprocess-shell": "shell command with shell=True",
    "B602": "shell command with shell=True",
    "B604": "shell command with shell=True",
    "B603": "subprocess use",
    "B404": "subprocess use",
    "py-sql-string": "SQL built from strings",
    "B608": "SQL built from strings",
    "B104": "server binds to all interfaces",
    "B201": "Flask debug mode on",
    "B324": "weak hash",
    "B311": "weak random",
    "B506": "unsafe YAML load",
    "B113": "request without timeout",
    "B301": "pickle use",
    "B403": "pickle use",
    "B317": "XML library use",
    "B319": "XML library use",
    "B406": "XML library use",
    "B409": "XML library use",
}

# One masking rule for every snippet: RepoLens's redactor (patterns for known key formats, URL
# passwords, secret-like assignments) plus any quoted value assigned to a secret-looking name.
SECRET_NAME = re.compile(
    r"""(?ix)((?:pass(?:word|wd)?|pwd|secret|token|api[_-]?key|private[_-]?key|key)\w*["']?\]?\s*[:=]\s*)
        (["'])(.+?)\2""")


def mask(text: str) -> str:
    text, _ = redact(text)
    return SECRET_NAME.sub(lambda m: f"{m[1]}{m[2]}[REDACTED]{m[2]}", text)


def category_of(rule: str) -> str:
    return CATEGORIES.get(rule.split()[0], "other")


def snippet(repo: Path, path: str, line: int | None) -> str:
    lines = (repo / path).read_text(encoding="utf-8", errors="replace").splitlines()
    i = (line or 1) - 1
    lo, hi = max(0, i - CONTEXT), min(len(lines), i + CONTEXT + 1)
    shown = [f"{'>' if n == i else ' '} {n + 1:>4}  {lines[n]}" for n in range(lo, hi)]
    return mask("\n".join(shown))


def bandit_on(repo: Path, py_paths: list[str]) -> tuple[list[dict], list[dict]]:
    import json as _json
    import subprocess

    out = subprocess.run(
        ["uvx", "--from", rp.BANDIT, "bandit", "-f", "json", "-q",
         *[str(repo / p) for p in py_paths]],
        capture_output=True, text=True, encoding="utf-8")
    data = _json.loads(out.stdout)
    found = [{"path": Path(r["filename"]).resolve().relative_to(repo.resolve()).as_posix(),
              "line": r["line_number"], "rule": f"{r['test_id']} {r['test_name']}",
              "severity": r["issue_severity"].lower(), "message": r["issue_text"]}
             for r in data["results"]]
    errors = [{"path": Path(e["filename"]).name, "reason": e["reason"][:200]}
              for e in data.get("errors", [])]
    return found, errors


def sample(findings: list[dict]) -> list[dict]:
    ordered = sorted(findings, key=lambda f: (f["path"], f["line"] or 0, f["rule"]))
    return random.Random(rp.SEED).sample(ordered, min(rp.N, len(ordered)))


def key_of(f: dict) -> tuple:
    return f["path"], f["line"], category_of(f["rule"])


def main() -> None:
    db.open_pool()
    with db.pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id, s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE lower(r.url) = lower(%s) AND st.status = 'done'", (URL,)).fetchone()
    snapshot_id, sha = row["id"], row["commit_sha"]
    files = rp.stored_files(snapshot_id)
    py_paths = sorted(p for p, f in files.items() if f["language"] == "python")
    rl = rp.repolens_findings(snapshot_id)

    work = Path(tempfile.mkdtemp(prefix="repolens-blind-"))
    try:
        repo = work / "repo"
        clone.fetch_commit(clone.normalize_repo_url(URL), sha, repo,
                           timeout=config.CLONE_TIMEOUT_S)
        bd, bandit_errors = bandit_on(repo, py_paths)
        samples = {"RepoLens": sample(rl), "Bandit": sample(bd)}

        groups: dict[tuple, dict] = {}
        for tool, picked in samples.items():
            for f in picked:
                g = groups.setdefault(key_of(f), {"path": f["path"], "line": f["line"],
                                                  "category": category_of(f["rule"]),
                                                  "findings": []})
                g["findings"].append({"tool": tool, "rule": f["rule"], "message": f["message"],
                                      "severity": f["severity"]})
        for g in groups.values():
            g["snippet"] = snippet(repo, g["path"], g["line"])
    finally:
        clone.remove_workspace(work)
        shutil.rmtree(work, ignore_errors=True)

    rows = list(groups.values())
    random.SystemRandom().shuffle(rows)
    ids = set()
    while len(ids) < len(rows):
        ids.add(secrets.token_hex(2))
    for g, rid in zip(rows, sorted(ids, key=lambda _: random.SystemRandom().random())):
        g["id"] = rid

    total = sum(len(s) for s in samples.values())
    merged = sum(1 for g in rows if len({f["tool"] for f in g["findings"]}) > 1)
    same_tool_dupes = sum(len(g["findings"]) - len({f["tool"] for f in g["findings"]})
                          for g in rows)

    # Population overlap, for context: findings both tools put on the same path+line+category.
    rl_keys = {key_of(f) for f in rl}
    bd_keys = {key_of(f) for f in bd}
    other_rules = sorted({f["rule"] for f in rl + bd if category_of(f["rule"]) == "other"})

    ASSETS.mkdir(parents=True, exist_ok=True)
    sheet = ASSETS / "sheet.csv"
    with sheet.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "path", "line", "category", "snippet", "label (real / not real)",
                    "note"])
        for g in rows:
            w.writerow([g["id"], g["path"], g["line"], g["category"], g["snippet"], "", ""])
    key = ASSETS / "key.json"
    key.write_text(json.dumps({"rows": rows, "samples": samples}, indent=2) + "\n",
                   encoding="utf-8")

    def sha256(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    info = run_info(llm_used=False)
    print(header(info))
    print(f"PyGoat @ {sha[:7]} snapshot {snapshot_id}: {len(files)} files, {len(py_paths)} Python")
    print(f"populations: RepoLens {len(rl)}, Bandit {len(bd)} ({len(bandit_errors)} files "
          f"Bandit could not parse); same path+line+category in both: {len(rl_keys & bd_keys)}")
    print(f"sampled {total} findings -> {len(rows)} sheet rows ({merged} rows merged across "
          f"tools, {same_tool_dupes} extra same-tool findings on a shared row)")
    print(f"'other' category rules (unmapped): {other_rules or 'none'}")
    print(f"sheet {sheet}\nkey (do not open until labelled) {key}")
    results = {
        "repo": {"url": URL, "commit": sha, "snapshot_id": snapshot_id,
                 "files_kept": len(files), "python_files": len(py_paths)},
        "sampling": {"seed": rp.SEED, "n": rp.N, "order": "path, line, rule"},
        "population": {"RepoLens": len(rl), "Bandit": len(bd),
                       "RepoLens_by_rule": rp_counts(rl), "Bandit_by_rule": rp_counts(bd),
                       "bandit_parse_errors": len(bandit_errors),
                       "both_tools_same_path_line_category": len(rl_keys & bd_keys)},
        "sample_findings": total, "sheet_rows": len(rows), "merged_rows": merged,
        "extra_same_tool_findings_on_shared_rows": same_tool_dupes,
        "other_category_rules": other_rules,
        "snippet": {"context_lines": CONTEXT, "source": "fresh clone at the pinned commit",
                    "masking": "eval/blind_sheet.py mask(): redact() + secret-named quoted values"},
        "files_sha256": {"sheet.csv (blank)": sha256(sheet), "key.json": sha256(key)},
        "files_location": str(ASSETS),
        "labels_confirmed": False,
    }
    print("saved", save_results("realworld_blind_setup", info, results))


def rp_counts(found: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for f in found:
        counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
