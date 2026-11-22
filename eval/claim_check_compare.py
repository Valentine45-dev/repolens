"""Step 5 Part C: the claim check off vs on, on the tuning Q&A questions, and its adoption rule.

    uv run --project backend python eval/claim_check_compare.py <off.json> <on.json>

Inputs: two eval/smoke_qa.py --all result files (QA_CLAIM_CHECK=0 and =1), first results. Per
question: answered_correct_file (answerable: an expected file among the validated citations),
citation_validity (no dropped citation), cited sentences (the frozen eval/score_claims.py),
claims kept/removed, tokens and latency. Adoption rule (pre-registered in PROGRESS.md, 23 Nov):
on by default if, on these questions, the check loses no more questions than it wins on
answered_correct_file, the number of answers that are the "could not find" answer rises by at
most 2, and the median latency (smoke_qa's seconds_median) rises by at most 50%.
"""

import argparse
import json
import sys
from pathlib import Path

from runinfo import run_info, save_results  # also puts backend/ on sys.path
from score_claims import score_answer

COULD_NOT_FIND = "i could not find this in the provided code"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def could_not_find(answer: str) -> bool:
    return COULD_NOT_FIND in " ".join(answer.lower().split())


def per_question(row: dict) -> dict:
    s = score_answer(row)
    return {
        "type": row["type"], "status": row["status"],
        "answered_correct_file": row.get("expected_file_cited"),
        "citation_valid": row["dropped"] == 0, "citations": len(row["citations"]),
        "dropped": row["dropped"], "could_not_find": could_not_find(row["answer"]),
        "sentences": s["sentences"], "cited_sentences": s["cited_sentences"],
        "claims": row.get("claims"), "tokens_in": row["tokens_in"],
        "tokens_out": row["tokens_out"], "seconds": row["seconds"],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("off", type=Path)
    p.add_argument("on", type=Path)
    args = p.parse_args()
    off, on = load(args.off), load(args.on)
    a = {str(r["id"]): per_question(r) for r in off["questions"]}
    b = {str(r["id"]): per_question(r) for r in on["questions"]}
    if a.keys() != b.keys():
        sys.exit(f"different questions: {sorted(a.keys() ^ b.keys())}")
    ans = [q for q in a if a[q]["type"] == "answerable"]
    wins = [q for q in ans if b[q]["answered_correct_file"] and not a[q]["answered_correct_file"]]
    losses = [q for q in ans if a[q]["answered_correct_file"] and not b[q]["answered_correct_file"]]
    cnf_off = sum(a[q]["could_not_find"] for q in a)
    cnf_on = sum(b[q]["could_not_find"] for q in b)
    med_off = off["totals"]["seconds_median"]
    med_on = on["totals"]["seconds_median"]

    def totals(x: dict) -> dict:
        sent = sum(v["sentences"] for v in x.values())
        cited = sum(v["cited_sentences"] for v in x.values())
        return {
            "answered_correct_file": f"{sum(bool(x[q]['answered_correct_file']) for q in ans)}"
                                     f"/{len(ans)}",
            "citation_validity": f"{sum(v['citation_valid'] for v in x.values())}/{len(x)}",
            "cited_sentence_rate": f"{cited}/{sent} = {round(cited / sent, 3) if sent else None}",
            "could_not_find": sum(v["could_not_find"] for v in x.values()),
            "dropped": sum(v["dropped"] for v in x.values()),
            "tokens_in": sum(v["tokens_in"] for v in x.values()),
            "tokens_out": sum(v["tokens_out"] for v in x.values()),
        }

    claims = [v["claims"] for v in b.values() if v["claims"]]
    rule = {
        "answered_correct_file": {"wins": wins, "losses": losses,
                                  "ok": len(losses) <= len(wins)},
        "could_not_find": {"off": cnf_off, "on": cnf_on, "rise": cnf_on - cnf_off,
                           "ok": cnf_on - cnf_off <= 2},
        "median_latency_s": {"off": med_off, "on": med_on,
                             "rise": round(med_on / med_off - 1, 3) if med_off else None,
                             "ok": med_on <= 1.5 * med_off},
    }
    rule["adopt"] = all(v["ok"] for v in rule.values() if isinstance(v, dict))
    result = {
        "off_file": str(args.off), "on_file": str(args.on),
        "off": totals(a), "on": totals(b),
        "claims_on": {"answers_with_claims": len(claims),
                      "total": sum(c["total"] for c in claims),
                      "kept": sum(c["kept"] for c in claims),
                      "removed": sum(c["removed"] for c in claims)},
        "rule": rule, "per_question": {q: {"off": a[q], "on": b[q]} for q in a},
    }
    print(json.dumps({k: v for k, v in result.items() if k != "per_question"}, indent=2))
    for q in a:
        x, y = a[q], b[q]
        print(f"{q:>10} off: acf={x['answered_correct_file']!s:5} cites={x['citations']:>2}"
              f" drop={x['dropped']} cnf={x['could_not_find']!s:5} {x['seconds']:>5}s |"
              f" on: acf={y['answered_correct_file']!s:5} cites={y['citations']:>2}"
              f" drop={y['dropped']} cnf={y['could_not_find']!s:5} {y['seconds']:>5}s"
              f" claims={y['claims'] and (y['claims']['kept'], y['claims']['removed'])}")
    info = run_info(llm_used=False)
    info["notes"] = "compares two saved smoke_qa result files; no LLM"
    print("saved", save_results("claim_check_compare", info, result))


if __name__ == "__main__":
    main()
