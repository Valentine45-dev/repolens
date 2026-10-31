"""Records the analysis stats of the eval repos (Step 2 of the v1 re-baseline).

Numbers are copied from the API log of the analysis and from the database; the log lines only
exist for repos analysed while the log was being kept, so the others carry DB-derived counts only.
    uv run --project backend --env-file .env python eval/analysis_stats.py
"""

from runinfo import run_info, save_results

STATS = {
    "express": {
        "url": "https://github.com/expressjs/express",
        "commit": "1c6f1b0fe4000977b9a7b4f34097e4d527dd9824", "snapshot_id": 3,
        "source": "API log (native uvicorn) + database",
        "files_kept": 165, "files_skipped": 51, "file_limit_hit": False, "files_parsed": 142,
        "edges": {"internal": 154, "external": 244, "calls@1.0": 63, "calls@0.9": 34,
                  "calls@0.5": 243, "db_imports": 398},
        "detector_findings": 0, "findings_shown": 1, "findings_shown_note": "1 hardcoded-secret, in test code",
        "chunks_non_test": 129, "embed_non_test_s": 83.6,
        "chunks_test_planned": 1048, "chunks_test_embedded": 0,
        "test_embed": "stopped by MAX_ANALYSIS_S=600 (search_state=failed); ~512/1048 done at the "
                      "stop; no test chunks stored. Evals leave test code out, so unaffected.",
        "analysis_to_done_s": 140, "ask_ready_s": 140,
    },
    "itsdangerous": {
        "url": "https://github.com/pallets/itsdangerous",
        "commit": "672971d66a2ef9f85151e53283113f33d642dabd", "snapshot_id": 1,
        "source": "API log lines supplied by the owner (31 Oct, same PC, same code) + database",
        "conditions": "Chrome open, Claude Code app closed",
        "files_kept": 41, "files_skipped": 9, "file_limit_hit": False, "files_parsed": 15,
        "edges": {"internal": 36, "external": 39, "defines": 91, "calls@1.0": 52,
                  "calls@0.9": 22, "calls@0.5": 8},
        "detector_findings": 0, "findings_shown": 7,
        "findings_shown_note": "7 hardcoded-secret, all in test code (produced by redaction)",
        "chunks_non_test": 113, "embed_non_test_s": 64.5,
        "chunks_test": 68, "embed_test_s": 45.8, "ask_ready_s_after_submit": 67,
    },
    "pygoat": {
        "url": "https://github.com/adeyosemanputra/pygoat",
        "commit": "46fef968f3f44d1191363baf936aaa3335dc5c6d", "snapshot_id": 2,
        "source": "API log lines supplied by the owner (31 Oct, same PC, same code) + database",
        "conditions": "Chrome open, Claude Code app closed",
        "files_kept": 222, "files_skipped": 240, "file_limit_hit": False, "files_parsed": 117,
        "python_files": 115,
        "edges": {"internal": 38, "external": 216, "defines": 103, "calls@1.0": 145,
                  "calls@0.9": 32, "calls@0.5": 110},
        "detector_findings": 12, "findings_shown": 60,
        "findings_by_rule": {"hardcoded-secret": 48, "py-bare-except": 9, "py-eval-exec": 1,
                             "py-sql-string": 1, "py-subprocess-shell": 1},
        "chunks_non_test": 834, "embed_non_test_s": 287.8,
        "chunks_test": 0,
        "test_embed": "no test chunks and no test embed stage: the job's search_state went "
                      "straight to ready (progress counts empty). Not a timeout. The three "
                      "tests.py files are classified as non-test by app.paths.is_test_path "
                      "(it matches tests/ dirs and test_*.py / *_test.py, not tests.py).",
        "findings_vs_progress": "PROGRESS 58 = after the f-string fix (116ca46); the config-file "
                                "redaction fix (a8638f8, review S3) added 2 hardcoded-secret "
                                "findings (docker-compose.yml SECRET_KEY, JWT_SECRET_KEY) -> 60.",
    },
}

if __name__ == "__main__":
    info = run_info(llm_used=False)
    info["notes"] = ("Claude Code desktop app was open during the express analysis; machine "
                     "otherwise idle. Timings are for this PC only, not comparable to v1.")
    print(save_results("analysis_stats", info, {"repos": STATS}))
