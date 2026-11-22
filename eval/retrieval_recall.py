"""Retrieval recall over the full context /ask would send to the LLM. No LLM.

    uv run --project backend --env-file .env python eval/retrieval_recall.py [--label name]

Configurations (same questions, same scoring):
    A  search top 8
    B  search top 16
    C  search top 8 + graph expansion (up to 8 more, so up to 16)
    D  hybrid (keyword + vector, reciprocal rank fusion) top 8
    DG hybrid top 8 + graph expansion (8)
Expansion helps only if C beats B: the same number of chunks spent on search alone.
A, B and C pass hybrid=False, so they mean what they meant before hybrid search existed.

--tuning-locked FILE adds that file's code_how and locate questions (eval/tuning_locked_format.yaml
format; `source: code` ranges only), so the summary covers both sets. Paired comparisons (wins,
losses, exact two-sided sign test) use eval/locked_metrics.paired.

--doc-ladder (Step 5 Part A, rule fixed in PROGRESS.md before the run): in the live configuration
(LIVE, the product defaults) with the default doc pool, for each doc cutoff rank in DOC_LADDER:
doc-leak = share of the code_how questions (v1 questions and the tuning file's code_how) with at
least one doc chunk sent; doc_hit = per purpose question of the tuning file, whether a sent doc
chunk overlaps a `source: doc` range. Code is checked to be the same at every rung.

Questions and labels come from a YAML file (default eval/questions.yaml); each repo entry names
the URL and commit, and the matching analysed snapshot is looked up in the database (it must be
`done`). Retrieval is the same function /ask uses (app.qa.retrieve.retrieve), with test code
left out as in the product default, and the same context budget.

Scoring, fixed before the first run (see questions.yaml): a question is a hit if any chunk in
the context overlaps any labelled range of the same path. Unanswerable questions are listed but
not scored. The first-hit rank is taken from B's search order (1..16).
"""

import argparse
import sys
from pathlib import Path

import yaml
from runinfo import ROOT, header, run_info, save_results  # also puts backend/ on sys.path

from app import db  # noqa: E402
from app.qa.retrieve import retrieve  # noqa: E402

CONFIGS = {
    "A": {"k": 8, "expand": False, "expand_max": 0, "hybrid": False},
    "B": {"k": 16, "expand": False, "expand_max": 0, "hybrid": False},
    "C": {"k": 8, "expand": True, "expand_max": 8, "hybrid": False},
    "D": {"k": 8, "expand": False, "expand_max": 0, "hybrid": True},
    "DG": {"k": 8, "expand": True, "expand_max": 8, "hybrid": True},
}
PAIRS = [("C", "B"), ("C", "A"), ("B", "A"), ("DG", "C"), ("DG", "D"), ("D", "A")]
CODE_TYPES = ("code_how", "locate")
DOC_LADDER = (8, 6, 4, 2, 1)  # loosest first; the rule adopts the loosest with leak <= 30%
LEAK_BAR = 0.30


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


