import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config, db
from app.api import ask, findings, graph, repos, snapshots
from app.qa.embed import get_embedder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("repolens")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the embedding model now, not on the first question or job. If it cannot load, the
    # API still starts: embed stages then fail without failing the job (search unavailable).
    try:
        embedder = get_embedder()
        log.info("embedder %s@%s ready", embedder.name, embedder.revision)
    except Exception as e:
        log.error("embedder failed to load: %s", type(e).__name__)
    if config.DATABASE_URL:
        db.open_pool()
        # Background tasks do not survive a restart; there is no requeue in this build.
        with db.pool().connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'failed', error = 'Interrupted by server restart.'"
                " WHERE status IN ('queued', 'running')"
            )
    yield
    db.close_pool()


app = FastAPI(title="RepoLens", lifespan=lifespan)
app.include_router(repos.router)
app.include_router(snapshots.router)
app.include_router(graph.router)
app.include_router(findings.router)
app.include_router(ask.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
