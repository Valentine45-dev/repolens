"""The per-job advisory lock (app/ingest/joblock.py): API start marks failed only the jobs whose
runner is gone, never one another process is still running (21 Nov: a second API that never
bound its port marked a running analysis "Interrupted by server restart")."""

import logging
import threading

import psycopg
import pytest

from app.ingest import joblock, pipeline

pytestmark = pytest.mark.db

SHA = "b" * 40


def connect(url):
    return psycopg.connect(url, autocommit=True, connect_timeout=5)


@pytest.fixture
def jobs(test_db):
    """A fresh repo and snapshot; returns a function that adds a job row and gives its id."""
    with connect(test_db) as conn:
        conn.execute("TRUNCATE repos RESTART IDENTITY CASCADE")
        conn.execute("INSERT INTO repos (url) VALUES ('https://github.com/o/r')")
        conn.execute("INSERT INTO snapshots (repo_id, commit_sha) VALUES (1, %s)", (SHA,))

    def add(status="running", stage="parse", search_state=None) -> int:
        with connect(test_db) as conn:
            return conn.execute(
                "INSERT INTO jobs (snapshot_id, status, stage, search_state)"
                " VALUES (1, %s, %s, %s) RETURNING id", (status, stage, search_state),
            ).fetchone()[0]

    return add


def job(url, job_id):
    with connect(url) as conn:
        return conn.execute("SELECT status, error, search_state, search_error FROM jobs"
                            " WHERE id = %s", (job_id,)).fetchone()


def holds(url, job_id) -> bool:
    """Some live session holds the job's lock. Read from pg_locks, so the probe never takes the
    lock itself: a take-and-release probe could hold it at the instant the job asks for it."""
    k = joblock.key(job_id)
    with connect(url) as conn:
        return conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted"
            " AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
            " AND classid::bigint = %s AND objid::bigint = %s AND objsubid = 1)",
            (k >> 32, k & 0xFFFFFFFF),
        ).fetchone()[0]


def test_api_start_leaves_jobs_of_a_live_process_alone(test_db, jobs):
    from fastapi.testclient import TestClient

    from app.main import app

    live = jobs("running", "embed")
    dead = jobs("running", "parse")
    queued_dead = jobs("queued", "queued")
    live_tests = jobs("done", "done", "tests")
    dead_tests = jobs("done", "done", "embedding")
    other = connect(test_db)  # stands for the process that runs `live` and `live_tests`
    for j in (live, live_tests):
        assert other.execute("SELECT pg_try_advisory_lock(%s)", (joblock.key(j),)).fetchone()[0]
    try:
        with TestClient(app, base_url="http://127.0.0.1"):  # runs the startup hook
            pass
        assert job(test_db, live)[:2] == ("running", None)
        assert job(test_db, live_tests)[2] == "tests"
        assert job(test_db, dead)[:2] == ("failed", "Interrupted by server restart.")
        assert job(test_db, queued_dead)[0] == "failed"
        assert job(test_db, dead_tests)[2:] == (
            "failed", "Search for questions was interrupted by a server restart.")
    finally:
        other.close()
    # The check took and released the free locks: none is left held by the hook.
    assert not any(holds(test_db, j) for j in (live, dead, queued_dead, live_tests, dead_tests))


def test_recover_reports_what_it_failed_and_left(test_db, jobs):
    from app import db

    live, dead = jobs(), jobs()
    other = connect(test_db)
    other.execute("SELECT pg_advisory_lock(%s)", (joblock.key(live),))
    db.open_pool()
    try:
        assert pipeline.recover_interrupted_jobs() == {"failed": [dead], "left": [live]}
    finally:
        db.close_pool()
        other.close()


def test_run_job_holds_the_lock_and_releases_it(test_db, jobs, monkeypatch):
    j = jobs("queued", "queued")
    seen = []
    monkeypatch.setattr(pipeline, "_run_job", lambda *a: seen.append(holds(test_db, j)))
    pipeline.run_job(j, 1, "https://github.com/o/r", SHA)
    assert seen == [True]
    assert not holds(test_db, j)


def test_run_job_releases_the_lock_when_it_crashes(test_db, jobs, monkeypatch):
    j = jobs()
    seen = []

    def boom(*a):
        seen.append(holds(test_db, j))
        raise RuntimeError("crash")

    monkeypatch.setattr(pipeline, "_run_job", boom)
    with pytest.raises(RuntimeError):
        pipeline.run_job(j, 1, "https://github.com/o/r", SHA)
    assert seen == [True]
    assert not holds(test_db, j)


