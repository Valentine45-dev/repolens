import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import config, db
from app.api import graph, repos, snapshots

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
