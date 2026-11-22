"""Backfill documentation chunks for analyses made before docs were in Ask.

    uv run --env-file ../.env python -m app.ingest.docchunks <snapshot id> [<snapshot id> ...]

For each snapshot named (there is no "all"): its stored files are chunked and embedded with the
same function a fresh analysis uses (pipeline.embed_docs), and its doc rows are replaced in one
transaction. Code chunks are never read or written. Running it twice gives the same rows.

Refused for a snapshot whose analysis is not done, whose search is not ready (being prepared,
failed, or test code still being embedded), or while another process holds its job's lock. Run it
with the API stopped (it loads its own copy of the embedding model) and never next to an
analysis.
"""

import argparse
import sys
import time

from app import config, db
from app.ingest import joblock
from app.ingest.pipeline import embed_docs


def _state(snapshot_id: int) -> dict | None:
    with db.pool().connection() as conn:
        return conn.execute(
            "SELECT st.status, st.job_id, st.search_state FROM snapshot_status st"
            " WHERE st.snapshot_id = %s", (snapshot_id,)).fetchone()


def backfill(snapshot_id: int) -> dict:
    row = _state(snapshot_id)
    if row is None:
        raise SystemExit(f"snapshot {snapshot_id}: not found")
    if row["status"] != "done" or row["search_state"] != "ready":
        raise SystemExit(f"snapshot {snapshot_id}: analysis {row['status']}, search"
                         f" {row['search_state']}; only a finished analysis with search ready")
    # Hold the job's lock for the whole backfill, so no analysis or search retry of this snapshot
    # can start meanwhile (both take the same lock).
    with joblock.held(row["job_id"]) as got:
        if not got:
            raise SystemExit(f"snapshot {snapshot_id}: job {row['job_id']}'s lock is held by"
                             " another process")
        return embed_docs(snapshot_id, None, time.monotonic() + config.MAX_ANALYSIS_S)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("snapshots", type=int, nargs="+")
    args = p.parse_args()
    db.open_pool()
    try:
        for sid in args.snapshots:
            stats = backfill(sid)
            print(f"snapshot {sid}: {stats['files']} doc files, {stats['chunks']} doc chunks"
                  f" ({stats['windows']} windows), {stats['embed_seconds']} s, {stats['model']}")
            if stats["too_large"]:
                print(f"  left out, over 200 KB: {', '.join(stats['too_large'])}")
    finally:
        db.close_pool()
    sys.exit(0)


if __name__ == "__main__":
    main()
