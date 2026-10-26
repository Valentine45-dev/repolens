# PROGRESS

## Done
- Git repo, `.gitignore`, `.gitattributes`; `main` pushed.
- Day 1 skeleton on `feat/ingest`: uv project in `backend/` (Python 3.12), `docker-compose.yml` (db on host 5433, api on 8000), `backend/Dockerfile`, `.env.example`.

## Next
- Day 1: schema, redaction, discover, parse, clone, pipeline, API, CI.

## Decisions
- Python 3.12 everywhere (safer for torch / sentence-transformers on Day 3).
- Embedding column `vector(384)` (all-MiniLM-L6-v2 / bge-small-en-v1.5 class models).
- No worker container: ingestion runs in FastAPI `BackgroundTasks` inside `api`.
- Config read from `os.environ` in `app/config.py` (no pydantic-settings).

## Known issues
- Docker Desktop still installing: nothing has run in Docker yet.
