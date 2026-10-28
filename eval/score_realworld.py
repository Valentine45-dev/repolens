"""Precision from hand-labelled samples (eval/realworld_precision.py output + a labels file).

    uv run --project backend python eval/score_realworld.py \\
        eval/results/realworld_precision-<...>.json eval/labels/<...>.yaml

Refuses to score unless the labels file says `confirmed: true`. Reports, per tool: overall
precision, precision per rule (the tool's own rule id), and for Bandit also with every B104
(bind to all interfaces) row counted as real instead of as labelled. Each figure comes with a
Wilson 95% interval, because the samples are small (n <= 20). Recall is not measured.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import yaml
from runinfo import RESULTS, run_info, save_results


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(centre - half, 2), round(centre + half, 2)]


def score(rows: list[dict]) -> dict:
    real = sum(r["label"] == "real" for r in rows)
    return {"real": real, "n": len(rows),
            "precision": round(real / len(rows), 2) if rows else None,
            "wilson95": wilson(real, len(rows))}


def labelled(sample: list[dict], labels: dict) -> list[dict]:
    rows = []
    for i, f in enumerate(sample, 1):
        lab = labels[i]
        if lab["label"] not in ("real", "false_alarm"):
            raise SystemExit(f"row {i}: unknown label {lab['label']!r}")
        rows.append({**f, "label": lab["label"], "reason": lab["reason"]})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("labels", type=Path)
    args = parser.parse_args()

    data = json.loads(args.results.read_text(encoding="utf-8"))
    labels = yaml.safe_load(args.labels.read_text(encoding="utf-8"))
    if labels.get("confirmed") is not True:
        raise SystemExit("labels are not confirmed; not scoring")

    out = {"source": {"samples": args.results.name, "labels": args.labels.name,
                      "repo": data["repo"], "sampling": data["sampling"],
                      "definition": labels["definition"]},
           "tools": {}}
    for tool, sample in data["samples"].items():
        rows = labelled(sample, labels[tool])
        per_rule: dict[str, list[dict]] = {}
        for r in rows:
            per_rule.setdefault(r["rule"], []).append(r)
        entry = {"overall": score(rows),
                 "population": data["population"][tool]["total"],
                 "per_rule": {rule: score(rs) for rule, rs in sorted(per_rule.items())},
                 "rows": rows}
        if tool == "Bandit":
            flipped = [{**r, "label": "real"} if r["rule"].startswith("B104 ") else r
                       for r in rows]
            entry["overall_b104_as_real"] = score(flipped)
        out["tools"][tool] = entry

    for tool, e in out["tools"].items():
        o = e["overall"]
        print(f"{tool}: {o['real']}/{o['n']} = {o['precision']} (95% {o['wilson95']})"
              f"  [population {e['population']}]")
        if "overall_b104_as_real" in e:
            b = e["overall_b104_as_real"]
            print(f"  B104 counted as real: {b['real']}/{b['n']} = {b['precision']}"
                  f" (95% {b['wilson95']})")
        for rule, s in e["per_rule"].items():
            print(f"  {rule:<45} {s['real']}/{s['n']} = {s['precision']}")
    info = run_info(llm_used=False)
    print("saved", save_results("realworld_precision_scored", info, out, RESULTS))


if __name__ == "__main__":
    sys.exit(main())
