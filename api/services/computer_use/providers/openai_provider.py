"""Computer Use - OpenAI-compatible provider.

Works with any OpenAI-compatible vision model:
  - OpenAI GPT-4o / GPT-4o-mini
  - Ollama (qwen2.5vl, llava, minicpm-v, etc.)
  - LM Studio, vLLM, Together AI, Groq, and similar APIs
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Generator
from typing import Any

from ..action_executor import execute_action
from ..browser_session import BrowserSession, VIEWPORT_HEIGHT, VIEWPORT_WIDTH
from ..dom_snapshot import format_snapshot_block
from ..runtime_config import (
    DEFAULT_OPENAI_BASE_URL,
    normalize_model_name,
    resolve_openai_base_url,
)

logger = logging.getLogger(__name__)


_COMPUTER_FUNCTION = {
    "type": "function",
    "function": {
        "name": "computer_action",
        "description": (
            "Control the browser to complete a task. "
            "Coordinates are pixel positions within a "
            f"{VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT} viewport."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "screenshot",
                        "left_click",
                        "double_click",
                        "right_click",
                        "mouse_move",
                        "left_click_drag",
                        "type",
                        "key",
                        "scroll",
                        "cursor_position",
                    ],
                    "description": "Action to perform on the browser.",
                },
                "coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "[x, y] pixel coordinate. Required for click, move, scroll.",
                },
                "text": {
                    "type": "string",
                    "description": (
                        "Text to type (for 'type' action) or key name "
                        "(for 'key' action, e.g. 'Return', 'ctrl+a')."
                    ),
                },
                "scroll_direction": {
                    "type": "string",
                    "enum": ["up", "down", "left", "right"],
                    "description": "Direction for scroll action.",
                },
                "scroll_amount": {
                    "type": "integer",
                    "description": "Number of scroll notches (default 3).",
                },
                "start_coordinate": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "Start [x, y] for left_click_drag.",
                },
            },
            "required": ["action"],
        },
    },
}


def _api_key() -> str:
    return str(os.environ.get("OPENAI_API_KEY", "")).strip()


def _read_retry_attempts() -> int:
    raw = str(os.environ.get("MAIA_COMPUTER_USE_PROVIDER_RETRY_ATTEMPTS", "3")).strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 3
    return max(1, min(parsed, 6))


_MAX_API_ATTEMPTS = _read_retry_attempts()
_RETRY_BASE_SECONDS = 0.6


def run_openai_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str,
    max_iterations: int,
    system: str | None,
    user_settings: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Run the computer-use loop using an OpenAI-compatible model."""
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        yield {"event_type": "error", "detail": "openai package not installed. Run: pip install openai"}
        return

    resolved_model = normalize_model_name(model)
    if not resolved_model:
        yield {"event_type": "error", "detail": "No valid computer-use model resolved."}
        return

    api_key = _api_key()
    base_url, base_source = resolve_openai_base_url(model=model, user_settings=user_settings)

    # Local OpenAI-compatible providers usually do not need a real API key.
    if not api_key and base_url == DEFAULT_OPENAI_BASE_URL:
        yield {
            "event_type": "error",
            "detail": (
                "OPENAI_API_KEY is not set, and the runtime resolved to api.openai.com. "
                "Configure a local OpenAI-compatible base URL or set OPENAI_API_KEY."
            ),
        }
        return

    logger.info(
        "Computer Use OpenAI-compatible runtime - model=%s base_url=%s source=%s",
        resolved_model,
        base_url,
        base_source,
    )
    client = OpenAI(
        api_key=api_key or "not-required",
        base_url=base_url,
    )

    system_prompt = system or (
        "You are a computer use agent with access to a real browser. "
        "Complete the user's task by calling the computer_action tool. "
        "After each action, call computer_action with action='screenshot' to see the result. "
        "When the task is complete, respond with a final text summary and do not call any more tools."
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for iteration in range(1, max_iterations + 1):
        b64 = session.screenshot_b64()
        dom_text = format_snapshot_block(session.dom_snapshot())
        yield {
            "event_type": "screenshot",
            "iteration": iteration,
            "screenshot_b64": b64,
            "url": session.current_url(),
        }

        if iteration == 1:
            user_content: list[dict[str, Any]] = [{"type": "text", "text": task}]
        else:
            user_content = []

        if dom_text:
            user_content.append({"type": "text", "text": dom_text})
        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        messages.append({"role": "user", "content": user_content})

        try:
            response = _create_chat_completion_with_retry(
                client=client,
                model=resolved_model,
                messages=messages,
            )
        except Exception as exc:
            detail = str(exc)[:400]
            yield {"event_type": "error", "iteration": iteration, "detail": detail}
            return

        choice = response.choices[0]
        assistant_message = choice.message

        if assistant_message.content:
            yield {"event_type": "text", "iteration": iteration, "text": assistant_message.content}

        if not assistant_message.tool_calls:
            yield {"event_type": "done", "iteration": iteration, "url": session.current_url()}
            return

        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in assistant_message.tool_calls
                ],
            }
        )

        tool_results: list[dict[str, Any]] = []
        for tool_call in assistant_message.tool_calls:
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except Exception:
                args = {}

            action = str(args.get("action", ""))
            yield {
                "event_type": "action",
                "iteration": iteration,
                "tool_id": tool_call.id,
                "action": action,
                "input": args,
            }

            tool_input = _normalise_args(args)
            try:
                result = execute_action(session, tool_input)
                if "screenshot_b64" in result:
                    result_text = f"Screenshot taken after {action}."
                else:
                    result_text = f"Action '{result['action']}' executed successfully."
            except Exception as exc:
                result_text = f"Error executing {action}: {exc}"

            tool_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_text,
                }
            )

        messages.extend(tool_results)

    yield {"event_type": "max_iterations", "iteration": max_iterations, "url": session.current_url()}


