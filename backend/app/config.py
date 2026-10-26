import os
from pathlib import Path
import tempfile

DATABASE_URL = os.environ.get("DATABASE_URL", "")

MAX_FILES = int(os.environ.get("MAX_FILES", "2000"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", "1000000"))
CLONE_TIMEOUT_S = int(os.environ.get("CLONE_TIMEOUT_S", "120"))
MAX_ANALYSIS_S = int(os.environ.get("MAX_ANALYSIS_S", "600"))

# Clones live here only while a job runs; each job deletes its own folder.
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", Path(tempfile.gettempdir()) / "repolens"))
