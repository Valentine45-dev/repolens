from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app import config
from app.db import pool
from app.ingest import clone
from app.ingest.pipeline import run_job

router = APIRouter()


class SubmitRepo(BaseModel):
    url: str
    # Optional pinned commit (full SHA), e.g. for the Home page examples: an analysis of that
    # commit is reused instead of following the default branch.
    commit: str | None = None


@router.post("/repos", status_code=202)
def submit_repo(body: SubmitRepo, background: BackgroundTasks) -> dict:
    try:
        url = clone.normalize_repo_url(body.url)
        if body.commit is not None and not clone.is_full_sha(body.commit):
            raise HTTPException(status_code=422, detail="commit must be a full 40-character SHA.")
        sha = body.commit or clone.resolve_sha(url, timeout=config.CLONE_TIMEOUT_S)
    except (clone.InvalidRepoUrl, clone.CloneError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    with pool().connection() as conn, conn.transaction():
        # One row per repo whatever the case (unique on lower(url)); a spelling with capitals
        # replaces an all-lower-case one, so the display shows the real owner/repo name.
        repo_id = conn.execute(
            "INSERT INTO repos (url) VALUES (%s)"
            " ON CONFLICT ((lower(url))) DO UPDATE SET url = CASE"
            " WHEN EXCLUDED.url <> lower(EXCLUDED.url) THEN EXCLUDED.url ELSE repos.url END"
            " RETURNING id",
            (url,),
        ).fetchone()["id"]
        snapshot_id = conn.execute(
            "INSERT INTO snapshots (repo_id, commit_sha) VALUES (%s, %s)"
            " ON CONFLICT (repo_id, commit_sha) DO UPDATE SET commit_sha = EXCLUDED.commit_sha"
            " RETURNING id",
            (repo_id, sha),
        ).fetchone()["id"]
        # Lock the snapshot so two concurrent submits cannot both start a job.
        conn.execute("SELECT id FROM snapshots WHERE id = %s FOR UPDATE", (snapshot_id,))
        latest = conn.execute(
            "SELECT job_id, status FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
        ).fetchone()
        if latest and latest["status"] != "failed":
            job_id, status, start = latest["job_id"], latest["status"], False
        else:
            job_id = conn.execute(
                "INSERT INTO jobs (snapshot_id) VALUES (%s) RETURNING id", (snapshot_id,)
            ).fetchone()["id"]
            status, start = "queued", True

    if start:
        background.add_task(run_job, job_id, snapshot_id, url, sha)
    return {"snapshot_id": snapshot_id, "job_id": job_id, "commit_sha": sha, "status": status}
