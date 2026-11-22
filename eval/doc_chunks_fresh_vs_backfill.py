"""Proof that a fresh analysis and the backfill make the same documentation chunks (Step 5 Part A).

    uv run --project backend --env-file .env python eval/doc_chunks_fresh_vs_backfill.py \\
        --snapshot 1 --repo pallets/itsdangerous --commit <40-hex sha>

Tuning repos only. Steps, in this process (no API is started):
1. mark the snapshot's latest job "Re-run: ..." (failed) so it is analysed again in place;
2. analyse it in process (the product's own submit; clone, discover, parse, ..., code and doc
   embedding), waiting until test code is embedded too;
3. read its doc rows: path, lines, token count, in_test, MD5 of text, search words and embedding;
4. run the backfill (app.ingest.docchunks) on it, read the doc rows again, and the code rows'
   signature before and after the backfill;
5. save both and say whether they are identical.
"""

import argparse
import json
import sys

import locked_eval as le
from runinfo import header, run_info, save_results  # also puts backend/ on sys.path

DOC_ROWS = (
    "SELECT f.path, c.start_line, c.end_line, c.token_count, c.in_test, c.symbol_id,"
    " md5(c.text) AS text, md5(coalesce(c.search_tsv::text, '')) AS tsv,"
    " md5(c.embedding::text) AS embedding FROM chunks c JOIN files f ON f.id = c.file_id"
    " WHERE c.snapshot_id = %s AND c.source = 'doc' ORDER BY f.path, c.start_line, c.end_line"
)
CODE_SIG = (
    "SELECT count(*) AS n, md5(coalesce(string_agg(concat_ws('|', id, symbol_id, file_id,"
    " start_line, end_line, token_count, in_test, md5(text), md5(coalesce(search_tsv::text, '')),"
    " md5(embedding::text)), ',' ORDER BY id), '')) AS sig FROM chunks"
    " WHERE snapshot_id = %s AND source = 'code'"
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--snapshot", type=int, required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--commit", required=True)
    args = p.parse_args()

    from app import db
    from app.ingest import docchunks

    db.open_pool()
    try:
        info = run_info(llm_used=False)
        print(header(info))
        with db.pool().connection() as conn:
            job = conn.execute("SELECT job_id FROM snapshot_status WHERE snapshot_id = %s",
                               (args.snapshot,)).fetchone()["job_id"]
            conn.execute("UPDATE jobs SET status = 'failed', error = %s WHERE id = %s",
                         ("Re-run: doc-chunk proof, fresh analysis vs backfill (Step 5 Part A)",
                          job))
        via = le.InProcess()
        rec = le.analyse({"repo": args.repo, "commit": args.commit}, via, wait_tests=True)
        for t in via.threads:
            t.join()
        if rec["final_status"] != "done" or rec["snapshot_id"] != args.snapshot:
            sys.exit(f"analysis did not finish in place: {rec}")
        with db.pool().connection() as conn:
            fresh = [dict(r) for r in conn.execute(DOC_ROWS, (args.snapshot,))]
            code_before = dict(conn.execute(CODE_SIG, (args.snapshot,)).fetchone())
        stats = docchunks.backfill(args.snapshot)
        with db.pool().connection() as conn:
            backfilled = [dict(r) for r in conn.execute(DOC_ROWS, (args.snapshot,))]
            code_after = dict(conn.execute(CODE_SIG, (args.snapshot,)).fetchone())
        result = {
            "snapshot_id": args.snapshot, "repo": args.repo, "commit": args.commit,
            "rerun_job": rec["job_id"], "analysis": {k: rec[k] for k in (
                "final_status", "search", "analysis_s", "total_with_tests_s")},
            "backfill": {k: v for k, v in stats.items()},
            "doc_chunks_fresh": len(fresh), "doc_chunks_backfill": len(backfilled),
            "doc_rows_identical": fresh == backfilled,
            "code_before_backfill": code_before, "code_after_backfill": code_after,
            "code_identical": code_before == code_after,
            "doc_rows": fresh,
        }
        print(json.dumps({k: v for k, v in result.items() if k != "doc_rows"}, indent=2))
        print("saved", save_results("doc_chunks_fresh_vs_backfill", info, result))
        sys.exit(0 if result["doc_rows_identical"] and result["code_identical"] else 1)
    finally:
        db.close_pool()


if __name__ == "__main__":
    main()
