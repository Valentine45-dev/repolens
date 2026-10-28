"""Detector precision/recall: RepoLens vs Bandit (Python) and Semgrep (JS), same labels.

    uv run --project backend python eval/detector_eval.py

Fixtures: eval/detector_fixtures/{python,js}. Labels are trailing comments on the fixture
lines, written before any tool was run: "vuln: <category>" is an issue, "safe: <category>"
looks similar but is fine (documentation; any finding there is a false positive anyway).
js/routes.js (fixture 2) was added after run 1, because fixture 1 had no request input for
Semgrep's taint rules; scores are also reported per fixture file.

Scoring (fixed before the first run):
- Each tool's findings are mapped to the shared categories by rule id (tables below). Findings
  from rules outside these categories are listed as out of scope and not counted.
- A finding is a true positive if it is on a "vuln" line of the same file and category.
  Findings are deduplicated by (file, line, category). Every other in-scope finding is a false
  positive. A "vuln" label no finding hit is a false negative.
- RepoLens is scored on both languages; Bandit on the Python labels; Semgrep on the JS labels.
  A category a tool has no rule for still counts its labels as misses (shown as "no rule").

Tools run with their own default settings: Bandit on the Python fixtures (all tests), Semgrep
with the p/javascript and p/secrets rulesets, natively, or in the semgrep/semgrep Docker image
when the native run fails. Versions are saved with the results.
"""

import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from runinfo import ROOT, header, run_info, save_results  # also puts backend/ on sys.path

from app.detect import detect  # noqa: E402
from app.ingest.parse import parse_python  # noqa: E402
from app.ingest.parse_js import parse_js  # noqa: E402
from app.ingest.redact import redact  # noqa: E402

FIXTURES = ROOT / "eval" / "detector_fixtures"
BANDIT = "bandit==1.9.4"
SEMGREP = "semgrep==1.182.1"
SEMGREP_IMAGE = "semgrep/semgrep:1.182.1"
SEMGREP_CONFIGS = ["p/javascript", "p/secrets"]

MARK = re.compile(r"(?:#|//)\s*(vuln|safe):\s*([a-z-]+)")
LANG_DIRS = {"python": "python", "js": "javascript"}

REPOLENS_MAP = {
    "py-eval-exec": "code-injection",
    "js-eval": "code-injection",
    "js-new-function": "code-injection",
    "py-subprocess-shell": "shell-command",
    "js-child-process-exec": "shell-command",
    "py-sql-string": "sql-injection",
    "js-sql-string": "sql-injection",
    "py-bare-except": "bare-except",
    "js-inner-html": "html-injection",
    "hardcoded-secret": "hardcoded-secret",
}
# Bandit test ids (bandit docs). Bandit has no bare-except check (B110 is try/except/pass,
# a different pattern), so bare-except counts as "no rule".
BANDIT_MAP = {
    "B102": "code-injection",  # exec_used
    "B307": "code-injection",  # eval
    "B602": "shell-command",  # subprocess_popen_with_shell_equals_true
    "B604": "shell-command",  # any_other_function_with_shell_equals_true
    "B608": "sql-injection",  # hardcoded_sql_expressions
    "B105": "hardcoded-secret",  # hardcoded_password_string
    "B106": "hardcoded-secret",  # hardcoded_password_funcarg
    "B107": "hardcoded-secret",  # hardcoded_password_default
}
# Semgrep registry rule ids are many and change; mapped by keywords in the check id, first match
# wins. Anything unmatched is listed as out of scope so the mapping can be checked by hand.
SEMGREP_KEYWORDS = [
    (("child-process", "child_process", "exec"), "shell-command"),
    (("innerhtml", "outerhtml", "insecure-document-method", "xss", "html"), "html-injection"),
    (("sql", "knex", "sequelize"), "sql-injection"),
    (("eval", "new-function", "function-constructor", "code-string", "code-injection"),
     "code-injection"),
    (("secret", "password", "token", "credential", "api-key", "apikey", "jwt"),
     "hardcoded-secret"),
]


