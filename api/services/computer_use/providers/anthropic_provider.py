"""Computer Use — Anthropic provider.

Uses the claude-opus-4-6 (or any claude-* model) with the
computer-use-2025-11-24 beta tool.  Only used when the active model
is a Claude model.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Generator
from typing import Any

from ..action_executor import execute_action
from ..browser_session import BrowserSession, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from ..dom_snapshot import format_snapshot_block

logger = logging.getLogger(__name__)

_COMPUTER_TOOL = {
    "type": "computer_20251124",
    "name": "computer",
    "display_width_px": VIEWPORT_WIDTH,
    "display_height_px": VIEWPORT_HEIGHT,
    "display_number": 1,
}


def _read_retry_attempts() -> int:
    raw = str(os.environ.get("MAIA_COMPUTER_USE_PROVIDER_RETRY_ATTEMPTS", "3")).strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 3
    return max(1, min(parsed, 6))


_MAX_API_ATTEMPTS = _read_retry_attempts()
_RETRY_BASE_SECONDS = 0.6


def run_anthropic_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str,
    max_iterations: int,
    system: str | None,
) -> Generator[dict[str, Any], None, None]:
    """Run the Anthropic computer-use beta loop."""
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        yield {"event_type": "error", "detail": "anthropic package not installed. Run: pip install anthropic"}
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield {"event_type": "error", "detail": "ANTHROPIC_API_KEY is not set. Configure it in settings or switch to an OpenAI-compatible model."}
        return

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = system or (
        "You are a computer use agent. Complete the user's task by controlling the browser. "
        "Always start by taking a screenshot to see the current state."
    )
    messages: list[dict[str, Any]] = []

    for iteration in range(1, max_iterations + 1):
        b64 = session.screenshot_b64()
        dom_text = format_snapshot_block(session.dom_snapshot())
        yield {"event_type": "screenshot", "iteration": iteration, "screenshot_b64": b64, "url": session.current_url()}

        if not messages:
            user_content: list[dict[str, Any]] = [{"type": "text", "text": task}]
            if dom_text:
                user_content.append({"type": "text", "text": dom_text})
            user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}})
            messages.append({"role": "user", "content": user_content})
        else:
            if dom_text:
                messages[-1]["content"].append({"type": "text", "text": dom_text})
            messages[-1]["content"].append(
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
            )

        try:
            response = _create_message_with_retry(
                client=client,
                model=model,
                system_prompt=system_prompt,
                messages=messages,
            )
        except Exception as exc:
            yield {"event_type": "error", "iteration": iteration, "detail": str(exc)[:400]}
            return

        tool_uses: list[Any] = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                yield {"event_type": "text", "iteration": iteration, "text": block.text}
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_uses.append(block)

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_uses:
            yield {"event_type": "done", "iteration": iteration, "url": session.current_url()}
            return

        tool_results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            tool_input: dict[str, Any] = dict(tool_use.input or {})
            yield {"event_type": "action", "iteration": iteration, "tool_id": tool_use.id, "action": tool_input.get("action"), "input": tool_input}
            try:
                result = execute_action(session, tool_input)
                content: list[dict[str, Any]] = [{"type": "text", "text": f"Action '{result['action']}' executed."}]
                if "screenshot_b64" in result:
                    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": result["screenshot_b64"]}}]
            except Exception as exc:
                content = [{"type": "text", "text": f"Error: {exc}"}]
            tool_results.append({"type": "tool_result", "tool_use_id": tool_use.id, "content": content})

        messages.append({"role": "user", "content": tool_results})

    yield {"event_type": "max_iterations", "iteration": max_iterations, "url": session.current_url()}


def _create_message_with_retry(
    *,
    client: Any,
    model: str,
    system_prompt: str,
    messages: list[dict[str, Any]],
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        try:
            return client.beta.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=[_COMPUTER_TOOL],  # type: ignore[arg-type]
                messages=messages,
                betas=["computer-use-2025-11-24"],
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= _MAX_API_ATTEMPTS or not _is_retryable_exception(exc):
                raise
            sleep_for = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Computer Use Anthropic call failed (attempt %d/%d) status=%s; retrying in %.1fs: %s",
                attempt,
                _MAX_API_ATTEMPTS,
                _exception_status_code(exc),
                sleep_for,
                str(exc)[:220],
            )
            time.sleep(sleep_for)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Anthropic completion retry loop failed without an exception.")


def _exception_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
    return None


def _is_retryable_exception(exc: Exception) -> bool:
    status = _exception_status_code(exc)
    if isinstance(status, int):
        return status in {408, 409, 425, 429} or status >= 500
    lowered = str(exc).lower()
    retryable_tokens = (
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "connection refused",
        "rate limit",
        "too many requests",
        "server error",
        "bad gateway",
        "gateway timeout",
        "service unavailable",
        "network",
    )
    return any(token in lowered for token in retryable_tokens)
