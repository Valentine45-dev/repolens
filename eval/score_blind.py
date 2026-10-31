"""Score the blind PyGoat labelling (see blind_sheet.py).

    uv run --project backend python eval/score_blind.py

Reads the labelled sheet and the key (both outside git, in eval-assets), refuses to run unless the
labelled sheet's SHA-256 matches the one recorded in eval/results/realworld_labels_received-*.json.
A row's label applies to every finding on it (rows merged across tools carry one label). Per tool:
precision = rows labelled "real" / 20 sampled findings, with a Wilson 95% interval, per rule too,
and for Bandit also with every B104 finding counted as real (as in v1). Rows whose note says the
labeller was unsure are counted and listed by id; precision is also shown with those rows counted
all real and all not real, as a range. Recall is not measured.
"""

import csv
import glob
import hashlib
import json
import re
import sys
from pathlib import Path

from runinfo import ROOT, RESULTS, run_info, save_results
from score_realworld import wilson

ASSETS = Path("C:/projects/repolens-eval-assets/pygoat-blind")
UNSURE = re.compile(r"unsure|not sure|uncertain|unclear|\?|maybe|judg(e)?ment", re.I)


def norm(label: str) -> str | None:
    t = re.sub(r"\s+", " ", label.strip().lower().replace("_", " ").replace("-", " "))
    return {"real": "real", "not real": "not real"}.get(t)


def stat(findings: list[dict], mark) -> dict:
    n = len(findings)
    k = sum(1 for f in findings if mark(f) == "real")
    return {"real": k, "n": n, "precision": round(k / n, 2) if n else None,
            "wilson95": wilson(k, n)}


def main() -> None:
    received = json.loads(Path(sorted(glob.glob(str(RESULTS / "realworld_labels_received-*.json")))[-1])
                          .read_text(encoding="utf-8"))
    sheet_path = ASSETS / "sheet.csv"
    sha = hashlib.sha256(sheet_path.read_bytes()).hexdigest()
    if sha != received["sheet_sha256_labelled"]:
        sys.exit(f"labelled sheet changed since it was recorded ({sha})")
    rows = list(csv.DictReader(sheet_path.open(encoding="utf-8-sig")))
    key = json.loads((ASSETS / "key.json").read_text(encoding="utf-8"))
    labels, notes, bad = {}, {}, []
    for r in rows:
        lab = norm(r["label (real / not real)"])
        if lab is None:
            bad.append((r["id"], r["label (real / not real)"]))
        labels[r["id"]], notes[r["id"]] = lab, r["note"].strip()
    if bad or len(rows) != len(key["rows"]):
        sys.exit(f"unlabelled or unknown labels: {bad}; rows {len(rows)} vs key {len(key['rows'])}")
    unsure_ids = sorted(i for i, n in notes.items() if UNSURE.search(n))

    findings = {"RepoLens": [], "Bandit": []}
    for g in key["rows"]:
        for f in g["findings"]:
            findings[f["tool"]].append({**f, "id": g["id"], "path": g["path"], "line": g["line"],
                                        "category": g["category"], "label": labels[g["id"]],
                                        "unsure": g["id"] in unsure_ids,
                                        "merged_row": len({x["tool"] for x in g["findings"]}) > 1})
    out = {"labelled_sheet_sha256": sha, "rows": len(rows),
           "rows_real": sum(v == "real" for v in labels.values()),
           "rows_not_real": sum(v == "not real" for v in labels.values()),
           "rows_unsure_in_notes": len(unsure_ids), "unsure_ids": unsure_ids,
           "unsure_matcher": UNSURE.pattern, "tools": {}}
    for tool, fs in findings.items():
        per_rule = {}
        for f in fs:
            per_rule.setdefault(f["rule"], []).append(f)
        e = {"overall": stat(fs, lambda f: f["label"]),
             "unsure_findings": sum(f["unsure"] for f in fs),
             "range_if_unsure_all_real": stat(fs, lambda f: "real" if f["unsure"] else f["label"]),
             "range_if_unsure_all_not_real": stat(
                 fs, lambda f: "not real" if f["unsure"] else f["label"]),
             "per_rule": {r: stat(v, lambda f: f["label"]) for r, v in sorted(per_rule.items())},
             "findings": fs}
        if tool == "Bandit":
            e["overall_b104_as_real"] = stat(
                fs, lambda f: "real" if f["rule"].startswith("B104 ") else f["label"])
        out["tools"][tool] = e

    print(f"rows {out['rows']}: real {out['rows_real']}, not real {out['rows_not_real']};"
          f" unsure in notes {out['rows_unsure_in_notes']} {unsure_ids}")
    for tool, e in out["tools"].items():
        o = e["overall"]
        print(f"{tool}: {o['real']}/{o['n']} = {o['precision']} (95% {o['wilson95']});"
              f" unsure findings {e['unsure_findings']}: "
              f"{e['range_if_unsure_all_not_real']['real']}-{e['range_if_unsure_all_real']['real']}"
              f" real")
        if "overall_b104_as_real" in e:
            b = e["overall_b104_as_real"]
            print(f"  B104 as real: {b['real']}/{b['n']} = {b['precision']} (95% {b['wilson95']})")
        for r, s in e["per_rule"].items():
            print(f"  {r:<45} {s['real']}/{s['n']}")
    print("merged rows:", sum(1 for g in key["rows"]
                              if len({f['tool'] for f in g['findings']}) > 1))
    print("saved", save_results("realworld_precision_blind_scored", run_info(llm_used=False), out))


if __name__ == "__main__":
    main()