def load_labels() -> list[dict]:
    labels = []
    for lang_dir in LANG_DIRS:
        for path in sorted((FIXTURES / lang_dir).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(FIXTURES).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                m = MARK.search(line)
                if m:
                    labels.append({"file": rel, "line": n, "kind": m[1], "category": m[2],
                                   "language": LANG_DIRS[lang_dir]})
    return labels


# --- tools -----------------------------------------------------------------------------------

def run_repolens() -> tuple[list[dict], list[dict]]:
    found = []
    for lang_dir, language in LANG_DIRS.items():
        for path in sorted((FIXTURES / lang_dir).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(FIXTURES).as_posix()
            redacted, secrets = redact(path.read_text(encoding="utf-8"))
            for s in secrets:
                found.append({"file": rel, "line": s.line, "rule": "hardcoded-secret"})
            parse = parse_python if language == "python" else parse_js
            parsed = parse(rel, redacted)
            for hit in detect(rel, language, redacted, parsed):
                found.append({"file": rel, "line": hit.line, "rule": hit.rule_id})
    return _map(found, lambda rule: REPOLENS_MAP.get(rule))


def run_bandit() -> tuple[list[dict], list[dict], str]:
    target = FIXTURES / "python"
    out = subprocess.run(
        ["uvx", "--from", BANDIT, "bandit", "-r", str(target), "-f", "json", "-q"],
        capture_output=True, text=True, cwd=ROOT,
    )
    data = json.loads(out.stdout)
    found = [{"file": Path(r["filename"]).resolve().relative_to(FIXTURES).as_posix(),
              "line": r["line_number"], "rule": f"{r['test_id']} {r['test_name']}"}
             for r in data["results"]]
    mapped, other = _map(found, lambda rule: BANDIT_MAP.get(rule.split()[0]))
    return mapped, other, BANDIT


def _semgrep_json(native: bool) -> tuple[dict, str]:
    args = ["scan", "--json", "--metrics=off", "--disable-version-check", "--quiet"]
    for c in SEMGREP_CONFIGS:
        args += ["--config", c]
    if native:
        cmd = ["uvx", "--from", SEMGREP, "semgrep", *args, str(FIXTURES / "js")]
        how = f"{SEMGREP} (native)"
    else:
        cmd = ["docker", "run", "--rm", "-v", f"{FIXTURES / 'js'}:/src", SEMGREP_IMAGE,
               "semgrep", *args, "/src"]
        how = f"{SEMGREP_IMAGE} (docker)"
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    data = json.loads(out.stdout) if out.stdout.strip().startswith("{") else None
    if data is None or (out.returncode not in (0, 1) and not data.get("results")):
        raise RuntimeError(f"semgrep failed ({how}): exit {out.returncode}: {out.stderr[-500:]}")
    return data, how


def run_semgrep() -> tuple[list[dict], list[dict], str]:
    try:
        data, how = _semgrep_json(native=True)
    except (RuntimeError, json.JSONDecodeError) as e:
        print(f"native semgrep did not work ({str(e)[:120]}); using docker", file=sys.stderr)
        if not shutil.which("docker"):
            raise
        data, how = _semgrep_json(native=False)
    found = []
    for r in data["results"]:
        name = Path(r["path"]).name  # native: absolute path, docker: /src/...
        found.append({"file": f"js/{name}", "line": r["start"]["line"], "rule": r["check_id"]})

    def category(rule: str) -> str | None:
        low = rule.lower()
        for words, cat in SEMGREP_KEYWORDS:
            if any(w in low for w in words):
                return cat
        return None

    mapped, other = _map(found, category)
    return mapped, other, how


def _map(found, to_category) -> tuple[list[dict], list[dict]]:
    mapped, other, seen = [], [], set()
    for f in found:
        cat = to_category(f["rule"])
        if cat is None:
            other.append(f)
            continue
        key = (f["file"], f["line"], cat)
        if key not in seen:
            seen.add(key)
            mapped.append({**f, "category": cat})
    return mapped, other


# --- scoring ---------------------------------------------------------------------------------

def score(findings: list[dict], labels: list[dict], categories_with_rules: set[str]) -> dict:
    vulns = [lab for lab in labels if lab["kind"] == "vuln"]
    hit_labels, tp_findings = set(), []
    fps = []
    for f in findings:
        match = next((lab for lab in vulns if lab["file"] == f["file"]
                      and lab["line"] == f["line"] and lab["category"] == f["category"]), None)
        if match:
            hit_labels.add((match["file"], match["line"], match["category"]))
            tp_findings.append(f)
        else:
            safe = any(lab["file"] == f["file"] and lab["line"] == f["line"]
                       and lab["kind"] == "safe" for lab in labels)
            fps.append({**f, "on_safe_line": safe})

    per_category = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "rule": True})
    for lab in vulns:
        c = per_category[lab["category"]]
        c["rule"] = lab["category"] in categories_with_rules
        if (lab["file"], lab["line"], lab["category"]) in hit_labels:
            c["tp"] += 1
        else:
            c["fn"] += 1
    for f in fps:
        per_category[f["category"]]["fp"] += 1

    tp = len(hit_labels)
    fp = len(fps)
    fn = len(vulns) - tp
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "per_category": dict(per_category),
        "false_positives": fps,
        "missed": [lab for lab in vulns
                   if (lab["file"], lab["line"], lab["category"]) not in hit_labels],
    }


def fmt(x):
    return "  -  " if x is None else f"{x:.2f}"


