"""The LLM behind an interface. Every AI answer goes through `complete_with_deadline`.

AnthropicProvider uses the official SDK's Messages API (checked against the installed SDK,
anthropic 2.3.0, and the Sonnet 5.5 / Haiku 5.5 migration guides):
- No sampling parameters: current models reject `temperature`, `top_p` and `top_k` (400).
  Reproducibility comes from a fixed model + effort + thinking setting + prompt version.
- Thinking runs by default, so a response can start with thinking blocks: the answer is the
  `text` blocks, selected by type. `LLM_THINKING=between_tools` (default) turns up-front
  thinking off on Sonnet 5.5, where `disabled` is a 400; it is accepted only at low, medium
  or high effort. Haiku 5.5's guide documents only `adaptive` (or no field): use
  `LLM_THINKING=adaptive` there.
- `output_config.effort` from `LLM_EFFORT` (default low: a short grounded answer).
- `stop_reason: "refusal"` (safety classifiers) is its own outcome, not an error.
- The SDK's own retries are off (`max_retries=0`): the retry here shares one deadline with
  the first attempt.

Errors are reduced to a kind and an HTTP status before anything is logged: the SDK's messages
can carry the response body, and nothing here may log the key, the prompt or the question.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Protocol

from app import config

log = logging.getLogger("repolens.qa")

THINKING = {
    "between_tools": {"type": "between_tools"},
    "adaptive": {"type": "adaptive"},
    "default": None,  # send no thinking field (the model's default)
}
EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    stop_reason: str | None = None
    refusal_category: str | None = None  # set when stop_reason == "refusal"

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"


class LLMError(Exception):
    """A failed call. `kind` is safe to log; the original exception is not kept."""

    def __init__(self, kind: str, *, retryable: bool, status: int | None = None,
                 retry_after: float | None = None):
        super().__init__(kind if status is None else f"{kind} (HTTP {status})")
        self.kind, self.retryable = kind, retryable
        self.status, self.retry_after = status, retry_after


class LLMProvider(Protocol):
    name: str  # model id, for the log and the eval output (never in API responses)
    settings: dict  # effort and thinking, recorded with the model in eval results

    def complete(self, system: str, prompt: str, max_tokens: int, timeout: float) -> Completion:
        """One attempt, no retry. Raises LLMError."""
        ...


def read_message(message) -> Completion:
    """The answer from a Messages API response: its text blocks by type (thinking blocks, which
    can come first, are skipped). A refusal keeps whatever text came before it."""
    text = "".join(block.text for block in message.content if block.type == "text")
    details = getattr(message, "stop_details", None)
    category = getattr(details, "category", None) if message.stop_reason == "refusal" else None
    return Completion(text, message.usage.input_tokens, message.usage.output_tokens,
                      message.stop_reason, category)


def _retry_after(headers) -> float | None:
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


class AnthropicProvider:
    def __init__(self, model: str, api_key: str, effort: str, thinking: str):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=0)
        self.name = model
        self.settings = {"effort": effort, "thinking": thinking}
        self._extra: dict = {"output_config": {"effort": effort}}
        if THINKING[thinking] is not None:
            self._extra["thinking"] = THINKING[thinking]

    def complete(self, system: str, prompt: str, max_tokens: int, timeout: float) -> Completion:
        a = self._anthropic
        try:
            message = self.client.messages.create(
                model=self.name,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
                **self._extra,
            )
        except a.APITimeoutError:
            raise LLMError("timeout", retryable=True) from None
        except a.APIConnectionError:
            raise LLMError("connection", retryable=True) from None
        except a.APIStatusError as e:
            status = e.status_code
            retryable = status in (408, 409, 429) or status >= 500
            kind = "rate_limit" if status == 429 else "server" if status >= 500 else "request"
            raise LLMError(kind, retryable=retryable, status=status,
                           retry_after=_retry_after(e.response.headers)) from None
        except a.AnthropicError:
            raise LLMError("sdk", retryable=False) from None
        return read_message(message)


@dataclass
class FakeProvider:
    """Scripted provider for tests. Each call takes the next item: a string (a plain text
    answer), an SDK `Message` (read exactly like a real response), or an LLMError to raise.
    Records what it was sent."""

    script: list = field(default_factory=list)
    name: str = "fake"
    settings: dict = field(default_factory=lambda: {"effort": "low", "thinking": "between_tools"})
    calls: list = field(default_factory=list)

    def complete(self, system: str, prompt: str, max_tokens: int, timeout: float) -> Completion:
        self.calls.append({"system": system, "prompt": prompt, "timeout": timeout})
        item = self.script.pop(0) if self.script else "I could not find this in the provided code."
        if isinstance(item, LLMError):
            raise item
        if isinstance(item, str):
            return Completion(item, len(system + prompt) // 4, len(item) // 4, "end_turn")
        return read_message(item)


def check_settings(effort: str, thinking: str) -> str | None:
    """Why these settings cannot work, or None."""
    if effort not in EFFORTS:
        return f"LLM_EFFORT must be one of {', '.join(EFFORTS)}"
    if thinking not in THINKING:
        return f"LLM_THINKING must be one of {', '.join(THINKING)}"
    if thinking == "between_tools" and effort in ("xhigh", "max"):
        return "LLM_THINKING=between_tools works only at low, medium or high effort"
    return None


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider | None:
    """The configured provider, or None (AI answers unavailable; graph questions still work)."""
    if config.LLM_PROVIDER != "anthropic" or not config.LLM_MODEL or not config.LLM_API_KEY:
        log.info("LLM not configured: AI answers are unavailable")
        return None
    problem = check_settings(config.LLM_EFFORT, config.LLM_THINKING)
    if problem:
        log.error("LLM settings rejected: %s; AI answers are unavailable", problem)
        return None
    return AnthropicProvider(config.LLM_MODEL, config.LLM_API_KEY, config.LLM_EFFORT,
                             config.LLM_THINKING)


def complete_with_deadline(
    provider: LLMProvider, system: str, prompt: str, *,
    max_tokens: int, deadline_s: float, min_retry_s: float,
    clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
) -> Completion:
    """At most two attempts inside one deadline. The retry happens only for retryable errors,
    only if at least `min_retry_s` is left after any wait, and a 429's retry-after is honoured
    only when it fits; otherwise the first error is raised."""
    end = clock() + deadline_s
    try:
        return provider.complete(system, prompt, max_tokens, timeout=end - clock())
    except LLMError as e:
        if not e.retryable:
            raise
        wait = e.retry_after if e.retry_after and e.retry_after > 0 else 0.5
        if end - clock() - wait < min_retry_s:
            log.warning("LLM %s; no time left for a retry", e)
            raise
        log.warning("LLM %s; retrying once in %.1fs", e, wait)
        sleep(wait)
    return provider.complete(system, prompt, max_tokens, timeout=end - clock())
