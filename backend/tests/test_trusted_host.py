"""The API answers only to its own host names, which stops DNS rebinding on port 8000."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import config
from app.main import app


def test_the_real_app_has_the_middleware_with_the_trusted_hosts():
    # The tests below use a small app, so they need no database at startup.
    middleware = [m for m in app.user_middleware if m.cls is TrustedHostMiddleware]
    assert len(middleware) == 1
    assert middleware[0].kwargs["allowed_hosts"] == ["127.0.0.1", "localhost", "api"]


@pytest.fixture
def small_client():
    small = FastAPI()
    small.add_middleware(TrustedHostMiddleware, allowed_hosts=list(config.TRUSTED_HOSTS))
    small.get("/health")(lambda: {"status": "ok"})
    return TestClient(small, base_url="http://127.0.0.1")


@pytest.mark.parametrize("host", ["127.0.0.1:8000", "127.0.0.1", "localhost:8000", "localhost",
                                  "api:8000"])  # api:8000 is the compose proxy (vite.config.ts)
def test_our_own_hosts_pass(small_client, host):
    assert small_client.get("/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "evil.example:8000", "testserver",
                                  "localhost.evil.example", "api.evil.example"])
def test_other_hosts_are_refused(small_client, host):
    r = small_client.get("/health", headers={"Host": host})
    assert r.status_code == 400
    assert "ok" not in r.text
