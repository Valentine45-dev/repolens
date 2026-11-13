"""J1 vs J3 agreement on the 30-row call-calibration judge sheet
(eval/results/CALL-CALIBRATION-J3-PLAN.md, Step 2 item 5; run once).

    uv run --project backend --env-file .env python eval/call_calibration_j3_agreement.py

Reports: (1) percent agreement and Cohen's kappa on correct / incorrect / unsure, 30 rows;
(2) the same on correct vs incorrect only, rows where either judge said unsure excluded (count
stated); the kappa < 0.4 flag for each; every disagreement and every unsure row; then J3's label
counts per confidence band (descriptive only). Refuses to run unless J3's sheet has the SHA-256
committed in eval/results/call_calibration_labels_received_j3-*.json and that check passed.
Writes eval/results/call_calibration_j3_agreement-<time>-<sha7>.json.
"""

import csv
import glob
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from runinfo import ROOT, header, run_info, save_results

ASSETS = Path(r"C:\projects\repolens-eval-assets\call-calibration")
J1_SHA256 = "672a3559991f218486d05eea9ffe12c2e4700120f44028f65851078c4bd19c34"
KAPPA_FLAG = 0.4
LABEL_COL, NOTE_COL = 8, 9
CATS3 = ["correct", "incorrect", "unsure"]
CATS2 = ["correct", "incorrect"]


def read(path: Path) -> dict[str, list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    return {r[0].strip(): r for r in rows[1:]}


def agreement(pairs: list[tuple[str, str]], cats: list[str]) -> dict:
    """pairs: (J1, J3). Kappa over the categories either judge used; undefined when chance is 1."""
    n = len(pairs)
    if n == 0:
        return {"n": 0, "kappa": None, "kappa_note": "undefined: no rows"}
    used = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    agree = sum(1 for a, b in pairs if a == b)
    observed = agree / n
    j1, j3 = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum((j1[c] / n) * (j3[c] / n) for c in used)
    kappa = None if chance >= 1 else (observed - chance) / (1 - chance)
    return {
        "n": n, "agree": agree, "percent_agreement": round(observed, 4),
        "chance_agreement": round(chance, 4),
        "kappa": None if kappa is None else round(kappa, 4),
        "kappa_note": "undefined: chance agreement is 1" if kappa is None else None,
        "kappa_below_0.4": None if kappa is None else kappa < KAPPA_FLAG,
        "j1_counts": {c: j1[c] for c in cats}, "j3_counts": {c: j3[c] for c in cats},
        "table_rows_j1_cols_j3": {f"J1 {a}": {f"J3 {b}": sum(1 for x, y in pairs if (x, y) == (a, b))
                                              for b in cats} for a in cats},
    }


def lab(r: list[str]) -> str:
    return r[LABEL_COL].strip().lower()


def main() -> None:
    rec_path = max(glob.glob(str(ROOT / "eval" / "results" / "call_calibration_labels_received_j3-*.json")))
    rel = Path(rec_path).relative_to(ROOT).as_posix()
    committed = subprocess.run(["git", "show", f"HEAD:{rel}"], check=False, cwd=ROOT, capture_output=True,
                               text=True, encoding="utf-8")
    if committed.returncode != 0:
        raise SystemExit(f"{rel} is not committed.")
    received = json.loads(committed.stdout)
    if not received["checks"]["passed"]:
        raise SystemExit("The committed check of J3's sheet did not pass.")
    j3_path = ASSETS / "sheet-labelled-judge3.csv"
    if hashlib.sha256(j3_path.read_bytes()).hexdigest() != received["sha256"]:
        raise SystemExit("J3's sheet is not the one whose hash was committed.")
    j1_path = ASSETS / "sheet-labelled.csv"
    if hashlib.sha256(j1_path.read_bytes()).hexdigest() != J1_SHA256:
        raise SystemExit("J1's sheet is not the one whose hash was recorded.")

    j1, j3 = read(j1_path), read(j3_path)
    with (ASSETS / "key.json").open(encoding="utf-8") as fh:
        key = json.load(fh)
    band_of = {r["id"]: r["band"] for r in key["main"]}
    ids = list(j3)
    if sorted(ids) != sorted(key["judge2_ids"]) or any(i not in j1 for i in ids):
        raise SystemExit("J3's ids do not match the judge-2 ids or J1's sheet.")

    pairs3 = [(lab(j1[i]), lab(j3[i])) for i in ids]
    excluded = [i for i in ids if "unsure" in (lab(j1[i]), lab(j3[i]))]
    pairs2 = [(lab(j1[i]), lab(j3[i])) for i in ids if i not in excluded]
    three, two = agreement(pairs3, CATS3), agreement(pairs2, CATS2)

    def row(i: str) -> dict:
        return {"id": i, "repo": j3[i][1], "band": band_of[i], "call_site": j3[i][2],
                "callee": j3[i][5], "j1": lab(j1[i]), "j3": lab(j3[i]),
                "j3_note": j3[i][NOTE_COL].strip(), "j1_note": j1[i][NOTE_COL].strip()}

    disagreements = [row(i) for i in ids if lab(j1[i]) != lab(j3[i])]
    unsure_rows = [row(i) for i in excluded]
    per_band = {}
    for band in (1.0, 0.9, 0.5):
        b_ids = [i for i in ids if band_of[i] == band]
        c = Counter(lab(j3[i]) for i in b_ids)
        per_band[str(band)] = {"rows": len(b_ids), **{f"j3_{k}": c[k] for k in CATS3}}

    results = {
        "plan": "eval/results/CALL-CALIBRATION-J3-PLAN.md (with Amendment 1)",
        "j3_sheet_sha256": received["sha256"], "j1_sheet_sha256": J1_SHA256,
        "judge": "J3", "ai_use": received["ai_use"],
        "normalisations": received["normalisations"],
        "rows": len(ids),
        "three_categories": three,
        "correct_vs_incorrect": {**two, "excluded_rows_either_unsure": len(excluded),
                                 "excluded_ids": excluded},
        "kappa_flag_threshold": KAPPA_FLAG,
        "disagreements": disagreements,
        "unsure_rows": unsure_rows,
        "j3_per_band_descriptive": per_band,
        "note": "Per-band counts are descriptive only: no intervals, no test. J1's labels and "
                "CALL-CALIBRATION.md are unchanged.",
    }
    info = run_info(llm_used=False)
    print(header(info))
    print("saved", save_results("call_calibration_j3_agreement", info, results))
    for name, r in (("three categories", three), ("correct vs incorrect", two)):
        print(name, {k: r.get(k) for k in ("n", "agree", "percent_agreement", "kappa", "kappa_note",
                                           "kappa_below_0.4")})
    print("excluded (either unsure):", len(excluded), "| disagreements:", len(disagreements))
    print("per band:", per_band)


if __name__ == "__main__":
    main()
