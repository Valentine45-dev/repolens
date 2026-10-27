"""Rule-based detectors. The LLM never decides what is a finding; these rules do."""

from app.detect.javascript import detect_javascript
from app.detect.python import detect_python
from app.detect.rules import Hit
from app.ingest.parse import ParsedFile


def detect(path: str, language: str, content: str, parsed: ParsedFile) -> list[Hit]:
    if language == "python":
        return detect_python(content, parsed.imports)
    return detect_javascript(path, content, parsed.imports)
