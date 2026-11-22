"""Who runs a job: a Postgres advisory lock per job, held by the process that runs it.

The lock is session-level, on a connection of its own (not from the pool), from the moment a
job is handed to a runner until it ends, test-code embedding included. Postgres releases it when
that connection closes, also when the process dies. At API start, a queued or running job (or a
search in progress) whose lock nobody holds has lost its runner and is marked failed; a job whose
lock is held is still running in another process (another API, or an evaluation script that runs
the pipeline in its own process) and is left alone.

The startup check takes a free lock and releases it at once. A job that asks for its lock in
that instant waits for it (up to WAIT_S) instead of failing at once: pg_try_advisory_lock would
have returned false, and the job would have run unlocked (22 Nov: a CI test flaked this way).

If the lock connection cannot be opened, or the lock is still held after WAIT_S, the job runs
unlocked, as before this lock existed, and a WARNING says so: a restart elsewhere could then mark
it interrupted.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg

from app import config

log = logging.getLogger("repolens.ingest")

# High bits mark the key as RepoLens's job lock ("RL"); the low 48 bits are the job id.
NAMESPACE = 0x524C << 48
CONNECT_TIMEOUT_S = 5
# How long a job waits for its lock. A check holds a free lock only for a moment; a lock still
# held after this belongs to another live session (the same job run twice).
WAIT_S = 5.0


def key(job_id: int) -> int:
    if not 0 < job_id < 1 << 48:
        raise ValueError(f"job id {job_id} does not fit the lock key")
    return NAMESPACE | job_id


def _reason(e: Exception) -> str:
    first = (str(e).strip().splitlines() or [""])[0]
    return f"{type(e).__name__}: {first[:200]}" if first else type(e).__name__


@contextmanager
def held(job_id: int) -> Iterator[bool]:
    """Hold the job's lock for the block. Yields whether it is held; never raises for the lock."""
    conn = None
    try:
        if not config.DATABASE_URL:
            raise ValueError("DATABASE_URL is not set")
        conn = psycopg.connect(config.DATABASE_URL, autocommit=True,
                               connect_timeout=CONNECT_TIMEOUT_S)
        # This connection only ever holds the lock, so the setting stays for its whole session.
        conn.execute("SELECT set_config('lock_timeout', %s, false)",
                     (f"{int(WAIT_S * 1000)}ms",))
        try:
            conn.execute("SELECT pg_advisory_lock(%s)", (key(job_id),))
        except psycopg.errors.LockNotAvailable:
            log.warning("job %s: its lock is still held by another session after %g s;"
                        " running unlocked", job_id, WAIT_S)
            conn.close()
            conn = None
    except (psycopg.Error, ValueError) as e:
        log.warning("job %s: could not take the job lock (%s); running unlocked, so a restart"
                    " elsewhere may mark this job interrupted", job_id, _reason(e))
        if conn is not None:
            conn.close()
        conn = None
    try:
        yield conn is not None
    finally:
        if conn is not None:
            try:
                conn.close()  # ends the session, which releases the lock
            except psycopg.Error:
                pass


def is_orphaned(conn, job_id: int) -> bool:
    """True when no live session holds the job's lock. Takes and releases it at once on `conn`."""
    got = conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (key(job_id),)).fetchone()
    got = got["got"] if isinstance(got, dict) else got[0]
    if got:
        conn.execute("SELECT pg_advisory_unlock(%s)", (key(job_id),))
    return bool(got)
