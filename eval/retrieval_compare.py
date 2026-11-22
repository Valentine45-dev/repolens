"""Are two retrieval_recall.py result files the same? Configs, summary and every question record.

    uv run --project backend python eval/retrieval_compare.py <before.json> <after.json>

Run info (commit, time, machine) is not compared. Exit 1 if anything else differs.
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    p.add_argument("--configs", default="",
                   help="e.g. A,B,C: compare only these configurations' per-question records"
                        " (and first-hit rank) over the questions in BEFORE; summaries skipped")
    args = p.parse_args()
    a, b = (json.loads(f.read_text(encoding="utf-8")) for f in (args.before, args.after))
    only = [c for c in args.configs.split(",") if c]
    same = True
    qa = {(q["repo"], q["id"]): q for q in a.get("questions", [])}
    qb = {(q["repo"], q["id"]): q for q in b.get("questions", [])}
    if only:
        def part(q):
            return {k: v for k, v in q.items() if k != "configs"} | {
                "configs": {c: q.get("configs", {}).get(c) for c in only}}
        qa = {k: part(q) for k, q in qa.items()}
        qb = {k: part(q) for k, q in qb.items() if k in qa}
    else:
        for key in ("configs", "summary"):
            if a.get(key) != b.get(key):
                print(f"{key}: differ")
                same = False
    if qa.keys() != qb.keys():
        print("question sets differ:", sorted(qa.keys() ^ qb.keys()))
        same = False
    for k in sorted(qa.keys() & qb.keys()):
        if qa[k] != qb[k]:
            print(f"question {k}: differs")
            same = False
    print("identical" if same else "DIFFERENT", f"({len(qa)} questions)")
    sys.exit(0 if same else 1)


if __name__ == "__main__":
    main()
