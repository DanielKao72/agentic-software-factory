"""The ONE path through which every Gemini call flows.

- `call_with_retry` retries 429 RESOURCE_EXHAUSTED with exponential backoff
  (+ jitter, honouring the server's retryDelay hint) and reports each retry
  through `on_retry` so the orchestrator can log it into the run.
- `run_agent` executes one ADK agent in a brand-new in-memory session whose
  state contains only what the orchestrator passes in. No conversation is
  shared between agents.

When retries are exhausted, `RateLimitExhausted` is raised. The orchestrator
has already checkpointed the last completed step, so `factory resume CR-XXX`
continues from there instead of starting over.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from . import config

T = TypeVar("T")


class RateLimitExhausted(RuntimeError):
    """Raised after RETRY_MAX_ATTEMPTS consecutive 429s; the run is resumable."""


def _unwrap(exc: BaseException) -> BaseException:
    """ADK wraps model errors (e.g. DynamicNodeFailError); find the genai error."""
    seen = exc
    while seen is not None:
        if getattr(seen, "code", None) in (429, 503):
            return seen
        seen = seen.__cause__ or seen.__context__
    return exc


def is_rate_limited(exc: BaseException) -> bool:
    exc = _unwrap(exc)
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "")
    return code == 429 or "RESOURCE_EXHAUSTED" in status or "RESOURCE_EXHAUSTED" in str(exc)


def is_overloaded(exc: BaseException) -> bool:
    """503 UNAVAILABLE ('model is experiencing high demand') is also transient."""
    exc = _unwrap(exc)
    return getattr(exc, "code", None) == 503 or "UNAVAILABLE" in str(getattr(exc, "status", ""))


def retry_delay_hint(exc: BaseException) -> float | None:
    """Extract google.rpc.RetryInfo.retryDelay (e.g. '27s') if the server sent one."""
    details = getattr(_unwrap(exc), "details", None)
    text = repr(details) if details is not None else str(exc)
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", text)
    return float(match.group(1)) if match else None


def backoff_delay(attempt: int, hint: float | None, rng: Callable[[], float]) -> float:
    exp = config.RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
    delay = max(exp, hint or 0.0) + rng() * config.RETRY_BASE_DELAY_S
    return min(delay, config.RETRY_MAX_DELAY_S)


def call_with_retry(
    fn: Callable[[], T],
    *,
    on_retry: Callable[[dict], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
    max_attempts: int | None = None,
) -> T:
    attempts = max_attempts or config.RETRY_MAX_ATTEMPTS
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised unless transient
            kind = "429" if is_rate_limited(exc) else "503" if is_overloaded(exc) else None
            if kind is None:
                raise
            if attempt == attempts:
                raise RateLimitExhausted(f"{kind} persisted after {attempts} attempts") from exc
            delay = backoff_delay(attempt, retry_delay_hint(exc), rng)
            if on_retry:
                on_retry({"attempt": attempt, "delay_s": round(delay, 2), "error": kind})
            sleep(delay)
    raise AssertionError("unreachable")


@dataclass
class AgentResult:
    text: str
    state: dict[str, Any] = field(default_factory=dict)
    llm_calls: int = 0


def run_agent(
    agent: Any,
    message: str,
    *,
    initial_state: dict[str, Any] | None = None,
    on_retry: Callable[[dict], None] | None = None,
) -> AgentResult:
    """Run one ADK agent in a fresh session (retrying the whole call on 429)."""
    config.ensure_api_key()
    return call_with_retry(
        lambda: asyncio.run(_run_once(agent, message, dict(initial_state or {}))),
        on_retry=on_retry,
    )


async def _run_once(agent: Any, message: str, initial_state: dict[str, Any]) -> AgentResult:
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    service = InMemorySessionService()
    session = await service.create_session(
        app_name="factory", user_id="factory", state=initial_state, session_id=uuid.uuid4().hex
    )
    runner = Runner(app_name="factory", agent=agent, session_service=service)
    content = types.Content(role="user", parts=[types.Part(text=message)])
    final_text, llm_calls = "", 0
    async for event in runner.run_async(
        user_id="factory",
        session_id=session.id,
        new_message=content,
        run_config=RunConfig(max_llm_calls=config.MAX_AGENT_STEPS),
    ):
        if event.content is not None and event.content.role == "model":
            llm_calls += 1  # one model turn (tool-response events have role "user")
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)
    done = await service.get_session(app_name="factory", user_id="factory", session_id=session.id)
    return AgentResult(text=final_text, state=dict(done.state) if done else {}, llm_calls=llm_calls)
