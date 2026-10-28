from fastapi import APIRouter, HTTPException

from app.db import pool
from app.qa import llm

router = APIRouter()


def _features(row: dict, has_chunks: bool) -> dict:
    """What the Ask drawer can do. Graph questions work whenever the analysis is done;
    `ask` is about AI answers from code search, `ai` about the LLM being configured."""
    if row["status"] != "done":
        ask, reason = False, "The analysis has not finished yet."
    elif row["search_error"]:
        ask, reason = False, row["search_error"]
    elif not has_chunks:
        ask, reason = False, "There is no code to search in this analysis."
    else:
        ask, reason = True, None
    return {"ask": ask, "ask_reason": reason, "ai": llm.get_provider() is not None}


@router.get("/snapshots/{snapshot_id}/status")
def snapshot_status(snapshot_id: int) -> dict:
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id AS snapshot_id, r.url, s.commit_sha, st.job_id, st.status, st.stage,"
            " st.percent, st.error, st.search_error, st.progress_done, st.progress_total,"
            " EXISTS (SELECT 1 FROM chunks c WHERE c.snapshot_id = s.id) AS has_chunks"
            " FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE s.id = %s",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    features = _features(row, row.pop("has_chunks"))
    row.pop("search_error")  # reported as features.ask_reason
    done, total = row.pop("progress_done"), row.pop("progress_total")
    # Counts within the current stage (parse: files, embed: chunks), or null.
    progress = {"done": done, "total": total} if total is not None else None
    return {**row, "progress": progress, "features": features}
