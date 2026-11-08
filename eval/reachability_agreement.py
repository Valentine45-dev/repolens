"""Agreement between the two judges on the judge-2 subset (pre-registration section 8, section 10):
percent agreement and Cohen's kappa on `label`, with unsure as its own category, per repo and pooled;
the disagreeing rows; and the judge-dependent flag (kappa below 0.4).

    uv run --project backend --env-file .env python eval/reachability_agreement.py

Reads J1's sheet (sheet-labelled.csv), J2's sheet (sheet-labelled-judge2.csv) and the key (only for the
rule of each disagreeing row). Refuses to run unless J2's sheet has the SHA-256 committed in
eval/results/reachability_labels_received_judge2-*.json. Run once; writes
eval/results/reachability_agreement-<time>-<sha7>.json.
"""

import csv
import glob
import hashlib
import json
from collections import Counter
from pathlib import Path

import reachability_guard
from runinfo import ROOT, header, run_info, save_results

ASSETS = Path(r"C:\projects\repolens-eval-assets\reachability")
KAPPA_FLAG = 0.4
NOTE_LIMIT = 600


def read(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.reader(fh))


def agreement(pairs: list[tuple[str, str]]) -> dict:
    """pairs: (J1 label, J2 label). Cohen's kappa over the categories seen; undefined when chance
    agreement is 1 (both judges used one and the same single category)."""
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    cats = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    observed = sum(1 for a, b in pairs if a == b) / n
    j1, j2 = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    chance = sum((j1[c] / n) * (j2[c] / n) for c in cats)
    kappa = None if chance >= 1 else (observed - chance) / (1 - chance)
    return {
        "n": n, "agree": sum(1 for a, b in pairs if a == b), "percent_agreement": round(observed, 4),
        "chance_agreement": round(chance, 4), "kappa": None if kappa is None else round(kappa, 4),
        "kappa_note": "undefined: chance agreement is 1" if kappa is None else None,
        "j1_counts": dict(j1), "j2_counts": dict(j2),
        "table": dict(Counter(f"J1 {a} | J2 {b}" for a, b in pairs)),
    }


def main() -> None:
    facts = reachability_guard.check()
    received = json.load(open(sorted(glob.glob(str(
        ROOT / "eval" / "results" / "reachability_labels_received_judge2-*.json")))[-1], encoding="utf-8"))
    path2 = ASSETS / "sheet-labelled-judge2.csv"
    if hashlib.sha256(path2.read_bytes()).hexdigest() != received["sha256"]:
        raise SystemExit("J2's sheet is not the one whose hash was committed.")
    j1_rows = {r[0]: r for r in read(ASSETS / "sheet-labelled.csv")[1:]}
    j2_rows = {r[0]: r for r in read(path2)[1:]}
    key = json.load(open(ASSETS / "key.json", encoding="utf-8"))
    by_id = {r["id"]: r for r in key["rows"]}
    ids = sorted(j2_rows)
    label = lambda r: r[6].strip().lower()  # noqa: E731

    per_repo: dict[str, list[tuple[str, str]]] = {}
    for i in ids:
        per_repo.setdefault(j2_rows[i][1], []).append((label(j1_rows[i]), label(j2_rows[i])))
    pooled = [p for pairs in per_repo.values() for p in pairs]
    pooled_result = agreement(pooled)

    disagreements = []
    for i in ids:
        a, b = label(j1_rows[i]), label(j2_rows[i])
        if a != b:
            note = j2_rows[i][7].strip()
            disagreements.append({
                "id": i, "repo": j2_rows[i][1], "j1": a, "j2": b,
                "flagged_for": j2_rows[i][4],
                "rules": sorted({f["rule"] for f in by_id[i]["findings"]}),
                "tools": sorted({f["tool"] for f in by_id[i]["findings"]}),
                "j2_note": note[:NOTE_LIMIT] + (" [cut]" if len(note) > NOTE_LIMIT else ""),
                "j1_note": j1_rows[i][7].strip(),
            })
    kappa = pooled_result["kappa"]
    results = {
        "guard": facts, "judge2_sheet_sha256": received["sha256"],
        "instructions_record": received["instructions_record"], "ai_use": received["ai_use"],
        "rows": len(ids), "unsure_rows": sum(1 for p in pooled for x in p if x == "unsure"),
        "three_way_equals_binary": all(x in ("real", "not real") for p in pooled for x in p),
        "pooled": pooled_result,
        "per_repo": {r: agreement(pairs) for r, pairs in sorted(per_repo.items())},
        "kappa_flag_threshold": KAPPA_FLAG,
        "judge_dependent": None if kappa is None else kappa < KAPPA_FLAG,
        "disagreements": disagreements,
        "j2_real_rows_also_real_for_j1": sum(1 for a, b in pooled if b == "real" and a == "real"),
        "primary_table_repeated_on_the_j2_subset": False,
        "note": "The pre-registration (section 10) asks for the primary table to be repeated on the J2 subset "
                "with both judges' labels when kappa is below 0.4; not done here (not requested).",
    }
    info = run_info(llm_used=False)
    print(header(info))
    print("saved", save_results("reachability_agreement", info, results))
    print("pooled", {k: pooled_result[k] for k in ("n", "agree", "percent_agreement", "kappa")},
          "| judge_dependent", results["judge_dependent"], "| disagreements", len(disagreements))
    for r, v in results["per_repo"].items():
        print(" ", r, {k: v[k] for k in ("n", "agree", "percent_agreement", "kappa")})


if __name__ == "__main__":
    main()
