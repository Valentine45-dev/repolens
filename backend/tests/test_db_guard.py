import pytest
from conftest import check_test_database_url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://repolens:repolens@localhost:5433/repolens_test",
        "postgresql://u@h/x_test?sslmode=disable",
        "dbname=repolens_test host=localhost",
    ],
)
def test_accepts_test_database(url):
    assert check_test_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://repolens:repolens@localhost:5433/repolens",
        "postgresql://u@h/test_repolens",
        "postgresql://u@h/",
        "host=localhost",
    ],
)
def test_rejects_other_databases(url):
    with pytest.raises(pytest.UsageError):
        check_test_database_url(url)