def test_search_retry_holds_the_lock(test_db, jobs, monkeypatch):
    j = jobs("done", "done", "embedding")
    seen = []
    monkeypatch.setattr(pipeline, "_run_search_retry", lambda *a: seen.append(holds(test_db, j)))
    pipeline.run_search_retry(j, 1)
    assert seen == [True]
    assert not holds(test_db, j)


def test_a_job_waiting_in_the_queue_already_holds_its_lock(test_db, jobs, monkeypatch):
    j = jobs("queued", "queued")
    monkeypatch.setattr(pipeline, "_run_job", lambda *a: None)
    with pipeline._JOB_LOCK:  # another job of this process is running
        t = threading.Thread(target=pipeline.run_job, args=(j, 1, "u", SHA))
        t.start()
        for _ in range(50):
            if holds(test_db, j):
                break
            threading.Event().wait(0.1)
        assert holds(test_db, j)
    t.join(timeout=10)
    assert not holds(test_db, j)


def test_a_job_waits_for_a_lock_held_for_a_moment(test_db, jobs, monkeypatch, caplog):
    """The startup check (or a probe) holds a free lock for a moment: a job asking for it then
    waits and gets it, instead of running unlocked (22 Nov CI flake)."""
    j = jobs("queued", "queued")
    seen = []
    monkeypatch.setattr(pipeline, "_run_job", lambda *a: seen.append(holds(test_db, j)))
    checker = connect(test_db)
    assert checker.execute("SELECT pg_try_advisory_lock(%s)", (joblock.key(j),)).fetchone()[0]
    try:
        with caplog.at_level(logging.WARNING, logger="repolens.ingest"):
            t = threading.Thread(target=pipeline.run_job, args=(j, 1, "u", SHA))
            t.start()
            threading.Event().wait(0.5)  # the job is now waiting for the lock
            assert seen == []
            checker.execute("SELECT pg_advisory_unlock(%s)", (joblock.key(j),))
            t.join(timeout=10)
    finally:
        checker.close()
    assert seen == [True]
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]
    assert not holds(test_db, j)


def test_a_lock_held_too_long_warns_and_runs_unlocked(test_db, jobs, monkeypatch, caplog):
    j = jobs()
    ran = []
    monkeypatch.setattr(joblock, "WAIT_S", 0.3)
    monkeypatch.setattr(pipeline, "_run_job", lambda *a: ran.append(True))
    other = connect(test_db)
    other.execute("SELECT pg_advisory_lock(%s)", (joblock.key(j),))
    try:
        with caplog.at_level(logging.WARNING, logger="repolens.ingest"):
            pipeline.run_job(j, 1, "u", SHA)
    finally:
        other.close()
    assert ran == [True]
    assert any(f"job {j}:" in r.getMessage() and "still held by another session after 0.3 s"
               in r.getMessage() and "running unlocked" in r.getMessage()
               for r in caplog.records if r.levelno == logging.WARNING)


def test_no_lock_connection_warns_and_runs_unlocked(test_db, jobs, monkeypatch, caplog):
    j = jobs()
    ran = []

    def refuse(*a, **k):
        raise psycopg.OperationalError("connection refused")

    monkeypatch.setattr(joblock.psycopg, "connect", refuse)
    monkeypatch.setattr(pipeline, "_run_job", lambda *a: ran.append(True))
    with caplog.at_level(logging.WARNING, logger="repolens.ingest"):
        pipeline.run_job(j, 1, "u", SHA)
    assert ran == [True]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(f"job {j}:" in r.getMessage() and "OperationalError: connection refused"
               in r.getMessage() and "running unlocked" in r.getMessage() for r in warnings)


def test_is_orphaned(test_db, jobs):
    j = jobs()
    with connect(test_db) as checker:
        assert joblock.is_orphaned(checker, j)
        assert not holds(test_db, j)  # released again
        with joblock.held(j) as locked:
            assert locked
            assert not joblock.is_orphaned(checker, j)
    assert not holds(test_db, j)


def test_key_range():
    assert joblock.key(1) != joblock.key(2)
    assert joblock.key(1) >> 48 == 0x524C
    with pytest.raises(ValueError):
        joblock.key(0)
