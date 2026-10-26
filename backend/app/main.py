from fastapi import FastAPI

app = FastAPI(title="RepoLens")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
