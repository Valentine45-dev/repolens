"""Rule-based detectors. The LLM never decides what is a finding; these rules do."""

from app.detect.python import detect_python
from app.detect.rules import Hit
from app.ingest.parse import ParsedFile


def detect(language: str, content: str, parsed: ParsedFile) -> list[Hit]:
    if language == "python":
        return detect_python(content, parsed.imports)
    return []  # JS/TS rules: Day 3 task 2
