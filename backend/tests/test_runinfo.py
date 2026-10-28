"""Eval results record what produced them: commit, embedder, and the LLM's model, effort,
thinking setting and prompt version (no temperature on current models)."""

import importlib.util
import json
from pathlib import Path

from app.qa.llm import FakeProvider

RUNINFO = Path(__file__).resolve().parents[2] / "eval" / "runinfo.py"


def load():
    spec = importlib.util.spec_from_file_location("runinfo", RUNINFO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_info_records_model_effort_thinking_and_sha(tmp_path):
    runinfo = load()
    fake = FakeProvider(settings={"effort": "medium", "thinking": "adaptive"})
    info = runinfo.run_info(fake, llm_used=True)
    assert len(info["commit_sha"]) == 40 and info["llm_used"] is True
    assert {k: info["llm"][k] for k in ("model", "effort", "thinking")} == {
        "model": "fake", "effort": "medium", "thinking": "adaptive"}
    assert info["llm"]["prompt_version"] == "2026-10-28.1"
    assert info["embed_model"] and info["embed_revision"]
    header = runinfo.header(info)
    assert "model fake effort=medium thinking=adaptive" in header

    path = runinfo.save_results("check", info, {"recall": 0.5}, directory=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["run"]["llm"]["effort"] == "medium" and saved["recall"] == 0.5
    assert path.name.startswith("check-") and path.name.endswith(f"-{info['commit_sha'][:7]}.json")


def test_run_info_without_llm_still_records_the_configured_settings():
    from app import config

    info = load().run_info(llm_used=False)
    assert info["llm_used"] is False
    assert (info["llm"]["effort"], info["llm"]["thinking"]) == (config.LLM_EFFORT,
                                                                config.LLM_THINKING)
