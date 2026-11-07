"""Path rules shared by the graph filter and findings."""

from pathlib import PurePosixPath

TEST_DIRS = {"test", "tests", "__tests__", "examples"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
TEMPLATE_MARKERS = {"example", "sample", "template", "dist"}
TEST_FILES = {"tests.py", "conftest.py"}  # Django's default test module; pytest's fixtures


def is_test_path(path: str) -> bool:
    """test/, tests/, __tests__/, examples/ anywhere in the path, *.test.* / *.spec.*, or
    Python test_*.py / *_test.py / tests.py / conftest.py."""
    p = PurePosixPath(path)
    parts = p.name.split(".")
    if TEST_DIRS & set(p.parts[:-1]):
        return True
    if len(parts) > 2 and parts[-2] in ("test", "spec"):
        return True
    if p.name in TEST_FILES:
        return True
    return p.suffix == ".py" and (p.stem.startswith("test_") or p.stem.endswith("_test"))


def is_doc_path(path: str) -> bool:
    """Documentation text (.md, .rst, .txt). A secret in one is usually an example."""
    return PurePosixPath(path).suffix.lower() in DOC_SUFFIXES


def is_template_path(path: str) -> bool:
    """An example or template file: a name part after the first is example, sample, template or
    dist (`config.yml.example`, `settings.example.py`, `.env.example`)."""
    return any(part.lower() in TEMPLATE_MARKERS for part in PurePosixPath(path).name.split(".")[1:])


def is_nonrunning_path(path: str) -> bool:
    """Files that are read by people or copied before use, not run as they are: documentation
    and example or template files."""
    return is_doc_path(path) or is_template_path(path)
