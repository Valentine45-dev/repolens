"""Product defaults that other documents quote (README, .env.example)."""

import runpy

from app import config


def test_analysis_time_limit_default_is_1200_s(monkeypatch):
    monkeypatch.delenv("MAX_ANALYSIS_S", raising=False)
    # A fresh copy of the module's namespace: the imported `config` is left as it is.
    assert runpy.run_path(config.__file__)["MAX_ANALYSIS_S"] == 1200


def test_step5_defaults(monkeypatch):
    """v2.1 by the Step 5 adoption rules: hybrid on (B), docs off (A), claim check on (C)."""
    for name in ("QA_HYBRID", "QA_DOC_POOL", "QA_CLAIM_CHECK"):
        monkeypatch.delenv(name, raising=False)
    fresh = runpy.run_path(config.__file__)
    assert (fresh["QA_HYBRID"], fresh["QA_DOC_POOL"], fresh["QA_CLAIM_CHECK"]) == (True, 0, True)
