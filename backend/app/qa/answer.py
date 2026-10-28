"""AI answers: retrieve, build the prompt, call the LLM inside the token cap and the deadline,
validate citations. Degraded states are answers with a status, never HTTP errors.

Statuses: answered | unverified (no citation survived validation) | refused (the model's
safety classifiers declined) | no_context (nothing to search) | unavailable (no key, provider
down, deadline passed, empty answer) | cap_reached.
"""

import hashlib
import logging

from app import config
from app.db import pool
from app.qa import llm
from app.qa.citations import validate
from app.qa.prompt import (
    COULD_NOT_FIND,
    IDENTITY_ANSWER,
    build_user_message,
    format_snippet,
    system_prompt,
)
from app.qa.retrieve import CHARS_PER_TOKEN, retrieve

log = logging.getLogger("repolens.qa")

# Copy from the UI spec (5.5).
UNAVAILABLE = "AI answers are unavailable right now. Graph questions still work."
NO_CODE = "I could not find code related to that question in this repository."
NO_SEARCH = "Search for questions is not available for this analysis. Graph questions still work."
CAP_REACHED = "This analysis has used its AI question budget. Graph questions still work."
REFUSED = (
    "The AI declined to answer this question. Security-related questions are sometimes"
    " declined; asking what a specific function or file does may work. Graph questions and"
    " findings still work."
)


def _reply(status: str, answer: str, retrieval=None, citations=(), dropped: int = 0) -> dict:
    return {
        "kind": "ai",
        "status": status,
        "answer": answer,
        "citations": [c.__dict__ for c in citations],
        "dropped": dropped,
        "results": [],
        "prompt_version": system_prompt().version,
        "retrieval": retrieval.summary() if retrieval else None,
    }


def _reserve(snapshot_id: int, tokens: int) -> bool:
    """Take `tokens` from the snapshot's budget atomically; False if it would go over."""
    with pool().connection() as conn:
        row = conn.execute(
            "UPDATE snapshots SET llm_tokens_used = llm_tokens_used + %s"
            " WHERE id = %s AND llm_tokens_used + %s <= %s RETURNING id",
            (tokens, snapshot_id, tokens, config.LLM_TOKEN_CAP_PER_SNAPSHOT),
        ).fetchone()
    return row is not None


def _adjust(snapshot_id: int, delta: int) -> None:
    with pool().connection() as conn:
        conn.execute(
            "UPDATE snapshots SET llm_tokens_used = greatest(llm_tokens_used + %s, 0)"
            " WHERE id = %s",
            (delta, snapshot_id),
        )


def search_ready(snapshot_id: int) -> bool:
    """Code search can answer: no search run is replacing the non-test chunks, and a failed
    search left some chunks behind. Test code may still be on its way (state 'tests'). A repo
    with no code at all is ready too; retrieval then finds nothing."""
    with pool().connection() as conn:
        row = conn.execute(
            "SELECT st.search_state, st.search_error,"
            " EXISTS (SELECT 1 FROM chunks c WHERE c.snapshot_id = st.snapshot_id) AS has_chunks"
            " FROM snapshot_status st WHERE st.snapshot_id = %s",
            (snapshot_id,),
        ).fetchone()
    if not row or row["search_state"] == "embedding":
        return False
    failed = row["search_state"] == "failed" or (
        row["search_state"] is None and row["search_error"] is not None)
    return row["has_chunks"] or not failed


def ai_answer(snapshot_id: int, question: str, include_tests: bool = False) -> dict:
    q_log = f"len={len(question)} hash={hashlib.sha256(question.encode()).hexdigest()[:10]}"
    provider = llm.get_provider()
    if provider is None:
        return _reply("unavailable", UNAVAILABLE)
    if not search_ready(snapshot_id):
        return _reply("no_context", NO_SEARCH)

    found = retrieve(snapshot_id, question, include_tests=include_tests)
    if not found.snippets:
        return _reply("no_context", NO_CODE, found)

    system = system_prompt()
    prompt = build_user_message(question, [
        format_snippet(s.path, s.qualified_name, s.start_line, s.text) for s in found.snippets
    ])
    estimate = int(len(system.text + prompt) / CHARS_PER_TOKEN) + config.LLM_MAX_TOKENS
    charge = provider.counts_toward_budget  # False for FakeProvider: made-up token counts
    if charge and not _reserve(snapshot_id, estimate):
        log.info("ask snapshot=%s %s: token cap reached", snapshot_id, q_log)
        return _reply("cap_reached", CAP_REACHED, found)

    try:
        completion = llm.complete_with_deadline(
            provider, system.text, prompt, max_tokens=config.LLM_MAX_TOKENS,
            deadline_s=config.QA_DEADLINE_S, min_retry_s=config.QA_MIN_RETRY_S,
        )
    except llm.LLMError as e:
        if charge:
            _adjust(snapshot_id, -estimate)
        log.warning("ask snapshot=%s %s: LLM %s", snapshot_id, q_log, e)
        return _reply("unavailable", UNAVAILABLE, found)
    if charge:
        _adjust(snapshot_id, completion.tokens_in + completion.tokens_out - estimate)
    if completion.refused:
        # Any partial text before the refusal is not shown: it was not finished or checked.
        log.info("ask snapshot=%s %s: refused category=%s model=%s", snapshot_id, q_log,
                 completion.refusal_category, provider.name)
        return _reply("refused", REFUSED, found)
    if not completion.text.strip():
        log.warning("ask snapshot=%s %s: empty answer (stop_reason=%s)", snapshot_id, q_log,
                    completion.stop_reason)
        return _reply("unavailable", UNAVAILABLE, found)

    checked = validate(completion.text.strip(), found.snippets)
    not_found = COULD_NOT_FIND.rstrip(".").lower() in checked.text.lower()
    # Only the exact identity reply is exempt, so uncited claims cannot ride along with it.
    identity = checked.text == IDENTITY_ANSWER
    status = "answered" if checked.citations or not_found or identity else "unverified"
    log.info(
        "ask snapshot=%s %s: %s model=%s %s prompt=%s sent=%d cited=%d dropped=%d"
        " tokens=%d+%d",
        snapshot_id, q_log, status, provider.name, provider.settings, system.version,
        len(found.snippets),
        len(checked.citations), checked.dropped, completion.tokens_in, completion.tokens_out,
    )
    return _reply(status, checked.text, found, checked.citations, checked.dropped)