def load_tuning_locked(path: Path) -> list[dict]:
    """The locked-format tuning file as repo entries: code_how and locate questions only, with
    their `source: code` ranges (code_hit's definition)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    repos: dict[tuple[str, str], dict] = {}
    for q in data["questions"]:
        if q["type"] not in CODE_TYPES:
            continue
        key = (q["repo"], q["commit"])
        repo = repos.setdefault(key, {"name": q["repo"], "url": f"https://github.com/{q['repo']}",
                                      "commit": q["commit"], "questions": []})
        repo["questions"].append({
            "id": q["id"], "question": q["question"], "type": q["type"],
            "expected": [{"path": e["path"], "start": e["start"], "end": e["end"]}
                         for e in q["expected"] if e["source"] == "code"],
        })
    return list(repos.values())


def snapshot_for(repo: dict) -> int:
    with db.pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id, st.status FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE lower(r.url) = lower(%s) AND s.commit_sha = %s",
            (repo["url"], repo["commit"]),
        ).fetchone()
    if row is None or row["status"] != "done":
        sys.exit(f"{repo['name']}: no finished analysis of {repo['url']} at {repo['commit']}."
                 " Analyse that commit first.")
    return row["id"]


def evaluate(repos: list[dict]) -> dict:
    rows = []
    for repo in repos:
        snapshot_id = snapshot_for(repo)
        for q in repo["questions"]:
            row = {"repo": repo["name"], "snapshot_id": snapshot_id, "id": q["id"],
                   "question": q["question"], "unanswerable": bool(q.get("unanswerable"))}
            contexts = {name: retrieve(snapshot_id, q["question"], **cfg)
                        for name, cfg in CONFIGS.items()}
            if row["unanswerable"]:
                row["top_paths"] = [f"{s.path}:{s.start_line}-{s.end_line}"
                                    for s in contexts["A"].snippets[:3]]
                rows.append(row)
                continue
            expected = q["expected"]
            row["first_hit_rank"] = first_hit_rank(contexts["B"].snippets, expected)
            row["configs"] = {
                name: {
                    "hit": is_hit(ctx.snippets, expected),
                    "sent": len(ctx.snippets),
                    "from_graph": sum(1 for s in ctx.snippets if s.via == "graph"),
                    "hit_from_graph": is_hit([s for s in ctx.snippets if s.via == "graph"],
                                             expected),
                }
                for name, ctx in contexts.items()
            }
            rows.append(row)
    return {"configs": CONFIGS, "questions": rows, "summary": summarise(rows),
            "comparisons": compare(rows)}


def _ranges(snippets, via: str | None = None) -> list[str]:
    return [f"{s.path}:{s.start_line}-{s.end_line}" for s in snippets if via is None or s.via == via]


def doc_ladder(v1_repos: list[dict], tuning_file: Path | None) -> dict:
    """Doc-leak and doc_hit for each rung of DOC_LADDER, in the live configuration."""
    from app import config

    code_how = []  # (repo name, question id, question, snapshot)
    for repo in v1_repos:
        sid = snapshot_for(repo)
        code_how += [(repo["name"], q["id"], q["question"], sid) for q in repo["questions"]
                     if not q.get("unanswerable")]
    purpose = []  # (repo, id, question, snapshot, doc ranges)
    if tuning_file:
        data = yaml.safe_load(tuning_file.read_text(encoding="utf-8"))
        for q in data["questions"]:
            if q["type"] not in ("code_how", "purpose"):
                continue
            sid = snapshot_for({"name": q["repo"], "url": f"https://github.com/{q['repo']}",
                                "commit": q["commit"]})
            if q["type"] == "code_how":
                code_how.append((q["repo"], q["id"], q["question"], sid))
            else:
                purpose.append((q["repo"], q["id"], q["question"], sid,
                                [e for e in q["expected"] if e["source"] == "doc"]))
    out = {"pool": config.QA_DOC_POOL, "live": "product defaults", "bar": LEAK_BAR, "rungs": {}}
    for rank in DOC_LADDER:
        rung = {"code_how": [], "purpose": []}
        for name, qid, text, sid in code_how:
            r = retrieve(sid, text, doc_cutoff_rank=rank)
            off = retrieve(sid, text, doc_pool=0)
            rung["code_how"].append({
                "q": f"{name}#{qid}", "docs_sent": _ranges(r.snippets, "doc"),
                "code_same_as_pool_0": _ranges([s for s in r.snippets if s.via != "doc"])
                == _ranges(off.snippets)})
        for name, qid, text, sid, wanted in purpose:
            r = retrieve(sid, text, doc_cutoff_rank=rank)
            docs = [s for s in r.snippets if s.via == "doc"]
            rung["purpose"].append({"q": f"{name}#{qid}", "docs_sent": _ranges(docs),
                                    "doc_hit": is_hit(docs, wanted) if wanted else None})
        n = len(rung["code_how"])
        leaked = sum(1 for x in rung["code_how"] if x["docs_sent"])
        rung["doc_leak"] = {"questions": n, "with_doc": leaked,
                            "rate": round(leaked / n, 3) if n else None}
        rung["doc_hit"] = {"questions": len(rung["purpose"]),
                           "hits": sum(1 for x in rung["purpose"] if x["doc_hit"])}
        rung["code_unchanged"] = all(x["code_same_as_pool_0"] for x in rung["code_how"])
        out["rungs"][str(rank)] = rung
    passing = [r for r in DOC_LADDER if out["rungs"][str(r)]["doc_leak"]["rate"] is not None
               and out["rungs"][str(r)]["doc_leak"]["rate"] <= LEAK_BAR]
    out["adopted_rank"] = passing[0] if passing else None  # loosest that meets the bar
    return out


def compare(rows: list[dict]) -> dict:
    """Paired hit/miss per question for each pair of configurations, with the questions named."""
    from locked_metrics import paired  # the frozen scorer's own sign test

    scored = [r for r in rows if not r["unanswerable"]]
    out = {}
    for x, y in PAIRS:
        hx = {f"{r['repo']}#{r['id']}": r["configs"][x]["hit"] for r in scored}
        hy = {f"{r['repo']}#{r['id']}": r["configs"][y]["hit"] for r in scored}
        out[f"{x} vs {y}"] = {
            **paired(hx, hy),
            "won": sorted(i for i in hx if hx[i] and not hy[i]),
            "lost": sorted(i for i in hx if hy[i] and not hx[i]),
        }
    return out


def summarise(rows: list[dict]) -> dict:
    scored = [r for r in rows if not r["unanswerable"]]
    groups = {"all": scored}
    for name in sorted({r["repo"] for r in scored}):
        groups[name] = [r for r in scored if r["repo"] == name]
    out = {}
    for name, group in groups.items():
        n = len(group)
        out[name] = {
            "questions": n,
            "recall": {c: sum(r["configs"][c]["hit"] for r in group) / n for c in CONFIGS},
            "mrr_search_16": sum(1 / r["first_hit_rank"] for r in group
                                 if r["first_hit_rank"]) / n,
        }
    return out


def print_table(results: dict) -> None:
    print(f"{'set':<22}{'n':>3}" + "".join(f"{c:>7}" for c in CONFIGS) + "   MRR@16")
    for name, s in results["summary"].items():
        r = s["recall"]
        print(f"{name:<22}{s['questions']:>3}" + "".join(f"{r[c]:>7.2f}" for c in CONFIGS)
              + f"   {s['mrr_search_16']:>6.2f}")
    print()
    for r in results["questions"]:
        if r["unanswerable"]:
            print(f"Q{r['id']!s:>3} unanswerable; top: {', '.join(r['top_paths'])}")
            continue
        cells = "  ".join(
            f"{c}:{'Y' if v['hit'] else '-'}{'*' if v['hit_from_graph'] else ' '}"
            f"({v['sent']:>2})" for c, v in r["configs"].items()
        )
        print(f"Q{r['id']!s:>3} rank {r['first_hit_rank'] or '-':>2}  {cells}")
    print("\n(n) = chunks sent; * = a graph-added chunk overlaps a label\n")
    for pair, c in results["comparisons"].items():
        print(f"{pair:<9} wins {c['wins']} losses {c['losses']} (of {c['questions']})"
              f"  p = {c['p_mcnemar_exact']}  won {c['won']} lost {c['lost']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--questions", type=Path, default=ROOT / "eval" / "questions.yaml")
    parser.add_argument("--tuning-locked", type=Path, default=None,
                        help="also score this locked-format file's code_how/locate questions")
    parser.add_argument("--label", default="", help="name for this run, e.g. baseline")
    parser.add_argument("--doc-ladder", action="store_true",
                        help="only the Part A doc cutoff ladder (doc-leak, doc_hit)")
    args = parser.parse_args()
    if args.doc_ladder:
        db.open_pool()
        try:
            info = run_info(llm_used=False)
            info["label"] = args.label
            print(header(info), f"| {args.label}" if args.label else "")
            res = doc_ladder(load_questions(args.questions), args.tuning_locked)
            for rank, rung in res["rungs"].items():
                print(f"cutoff at code vector hit {rank}: doc-leak {rung['doc_leak']['with_doc']}/"
                      f"{rung['doc_leak']['questions']} = {rung['doc_leak']['rate']}; doc_hit"
                      f" {rung['doc_hit']['hits']}/{rung['doc_hit']['questions']}; code unchanged"
                      f" {rung['code_unchanged']}")
            print(f"adopted (loosest with doc-leak <= {LEAK_BAR}): {res['adopted_rank']}")
            name = "doc_ladder" + (f"-{args.label}" if args.label else "")
            print("saved", save_results(name, info, res))
        finally:
            db.close_pool()
        return

    db.open_pool()
    try:
        info = run_info(llm_used=False)
        info["label"] = args.label
        print(header(info), f"| {args.label}" if args.label else "")
        repos = load_questions(args.questions)
        if args.tuning_locked:
            repos += load_tuning_locked(args.tuning_locked)
        results = evaluate(repos)
        results["questions_file"] = str(args.questions.relative_to(ROOT))
        if args.tuning_locked:
            results["tuning_locked_file"] = str(args.tuning_locked.resolve().relative_to(ROOT))
        print_table(results)
        name = "retrieval_context" + (f"-{args.label}" if args.label else "")
        print("\nsaved", save_results(name, info, results))
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
