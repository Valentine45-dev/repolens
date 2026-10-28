"""Retrieval recall@k, with and without 1-hop graph expansion. No LLM.

    uv run --project backend --env-file .env python eval/retrieval_recall.py
    uv run --project backend --env-file .env python eval/retrieval_recall.py --k 1 3 5 8

Questions and labels come from a YAML file (default eval/questions.yaml); each repo entry names
the URL and commit, and the matching analysed snapshot is looked up in the database (it must be
`done`). Retrieval is the same function /ask uses (app.qa.retrieve.retrieve), with test code
left out as in the product default.

Scoring, fixed before the first run (see questions.yaml): a question is a hit at k if any
snippet retrieved with that k overlaps any labelled range of the same path. "Without
expansion" is the top-k search hits; "with expansion" is what /ask would send for that k: the
top-k hits plus their graph neighbours. Unanswerable questions are listed but not scored.
"""

import argparse
import sys
from pathlib import Path

import yaml
from runinfo import ROOT, header, run_info, save_results  # also puts backend/ on sys.path

from app import db  # noqa: E402
from app.qa.retrieve import retrieve  # noqa: E402


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start <= b_end and b_start <= a_end


def is_hit(snippets, expected: list[dict]) -> bool:
    """Any retrieved snippet overlapping any labelled range of the same path."""
    return any(
        s.path == e["path"] and overlaps(s.start_line, s.end_line, e["start"], e["end"])
        for s in snippets for e in expected
    )


def first_hit_rank(snippets, expected: list[dict]) -> int | None:
    for rank, s in enumerate(snippets, start=1):
        if is_hit([s], expected):
            return rank
    return None


def load_questions(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["repos"]


def snapshot_for(repo: dict) -> int:
    with db.pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id, st.status FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE r.url = %s AND s.commit_sha = %s",
            (repo["url"], repo["commit"]),
        ).fetchone()
    if row is None or row["status"] != "done":
        sys.exit(f"{repo['name']}: no finished analysis of {repo['url']} at {repo['commit']}."
                 " Analyse that commit first.")
    return row["id"]


def evaluate(repos: list[dict], ks: list[int]) -> dict:
    rows = []
    for repo in repos:
        snapshot_id = snapshot_for(repo)
        for q in repo["questions"]:
            row = {"repo": repo["name"], "snapshot_id": snapshot_id, "id": q["id"],
                   "question": q["question"], "unanswerable": bool(q.get("unanswerable"))}
            if row["unanswerable"]:
                top = retrieve(snapshot_id, q["question"], k=max(ks), expand=False)
                row["top_paths"] = [
                    f"{s.path}:{s.start_line}-{s.end_line}" for s in top.snippets[:3]
                ]
                rows.append(row)
                continue
            expected = q["expected"]
            ranked = retrieve(snapshot_id, q["question"], k=max(ks), expand=False)
            row["first_hit_rank"] = first_hit_rank(ranked.snippets, expected)
            row["hits"] = {}
            for k in ks:
                plain = retrieve(snapshot_id, q["question"], k=k, expand=False)
                expanded = retrieve(snapshot_id, q["question"], k=k, expand=True)
                row["hits"][k] = {
                    "plain": is_hit(plain.snippets, expected),
                    "expanded": is_hit(expanded.snippets, expected),
                    "sent_expanded": len(expanded.snippets),
                }
            row["used_test_code"] = ranked.used_test_code
            rows.append(row)
    return {"questions": rows, "summary": summarise(rows, ks)}


def summarise(rows: list[dict], ks: list[int]) -> dict:
    scored = [r for r in rows if not r["unanswerable"]]
    groups = {"all": scored}
    for name in sorted({r["repo"] for r in scored}):
        groups[name] = [r for r in scored if r["repo"] == name]
    out = {}
    for name, group in groups.items():
        n = len(group)
        ranks = [r["first_hit_rank"] for r in group]
        out[name] = {
            "questions": n,
            "recall": {
                str(k): {
                    "plain": sum(r["hits"][k]["plain"] for r in group) / n,
                    "expanded": sum(r["hits"][k]["expanded"] for r in group) / n,
                }
                for k in ks
            },
            "mrr_plain": sum(1 / r for r in ranks if r) / n,
        }
    return out


def print_table(results: dict, ks: list[int]) -> None:
    print(f"{'set':<14}{'n':>3}  " + "  ".join(f"R@{k} plain/+graph" for k in ks) + "   MRR")
    for name, s in results["summary"].items():
        cells = "  ".join(
            f"{s['recall'][str(k)]['plain']:>8.2f} /{s['recall'][str(k)]['expanded']:>5.2f} "
            for k in ks
        )
        print(f"{name:<14}{s['questions']:>3}  {cells}  {s['mrr_plain']:.2f}")
    print()
    for r in results["questions"]:
        if r["unanswerable"]:
            print(f"Q{r['id']:>2} unanswerable; top: {', '.join(r['top_paths'])}")
            continue
        marks = " ".join(
            f"@{k}:{'Y' if h['plain'] else '-'}{'Y' if h['expanded'] else '-'}"
            for k, h in r["hits"].items()
        )
        print(f"Q{r['id']:>2} first hit rank {r['first_hit_rank'] or '-':>2}  {marks}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "questions.yaml")
    parser.add_argument("--k", type=int, nargs="+", default=[1, 3, 5, 8])
    args = parser.parse_args()

    db.open_pool()
    try:
        info = run_info(llm_used=False)
        print(header(info))
        results = evaluate(load_questions(args.questions), sorted(args.k))
        results["questions_file"] = str(args.questions.relative_to(ROOT))
        print_table(results, sorted(args.k))
        print("\nsaved", save_results("retrieval_recall", info, results))
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
