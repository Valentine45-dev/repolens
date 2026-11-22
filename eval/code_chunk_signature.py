"""Signature of the code chunks of given snapshots: proves a migration or a doc backfill left them
byte-identical. No LLM, no embedding.

    uv run --project backend --env-file .env python eval/code_chunk_signature.py 1 2 3 [--out F]

Per snapshot: the number of code chunks and an MD5 over every column of every code row in id
order (id, symbol_id, file_id when present, lines, token count, in_test, text, search_tsv,
embedding). Rows whose `source` is 'doc' are left out (the column may not exist yet: before the
doc-chunk migration every row is code). Only the snapshot ids given are read.
"""

import argparse
import json
import sys
from pathlib import Path

from runinfo import ROOT  # also puts backend/ on sys.path (app is imported in main)

ROW = ("concat_ws('|', c.id, c.symbol_id, {file_id} c.start_line, c.end_line, c.token_count,"
       " c.in_test, md5(c.text), md5(coalesce(c.search_tsv::text, '')),"
       " md5(coalesce(c.embedding::text, '')))")


def signature(conn, snapshot_id: int) -> dict:
    cols = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'chunks'")}
    code_only = " AND c.source = 'code'" if "source" in cols else ""
    # file_id is compared too once it exists; before the migration it is not part of the row.
    row = ROW.format(file_id="c.file_id," if "file_id" in cols else "")
    r = conn.execute(
        f"SELECT count(*) AS n, md5(coalesce(string_agg({row}, ',' ORDER BY c.id), ''))"
        f" AS sig FROM chunks c WHERE c.snapshot_id = %s{code_only}",
        (snapshot_id,),
    ).fetchone()
    return {"code_chunks": r["n"], "md5": r["sig"], "with_file_id": "file_id" in cols}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("snapshots", type=int, nargs="+")
    p.add_argument("--out", type=Path)
    p.add_argument("--without-file-id", action="store_true",
                   help="leave chunks.file_id out of the row, to compare with a capture made"
                        " before the column existed")
    args = p.parse_args()
    from app import db

    if args.without_file_id:
        global ROW
        ROW = ROW.replace("{file_id}", "")
    db.open_pool()
    try:
        with db.pool().connection() as conn:
            out = {str(s): signature(conn, s) for s in args.snapshots}
    finally:
        db.close_pool()
    text = json.dumps(out, indent=2)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print("saved", args.out.resolve().relative_to(ROOT) if args.out.resolve().is_relative_to(
            ROOT) else args.out)
    sys.exit(0)


if __name__ == "__main__":
    main()
