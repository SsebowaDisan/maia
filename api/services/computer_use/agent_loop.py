"""B1-CU-03 — Computer Use agent loop.

Responsibility: run the Claude computer-use loop for a BrowserSession and
yield SSE-compatible event dicts.

Loop:
  1. Take screenshot.
  2. Send screenshot + task to Claude (claude-opus-4-6, computer-use-2025-11-24 beta).
  3. Receive tool_use blocks → execute each via action_executor.
  4. Feed tool results back to Claude.
  5. Repeat until Claude emits end_turn or max_iterations reached.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Generator
from typing import Any

from .action_executor import execute_action
from .browser_session import BrowserSession, VIEWPORT_WIDTH, VIEWPORT_HEIGHT

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-opus-4-6"
_MAX_ITERATIONS = 25
_COMPUTER_TOOL = {
    "type": "computer_20251124",
    "name": "computer",
    "display_width_px": VIEWPORT_WIDTH,
    "display_height_px": VIEWPORT_HEIGHT,
    "display_number": 1,
}


def run_agent_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str = _DEFAULT_MODEL,
    max_iterations: int = _MAX_ITERATIONS,
    system: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield event dicts while running the Computer Use loop.

    Each event dict has at least:
      - ``event_type`` (str)
      - ``iteration`` (int)
      - optional ``screenshot_b64``, ``action``, ``text``
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError as exc:
        yield {"event_type": "error", "detail": "anthropic package not installed. Run: pip install anthropic"}
        return

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield {"event_type": "error", "detail": "ANTHROPIC_API_KEY environment variable not set."}
        return

    client = anthropic.Anthropic(api_key=api_key)

    messages: list[dict[str, Any]] = []
    system_prompt = system or (
        "You are a computer use agent. Complete the user's task by controlling the browser. "
        "Always start by taking a screenshot to see the current state."
    )

    for iteration in range(1, max_iterations + 1):
        # ── Take screenshot and append as user message ─────────────────────
        b64 = session.screenshot_b64()
        yield {
            "event_type": "screenshot",
            "iteration": iteration,
            "screenshot_b64": b64,
            "url": session.current_url(),
        }

        if not messages:
            # First turn: task text + initial screenshot
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": task},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                ],
            })
        else:
            # Subsequent turns: screenshot is the tool result
            messages[-1]["content"].append(
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
            )

        # ── Call Claude ────────────────────────────────────────────────────
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

        # ── Emit any text content from Claude ─────────────────────────────
        tool_uses: list[Any] = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                yield {"event_type": "text", "iteration": iteration, "text": block.text}
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_uses.append(block)

        # Append Claude's assistant turn to messages
        messages.append({"role": "assistant", "content": response.content})

        # ── Check stop condition ───────────────────────────────────────────
        if response.stop_reason == "end_turn" or not tool_uses:
            yield {"event_type": "done", "iteration": iteration, "url": session.current_url()}
            return

        # ── Execute tool calls ─────────────────────────────────────────────
        tool_results: list[dict[str, Any]] = []
        for tool_use in tool_uses:
            tool_id: str = tool_use.id
            tool_name: str = tool_use.name
            tool_input: dict[str, Any] = dict(tool_use.input or {})

            yield {
                "event_type": "action",
                "iteration": iteration,
                "tool_id": tool_id,
                "action": tool_input.get("action"),
                "input": tool_input,
            }

            try:
                result = execute_action(session, tool_input)
                content: list[dict[str, Any]] = [{"type": "text", "text": f"Action '{result['action']}' executed."}]
                # If the action produced a screenshot, include it
                if "screenshot_b64" in result:
                    content = [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": result["screenshot_b64"]}}
                    ]
            except Exception as exc:
                content = [{"type": "text", "text": f"Error: {exc}"}]

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": content,
            })

        # Next user message contains all tool results
        messages.append({"role": "user", "content": tool_results})

    yield {"event_type": "max_iterations", "iteration": max_iterations, "url": session.current_url()}
