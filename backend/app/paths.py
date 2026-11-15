"""Path rules shared by the graph filter and findings."""

from pathlib import PurePosixPath

# Folder names (any case) that hold tests, examples or benchmarks. `testing/` is left out on
# purpose: packages ship it as product code (IPython/testing), and hiding real findings there
# would be worse than showing a few test helpers.
TEST_DIRS = {"test", "tests", "__tests__", "spec", "e2e", "cypress", "examples", "example",
             "samples", "benchmarks"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
TEMPLATE_MARKERS = {"example", "sample", "template", "dist"}
TEST_FILES = {"tests.py", "conftest.py"}  # Django's default test module; pytest's fixtures
CODE_SUFFIXES = {".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def is_test_path(path: str) -> bool:
    """A test/example/benchmark folder anywhere in the path (TEST_DIRS, any case),
    *.test.* / *.spec.*, tests.py / conftest.py, or a code file named test / tests / spec,
    test_*, *_test, *-test or *_spec (any language, any case)."""
    p = PurePosixPath(path)
    if TEST_DIRS & {d.lower() for d in p.parts[:-1]}:
        return True
    parts = p.name.split(".")
    if len(parts) > 2 and parts[-2].lower() in ("test", "spec"):
        return True
    if p.name in TEST_FILES:
        return True
    if p.suffix.lower() not in CODE_SUFFIXES:
        return False
    stem = p.stem.lower()
    return (stem in ("test", "tests", "spec") or stem.startswith("test_")
            or stem.endswith(("_test", "-test", "_spec")))


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
