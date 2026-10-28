import os
import tempfile
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL", "")

MAX_FILES = int(os.environ.get("MAX_FILES", "2000"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", "1000000"))
CLONE_TIMEOUT_S = int(os.environ.get("CLONE_TIMEOUT_S", "120"))
MAX_ANALYSIS_S = int(os.environ.get("MAX_ANALYSIS_S", "600"))

# Clones live here only while a job runs; each job deletes its own folder.
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", Path(tempfile.gettempdir()) / "repolens"))

# Embeddings. The revision is pinned so results are reproducible; evaluation runs report both.
# EMBEDDER=stub uses a deterministic hashing embedder (tests and CI: no model download).
EMBEDDER = os.environ.get("EMBEDDER", "sentence-transformers")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_MODEL_REVISION = os.environ.get(
    "EMBED_MODEL_REVISION", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
)
EMBED_BATCH = int(os.environ.get("EMBED_BATCH", "64"))