def _normalise_args(args: dict[str, Any]) -> dict[str, Any]:
    """Normalize function-call args for action_executor."""
    return dict(args)


def _create_chat_completion_with_retry(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
) -> Any:
    last_exc: Exception | None = None
    candidate_messages = messages
    attempted_string_fallback = False
    for attempt in range(1, _MAX_API_ATTEMPTS + 1):
        try:
            return client.chat.completions.create(
                model=model,
                messages=candidate_messages,  # type: ignore[arg-type]
                tools=[_COMPUTER_FUNCTION],  # type: ignore[arg-type]
                tool_choice="auto",
                max_tokens=1024,
            )
        except Exception as exc:
            last_exc = exc
            if (
                not attempted_string_fallback
                and _requires_string_user_content(exc)
                and _has_structured_user_content(candidate_messages)
            ):
                attempted_string_fallback = True
                candidate_messages = _coerce_user_content_to_string(candidate_messages)
                logger.info(
                    "Computer Use runtime rejected structured user content; retrying with string-only user messages."
                )
                continue
            if attempt >= _MAX_API_ATTEMPTS or not _is_retryable_exception(exc):
                raise
            sleep_for = _RETRY_BASE_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "Computer Use OpenAI call failed (attempt %d/%d) status=%s; retrying in %.1fs: %s",
                attempt,
                _MAX_API_ATTEMPTS,
                _exception_status_code(exc),
                sleep_for,
                str(exc)[:220],
            )
            time.sleep(sleep_for)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("OpenAI completion retry loop failed without an exception.")


def _has_structured_user_content(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        if str(message.get("role") or "").strip().lower() != "user":
            continue
        if isinstance(message.get("content"), list):
            return True
    return False


def _coerce_user_content_to_string(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for message in messages:
        cloned = dict(message)
        if str(cloned.get("role") or "").strip().lower() != "user":
            normalized.append(cloned)
            continue
        content = cloned.get("content")
        if not isinstance(content, list):
            normalized.append(cloned)
            continue
        parts: list[str] = []
        saw_image = False
        for item in content:
            if not isinstance(item, dict):
                text = " ".join(str(item or "").split()).strip()
                if text:
                    parts.append(text)
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "text":
                text = " ".join(str(item.get("text") or "").split()).strip()
                if text:
                    parts.append(text)
                continue
            if item_type == "image_url":
                saw_image = True
        if saw_image:
            parts.append("Screenshot is available in the current browser state.")
        cloned["content"] = "\n\n".join(part for part in parts if part).strip()
        normalized.append(cloned)
    return normalized


def _requires_string_user_content(exc: Exception) -> bool:
    lowered = str(exc or "").lower()
    return "content must be a string" in lowered and "messages[" in lowered


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
