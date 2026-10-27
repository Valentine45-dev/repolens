"""Path rules shared by the graph filter and findings."""

from pathlib import PurePosixPath

TEST_DIRS = {"test", "tests", "__tests__", "examples"}


def is_test_path(path: str) -> bool:
    """test/, tests/, __tests__/, examples/ anywhere in the path, *.test.* / *.spec.*, or
    Python test_*.py / *_test.py."""
    p = PurePosixPath(path)
    parts = p.name.split(".")
    if TEST_DIRS & set(p.parts[:-1]):
        return True
    if len(parts) > 2 and parts[-2] in ("test", "spec"):
        return True
    return p.suffix == ".py" and (p.stem.startswith("test_") or p.stem.endswith("_test"))
