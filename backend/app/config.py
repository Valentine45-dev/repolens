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

# LLM. Only the backend reads these; the key never leaves this process (no logs, no responses).
# AI answers are available only when the provider is anthropic and both model and key are set.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
# Thinking tokens count toward max_tokens, so leave room beyond the short answer itself.
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
# No temperature on current models; these (with the model and PROMPT_VERSION) fix behaviour.
LLM_EFFORT = os.environ.get("LLM_EFFORT", "low")  # output_config.effort
LLM_THINKING = os.environ.get("LLM_THINKING", "between_tools")  # between_tools|adaptive|default
LLM_TOKEN_CAP_PER_SNAPSHOT = int(os.environ.get("LLM_TOKEN_CAP_PER_SNAPSHOT", "500000"))
# One deadline per question, both attempts included; the retry runs only if this much is left.
QA_DEADLINE_S = float(os.environ.get("QA_DEADLINE_S", "40"))
QA_MIN_RETRY_S = float(os.environ.get("QA_MIN_RETRY_S", "5"))

# Retrieval
QA_TOP_K = int(os.environ.get("QA_TOP_K", "8"))
QA_GRAPH_EXPANSION = os.environ.get("QA_GRAPH_EXPANSION", "1") == "1"
QA_EXPAND_MAX = int(os.environ.get("QA_EXPAND_MAX", "8"))
QA_CONTEXT_TOKENS = int(os.environ.get("QA_CONTEXT_TOKENS", "6000"))  # snippet text, estimated
