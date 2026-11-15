import pytest

from app.paths import is_test_path


@pytest.mark.parametrize("path", [
    # C-05: layouts the old rule missed (review table)
    "test.js", "test.py", "src/foo_test.js", "src/test_foo.js", "src/foo-test.ts",
    "spec/foo_spec.js", "cypress/a.cy.ts", "e2e/login.ts", "client/e2e/support/ui.ts",
    "benchmarks/run.py", "example/app.py", "samples/app.py", "Tests/a.py", "TESTS/b.js",
    "tests.js", "src/Foo.Test.ts",
    # controls that were already test code
    "latest/tests.py", "tests/a.py", "src/foo.test.ts", "Tests/test_a.py", "conftest.py",
    "examples/auth/index.js", "__tests__/x.js", "pkg/x_test.py",
])
def test_test_paths(path):
    assert is_test_path(path)


@pytest.mark.parametrize("path", [
    # `testing/` is product code in shipped packages (IPython/testing): kept, by decision.
    "testing/helpers.py", "IPython/testing/decorators.py", "src/flask/testing.py",
    # names that only look like tests, and non-code files
    "src/contest.py", "src/latest.js", "src/attest_x.py", "docs/test.md", "test.txt",
    "src/sample.py", "lib/benchmark.js", "src/specs_parser.ts", "app/inspect_test_data.json",
])
def test_not_test_paths(path):
    assert not is_test_path(path)
