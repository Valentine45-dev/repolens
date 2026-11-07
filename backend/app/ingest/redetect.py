"""Re-run the detect stage on finished snapshots from their stored files, so an analysis made
before the code-quality checks existed gets its Bug / Quality findings.

No clone, no embedding, no LLM. Only detector findings are replaced (by the detect stage's own
transaction); hardcoded-secret findings belong to the discover stage and are not touched, so
`findings.placeholder` of old rows stays false until the repository is analysed again. Finding
ids change. With no argument it handles every finished snapshot.

Run with the API stopped:
    cd backend; uv run --env-file ../.env python -m app.ingest.redetect [snapshot_id ...]
"""

import sys

from app.db import close_pool, open_pool, pool
from app.ingest.pipeline import parse_stored, store_findings


def main(argv: list[str]) -> int:
    open_pool()
    try:
        with pool().connection() as conn:
            busy = conn.execute(
                "SELECT count(*) AS n FROM jobs WHERE status IN ('queued', 'running')"
            ).fetchone()["n"]
            if busy:
                print(f"{busy} job(s) queued or running; stop the API first.")
                return 1
            done = conn.execute(
                "SELECT snapshot_id, job_id FROM snapshot_status WHERE status = 'done'"
                " ORDER BY snapshot_id"
            ).fetchall()
        wanted = {int(a) for a in argv}
        for row in done:
            if wanted and row["snapshot_id"] not in wanted:
                continue
            n = store_findings(row["snapshot_id"], parse_stored(row["snapshot_id"]), row["job_id"])
            print(row["snapshot_id"], "detector findings", n)
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