def main() -> None:
    info = run_info(llm_used=False)
    print(header(info))
    labels = load_labels()
    py = [lab for lab in labels if lab["language"] == "python"]
    js = [lab for lab in labels if lab["language"] == "javascript"]

    rl_found, rl_other = run_repolens()
    bandit_found, bandit_other, bandit_version = run_bandit()
    semgrep_found, semgrep_other, semgrep_version = run_semgrep()

    def by_lang(found, lang_dir):
        return [f for f in found if f["file"].startswith(f"{lang_dir}/")]

    rl_cats = set(REPOLENS_MAP.values())
    runs = {
        ("python", "RepoLens"): score(by_lang(rl_found, "python"), py, rl_cats),
        ("python", "Bandit"): score(bandit_found, py, set(BANDIT_MAP.values())),
        ("javascript", "RepoLens"): score(by_lang(rl_found, "js"), js, rl_cats),
        ("javascript", "Semgrep"): score(semgrep_found, js,
                                         {cat for _, cat in SEMGREP_KEYWORDS}),
    }

    # Per fixture file too: JS fixture 2 (routes.js) was added after run 1, so its numbers are
    # reported apart from fixture 1's.
    semgrep_cats = {cat for _, cat in SEMGREP_KEYWORDS}
    per_file = {}
    for path in sorted({lab["file"] for lab in labels}):
        file_labels = [lab for lab in labels if lab["file"] == path]
        tools = [("RepoLens", rl_found, rl_cats)]
        tools.append(("Bandit", bandit_found, set(BANDIT_MAP.values())) if path.startswith(
            "python/") else ("Semgrep", semgrep_found, semgrep_cats))
        for tool, found, cats in tools:
            per_file[(path, tool)] = score([f for f in found if f["file"] == path],
                                           file_labels, cats)

    n_py = sum(lab["kind"] == "vuln" for lab in py)
    n_js = sum(lab["kind"] == "vuln" for lab in js)
    print(f"labels: python {n_py} vuln / {len(py) - n_py} safe;"
          f" javascript {n_js} vuln / {len(js) - n_js} safe")
    print(f"tools: {bandit_version}, {semgrep_version}\n")
    print(f"{'language':<11}{'tool':<10}{'TP':>4}{'FP':>4}{'FN':>4}  precision  recall")
    for (lang, tool), s in runs.items():
        print(f"{lang:<11}{tool:<10}{s['tp']:>4}{s['fp']:>4}{s['fn']:>4}"
              f"     {fmt(s['precision'])}    {fmt(s['recall'])}")

    print(f"\n{'fixture':<22}{'tool':<10}{'TP':>4}{'FP':>4}{'FN':>4}  precision  recall")
    for (path, tool), s in per_file.items():
        print(f"{path:<22}{tool:<10}{s['tp']:>4}{s['fp']:>4}{s['fn']:>4}"
              f"     {fmt(s['precision'])}    {fmt(s['recall'])}")

    for lang in ("python", "javascript"):
        tools = [t for (lg, t) in runs if lg == lang]
        cats = sorted({c for (lg, _), s in runs.items() if lg == lang for c in s["per_category"]})
        print(f"\n{lang}: per category, TP/FP/FN")
        print(f"  {'category':<18}" + "".join(f"{t:<16}" for t in tools))
        for cat in cats:
            cells = []
            for t in tools:
                c = runs[(lang, t)]["per_category"].get(cat)
                if c is None:
                    cells.append("0/0/0")
                elif not c["rule"]:
                    cells.append(f"{c['tp']}/{c['fp']}/{c['fn']} no rule")
                else:
                    cells.append(f"{c['tp']}/{c['fp']}/{c['fn']}")
            print(f"  {cat:<18}" + "".join(f"{x:<16}" for x in cells))

    print()
    for (_lang, tool), s in runs.items():
        for f in s["false_positives"]:
            where = "safe line" if f["on_safe_line"] else "unlabelled line"
            print(f"FP {tool:<9}{f['file']}:{f['line']} {f['category']} ({where}) [{f['rule']}]")
        for lab in s["missed"]:
            print(f"FN {tool:<9}{lab['file']}:{lab['line']} {lab['category']}")
    others = {"RepoLens": rl_other, "Bandit": bandit_other, "Semgrep": semgrep_other}
    for tool, items in others.items():
        for f in items:
            print(f"out of scope {tool}: {f['file']}:{f['line']} [{f['rule']}]")

    results = {
        "tools": {"bandit": bandit_version, "semgrep": semgrep_version,
                  "semgrep_configs": SEMGREP_CONFIGS},
        "labels": labels,
        "scores": {f"{lang}/{tool}": s for (lang, tool), s in runs.items()},
        "scores_per_fixture": {f"{path}/{tool}": s for (path, tool), s in per_file.items()},
        "out_of_scope": others,
    }
    print("\nsaved", save_results("detectors", info, results))


if __name__ == "__main__":
    main()
