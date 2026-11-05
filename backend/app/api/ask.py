"""POST /snapshots/{id}/ask: graph questions from the graph, everything else from the LLM.
Each question is answered on its own (no conversation history is sent)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import pool
from app.qa.answer import ai_answer
from app.qa.router import graph_answer, match_route

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    include_tests: bool = False
    # "Ask about this": this file's chunks always go into the context (AI answers only).
    file_id: int | None = Field(default=None, ge=1, le=2**63 - 1)


def _require_file(snapshot_id: int, file_id: int) -> None:
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM files WHERE id = %s AND snapshot_id = %s", (file_id, snapshot_id)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="File not found in this analysis.")


def _require_done(snapshot_id: int) -> None:
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT status, stage FROM snapshot_status WHERE snapshot_id = %s", (snapshot_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    if row["status"] == "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Questions are not available: the analysis failed during {row['stage']}.",
        )
    if row["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"The analysis has not finished yet (current stage: {row['stage']}).",
        )


@router.post("/snapshots/{snapshot_id}/ask")
def ask(snapshot_id: int, body: AskRequest) -> dict:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="The question is empty.")
    _require_done(snapshot_id)
    if body.file_id is not None:
        _require_file(snapshot_id, body.file_id)
    route = match_route(question)
    if route:
        answer = graph_answer(snapshot_id, route)
        if answer is not None:
            return answer
    return ai_answer(snapshot_id, question, body.include_tests, body.file_id)
