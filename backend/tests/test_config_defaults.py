"""Product defaults that other documents quote (README, .env.example)."""

import runpy

from app import config


def test_analysis_time_limit_default_is_1200_s(monkeypatch):
    monkeypatch.delenv("MAX_ANALYSIS_S", raising=False)
    # A fresh copy of the module's namespace: the imported `config` is left as it is.
    assert runpy.run_path(config.__file__)["MAX_ANALYSIS_S"] == 1200
