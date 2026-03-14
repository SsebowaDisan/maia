"""Computer Use — Anthropic provider.

Uses the claude-opus-4-6 (or any claude-* model) with the
computer-use-2025-11-24 beta tool.  Only used when the active model
is a Claude model.
"""
from __future__ import annotations

import logging
import os
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
            response = client.beta.messages.create(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                tools=[_COMPUTER_TOOL],  # type: ignore[arg-type]
                messages=messages,
                betas=["computer-use-2025-11-24"],
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
