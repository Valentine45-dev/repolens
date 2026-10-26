from fastapi import APIRouter, HTTPException

from app.db import pool

router = APIRouter()


@router.get("/snapshots/{snapshot_id}/status")
def snapshot_status(snapshot_id: int) -> dict:
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT s.id AS snapshot_id, r.url, s.commit_sha, st.job_id, st.status, st.stage,"
            " st.percent, st.error"
            " FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " JOIN snapshot_status st ON st.snapshot_id = s.id"
            " WHERE s.id = %s",
            (snapshot_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    return row
