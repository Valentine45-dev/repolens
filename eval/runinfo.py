"""What every eval result records, so each number can be traced to what produced it.

Current models take no temperature, so an LLM result is reproducible only as: model + effort +
thinking setting + prompt version (+ retrieval settings and the commit). All are recorded.

Run eval scripts from the repo root with the backend's environment, e.g.
    uv run --project backend --env-file .env python eval/<script>.py
"""

import datetime
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import config  # noqa: E402
from app.qa.prompt import system_prompt  # noqa: E402

RESULTS = ROOT / "eval" / "results"

# Pinned in the eval scripts (detector_eval.py, realworld_precision.py); recorded here so every
# result file says which versions were meant.
BANDIT_PIN = "bandit==1.9.4"
SEMGREP_PIN = "semgrep==1.182.1"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def _powershell(expr: str) -> str:
    try:
        return subprocess.run(["powershell", "-NoProfile", "-Command", expr],
                              capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def machine_info() -> dict:
    ram = _powershell("[math]::Round((Get-CimInstance Win32_ComputerSystem)"
                      ".TotalPhysicalMemory/1GB,1)")
    return {
        "machine": socket.gethostname(),
        "cpu": _powershell("(Get-CimInstance Win32_Processor | select -First 1).Name")
        or platform.processor(),
        "cpu_threads": os.cpu_count(),
        "ram_gb": float(ram) if ram else None,
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "python": platform.python_version(),
    }


def package_versions() -> dict:
    out = {}
    for name in ("torch", "sentence-transformers", "transformers", "tree-sitter", "anthropic"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    return out


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
        # Uncommitted changes to tracked files (new result files do not count).
        "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        "run_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        **machine_info(),
        "packages": package_versions(),
        "max_analysis_s": config.MAX_ANALYSIS_S,
        "tool_pins": {"bandit": BANDIT_PIN, "semgrep": SEMGREP_PIN},
        # Free text for conditions of the run (e.g. which apps were open); set by the caller.
        "notes": "",
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
