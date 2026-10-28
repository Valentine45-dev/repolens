"""What every eval result records, so each number can be traced to what produced it.

Current models take no temperature, so an LLM result is reproducible only as: model + effort +
thinking setting + prompt version (+ retrieval settings and the commit). All are recorded.

Run eval scripts from the repo root with the backend's environment, e.g.
    uv run --project backend --env-file .env python eval/<script>.py
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.qa.prompt import system_prompt  # noqa: E402

RESULTS = ROOT / "eval" / "results"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def run_info(provider=None, *, llm_used: bool) -> dict:
    """`provider` is the LLMProvider actually used (its model and settings win over config, so
    a FakeProvider run says "fake"). The LLM block is always present; `llm_used` says whether
    this eval called it."""
    llm = {
        "provider": config.LLM_PROVIDER,
        "model": provider.name if provider else (config.LLM_MODEL or None),
        "effort": provider.settings["effort"] if provider else config.LLM_EFFORT,
        "thinking": provider.settings["thinking"] if provider else config.LLM_THINKING,
        "max_tokens": config.LLM_MAX_TOKENS,
        "prompt_version": system_prompt().version,
    }
    return {
        "commit_sha": _git("rev-parse", "HEAD"),
        "dirty": bool(_git("status", "--porcelain")),
        "run_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "embedder": config.EMBEDDER,
        "embed_model": config.EMBED_MODEL,
        "embed_revision": config.EMBED_MODEL_REVISION,
        "llm_used": llm_used,
        "llm": llm,
        "retrieval": {
            "top_k": config.QA_TOP_K,
            "graph_expansion": config.QA_GRAPH_EXPANSION,
            "expand_max": config.QA_EXPAND_MAX,
            "context_tokens": config.QA_CONTEXT_TOKENS,
        },
    }


def save_results(name: str, info: dict, results: dict, directory: Path = RESULTS) -> Path:
    """Write `<name>-<UTC time>-<sha7>.json` with the run info first, then the results."""
    directory.mkdir(parents=True, exist_ok=True)
    stamp = info["run_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    path = directory / f"{name}-{stamp}-{info['commit_sha'][:7]}.json"
    path.write_text(json.dumps({"run": info, **results}, indent=2) + "\n", encoding="utf-8")
    return path


def header(info: dict) -> str:
    """One line for the console, before the numbers."""
    llm = info["llm"]
    parts = [f"commit {info['commit_sha'][:7]}{' (dirty)' if info['dirty'] else ''}",
             f"embed {info['embed_model']}@{info['embed_revision'][:7]}"]
    if info["llm_used"]:
        parts.append(f"model {llm['model']} effort={llm['effort']} thinking={llm['thinking']}"
                     f" prompt {llm['prompt_version']}")
    return " | ".join(parts)
