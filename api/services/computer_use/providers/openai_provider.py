"""Computer Use — OpenAI-compatible provider.

Works with any OpenAI-compatible vision model:
  - OpenAI GPT-4o / GPT-4o-mini
  - Ollama (qwen2-vl, llava, minicpm-v, etc.)  via OPENAI_API_BASE
  - LM Studio, vLLM, Together AI, Groq, etc.

Model is read from OPENAI_CHAT_MODEL env var (or passed explicitly).
Base URL is read from OPENAI_API_BASE (defaults to https://api.openai.com/v1).

The computer actions are exposed as a function-calling tool so any model
that supports tool_use / function calling can drive the browser.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from typing import Any

from ..action_executor import execute_action
from ..browser_session import BrowserSession, VIEWPORT_WIDTH, VIEWPORT_HEIGHT
from ..dom_snapshot import format_snapshot_block

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.openai.com/v1"

# The computer tool exposed as an OpenAI function — model-agnostic
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
                    "description": "Text to type (for 'type' action) or key name (for 'key' action, e.g. 'Return', 'ctrl+a').",
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


def _base_url() -> str:
    return str(os.environ.get("OPENAI_API_BASE", _DEFAULT_BASE)).strip() or _DEFAULT_BASE


def run_openai_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str,
    max_iterations: int,
    system: str | None,
) -> Generator[dict[str, Any], None, None]:
    """Run the computer-use loop using any OpenAI-compatible vision model."""
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        yield {"event_type": "error", "detail": "openai package not installed. Run: pip install openai"}
        return

    api_key = _api_key()
    base_url = _base_url()

    # Ollama and some local providers don't require a real API key
    if not api_key and base_url == _DEFAULT_BASE:
        yield {"event_type": "error", "detail": "OPENAI_API_KEY is not set. Set it in settings or configure OPENAI_API_BASE to point to a local model."}
        return

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

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]

    for iteration in range(1, max_iterations + 1):
        b64 = session.screenshot_b64()
        dom_text = format_snapshot_block(session.dom_snapshot())
        yield {"event_type": "screenshot", "iteration": iteration, "screenshot_b64": b64, "url": session.current_url()}

        # Build the user message: task text on first turn, DOM index + screenshot every turn
        if iteration == 1:
            user_content: list[dict[str, Any]] = [
                {"type": "text", "text": task},
            ]
        else:
            user_content = []

        if dom_text:
            user_content.append({"type": "text", "text": dom_text})

        user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

        messages.append({"role": "user", "content": user_content})

        # Call the model
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore[arg-type]
                tools=[_COMPUTER_FUNCTION],  # type: ignore[arg-type]
                tool_choice="auto",
                max_tokens=1024,
            )
        except Exception as exc:
            yield {"event_type": "error", "iteration": iteration, "detail": str(exc)[:400]}
            return

        choice = response.choices[0]
        assistant_message = choice.message

        # Emit any text the model produced
        if assistant_message.content:
            yield {"event_type": "text", "iteration": iteration, "text": assistant_message.content}

        # No tool calls → model is done
        if not assistant_message.tool_calls:
            yield {"event_type": "done", "iteration": iteration, "url": session.current_url()}
            return

        # Append assistant turn to history
        messages.append({"role": "assistant", "content": assistant_message.content or "", "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in assistant_message.tool_calls
        ]})

        # Execute each tool call and collect results
        tool_results: list[dict[str, Any]] = []
        for tool_call in assistant_message.tool_calls:
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except Exception:
                args = {}

            action = str(args.get("action", ""))
            yield {"event_type": "action", "iteration": iteration, "tool_id": tool_call.id, "action": action, "input": args}

            # Map openai function args to action_executor format
            tool_input = _normalise_args(args)

            try:
                result = execute_action(session, tool_input)
                if "screenshot_b64" in result:
                    result_text = f"Screenshot taken after {action}."
                else:
                    result_text = f"Action '{result['action']}' executed successfully."
            except Exception as exc:
                result_text = f"Error executing {action}: {exc}"

            tool_results.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_text,
            })

        messages.extend(tool_results)

    yield {"event_type": "max_iterations", "iteration": max_iterations, "url": session.current_url()}


def _normalise_args(args: dict[str, Any]) -> dict[str, Any]:
    """Normalise OpenAI function args to the action_executor dict format."""
    normalised = dict(args)
    # The action executor uses "coordinate" for [x, y]; our tool uses the same name — pass through.
    # Map "text" action key to the same field name (action_executor reads tool_input["text"]).
    return normalised
