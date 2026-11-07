"""Score the call-confidence calibration exactly as pre-registered (eval/call_calibration_rule.md).

    uv run --project backend python eval/score_call_calibration.py

Refuses to run unless both labelled sheets match the SHA-256 recorded in
eval/results/call_calibration_labels_received-*.json (committed before the key was opened).
Primary result: precision with unsure excluded, correct / (correct + incorrect), per band, Wilson
95%; unsure-as-incorrect and unsure-as-correct are shown alongside. Main sheet and the express
add-on are scored separately. This is precision of drawn call edges only, not recall.
"""

import csv
import glob
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from runinfo import RESULTS, run_info, save_results
from score_realworld import wilson

ASSETS = Path(r"C:\projects\repolens-eval-assets\call-calibration")
LABEL = "label (correct / incorrect / unsure)"
BANDS = ("1.0", "0.9", "0.5")


def read(name: str) -> dict[str, dict]:
    rows = list(csv.DictReader((ASSETS / name).open(encoding="utf-8-sig")))
    return {r["id"]: r for r in rows}


def norm(x: str) -> str | None:
    return {"correct": "correct", "incorrect": "incorrect", "unsure": "unsure"}.get(x.strip().lower())


def precision(k: int, n: int) -> dict:
    return {"correct": k, "n": n, "precision": round(k / n, 2) if n else None, "wilson95": wilson(k, n)}


def band_stats(rows: list[dict]) -> dict:
    c = Counter(r["label"] for r in rows)
    ok, bad, uns = c["correct"], c["incorrect"], c["unsure"]
    return {
        "rows": len(rows), "correct": ok, "incorrect": bad, "unsure": uns,
        "primary_unsure_excluded": precision(ok, ok + bad),
        "unsure_as_incorrect": precision(ok, ok + bad + uns),
        "unsure_as_correct": precision(ok + uns, ok + bad + uns),
        "distinct_callees": len({r["callee_symbol_id"] for r in rows}),
        "distinct_caller_files": len({r["call site"].rsplit(":", 1)[0] for r in rows}),
        "distinct_callee_files": len({r["callee location"].rsplit(":", 1)[0] for r in rows}),
    }


def score(sheet: str, key_rows: list[dict]) -> dict:
    labelled = read(sheet)
    key_ids = {r["id"] for r in key_rows}
    labels = {i: norm(r[LABEL]) for i, r in labelled.items()}
    bad = {i: labelled[i][LABEL] for i, v in labels.items() if v is None}
    if bad or set(labelled) != key_ids:
        sys.exit(f"{sheet}: unknown labels {bad}; id mismatch {set(labelled) ^ key_ids}")
    rows = [{**r, "label": labels[r["id"]], "note": labelled[r["id"]]["note"].strip()}
            for r in key_rows]
    out = {"sheet": sheet, "rows": len(rows),
           "per_band": {b: band_stats([r for r in rows if f"{r['band']}" == b]) for b in BANDS},
           "per_repo_band": {},
           "unsure_rows": [{"id": r["id"], "repo": r["repo"], "band": r["band"],
                            "call site": r["call site"], "callee": r["callee"], "note": r["note"]}
                           for r in rows if r["label"] == "unsure"],
           "unsure_without_note": [r["id"] for r in rows if r["label"] == "unsure" and not r["note"]]}
    for repo in sorted({r["repo"] for r in rows}):
        for b in BANDS:
            sub = [r for r in rows if r["repo"] == repo and f"{r['band']}" == b]
            if sub:
                c = Counter(r["label"] for r in sub)
                out["per_repo_band"][f"{repo} {b}"] = {"rows": len(sub), **{k: c[k] for k in
                                                       ("correct", "incorrect", "unsure")}}
    out["incorrect_rows"] = [{"id": r["id"], "repo": r["repo"], "band": r["band"],
                              "call site": r["call site"], "callee": r["callee"], "note": r["note"]}
                             for r in rows if r["label"] == "incorrect"]
    if any("in_test" in r for r in rows):
        out["express_in_test_or_example"] = {
            b: {"in_test": sum(bool(r["in_test"]) for r in rows if f"{r['band']}" == b),
                "rows": sum(f"{r['band']}" == b for r in rows)} for b in BANDS}
    return out


def main() -> None:
    got = json.loads(Path(sorted(glob.glob(str(RESULTS / "call_calibration_labels_received-*.json")))[-1])
                     .read_text(encoding="utf-8"))
    for name, want in (("sheet-labelled.csv", got["sheet_labelled_sha256"]),
                       ("sheet-labelled-express.csv", got["sheet_labelled_express_sha256"])):
        have = hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
        if have != want:
            sys.exit(f"{name} changed since its hash was recorded ({have})")
    key = json.loads((ASSETS / "key.json").read_text(encoding="utf-8"))
    for r in key["main"] + key["express"]:
        r["band"] = f"{r['band']}"
    results = {"labelled_sha256": {"main": got["sheet_labelled_sha256"],
                                   "express": got["sheet_labelled_express_sha256"]},
               "measures": "precision of drawn call edges only, not recall",
               "main": score("sheet-labelled.csv", key["main"]),
               "express": score("sheet-labelled-express.csv", key["express"])}
    for part in ("main", "express"):
        print(part)
        for b, s in results[part]["per_band"].items():
            p = s["primary_unsure_excluded"]
            print(f"  {b}: correct {s['correct']} incorrect {s['incorrect']} unsure {s['unsure']} | "
                  f"primary {p['correct']}/{p['n']} = {p['precision']} {p['wilson95']} | "
                  f"unsure=incorrect {s['unsure_as_incorrect']['precision']} "
                  f"{s['unsure_as_incorrect']['wilson95']} | unsure=correct "
                  f"{s['unsure_as_correct']['precision']} {s['unsure_as_correct']['wilson95']} | "
                  f"callees {s['distinct_callees']} files {s['distinct_caller_files']}/"
                  f"{s['distinct_callee_files']}")
        for k, v in results[part]["per_repo_band"].items():
            print("   ", k, v)
    print("saved", save_results("call_calibration_scored", run_info(llm_used=False), results))


if __name__ == "__main__":
    main()
