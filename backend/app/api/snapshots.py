from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.db import pool
from app.ingest import pipeline
from app.qa import llm

router = APIRouter()


def search_state(row: dict) -> str:
    """embedding | tests | ready | failed; rows from before search_state existed are 'failed'
    when they have a search error, else 'ready'."""
    return row["search_state"] or ("failed" if row["search_error"] else "ready")


def _features(row: dict, has_chunks: bool) -> dict:
    """What the Ask drawer can do. Graph questions work whenever the analysis is done;
    `ask` is about AI answers from code search, `ai` about the LLM being configured.
    `search` is the search state, `search_progress` its counts while it runs, and
    `retry_search` whether "Retry preparing search" is offered."""
    state = search_state(row)
    if row["status"] != "done":
        ask, reason = False, "The analysis has not finished yet."
    elif state == "embedding":
        ask, reason = False, "Search for questions is still being prepared."
    elif not has_chunks:
        ask = False
        reason = row["search_error"] or "There is no code to search in this analysis."
    else:
        # Non-test code is searchable; test code may still be on its way or have failed.
        ask, reason = True, None
    running = row["status"] == "done" and state in ("embedding", "tests")
    progress = ({"done": row["progress_done"], "total": row["progress_total"]}
                if running and row["progress_total"] is not None else None)
    return {"ask": ask, "ask_reason": reason, "ai": llm.get_provider() is not None,
            "search": state, "search_progress": progress,
            "search_error": row["search_error"],
            "retry_search": row["status"] == "done" and state == "failed"}


@router.get("/snapshots/{snapshot_id}/status")
def snapshot_status(snapshot_id: int) -> dict:
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id AS snapshot_id, r.url, s.commit_sha, st.job_id, st.status, st.stage,"
            " st.percent, st.error, st.search_error, st.progress_done, st.progress_total,"
            " st.search_state,"
            " EXISTS (SELECT 1 FROM chunks c WHERE c.snapshot_id = s.id) AS has_chunks"
            " FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE s.id = %s",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    features = _features(row, row.pop("has_chunks"))
    row.pop("search_error")  # reported in features
    row.pop("search_state")
    done, total = row.pop("progress_done"), row.pop("progress_total")
    # Counts within the current stage (parse: files, embed: chunks) while the job runs.
    progress = ({"done": done, "total": total}
                if total is not None and row["status"] == "running" else None)
    return {**row, "progress": progress, "features": features}


@router.post("/snapshots/{snapshot_id}/search", status_code=202)
def retry_search(snapshot_id: int, background: BackgroundTasks) -> dict:
    """"Retry preparing search" for a finished analysis whose search failed (resubmitting the
    same commit reuses the finished job, so it would not run the embed stage again)."""
    with pool().connection() as conn:
        exists = conn.execute("SELECT 1 FROM snapshots WHERE id = %s", (snapshot_id,)).fetchone()
    if exists is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    job_id = pipeline.claim_search_retry(snapshot_id)
    if job_id is None:
        raise HTTPException(
            status_code=409,
            detail="Search is ready or already being prepared for this analysis.",
        )
    background.add_task(pipeline.run_search_retry, job_id, snapshot_id)
    return {"snapshot_id": snapshot_id, "job_id": job_id, "search": "embedding"}
