"""Shared LLM utility for Phase-2 agent services.

Responsibility: lightweight JSON-mode LLM call used by resolver and
improvement modules.  Uses the anthropic SDK directly.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # cheap model for routing/meta tasks


def call_llm_json(
    prompt: str,
    *,
    temperature: float = 0.0,
    max_tokens: int = 500,
    model: str = _DEFAULT_MODEL,
) -> dict[str, Any]:
    """Send a prompt to Claude and parse the response as JSON.

    Args:
        prompt: Full user-turn prompt.  Should instruct Claude to reply with JSON.
        temperature: Sampling temperature.
        max_tokens: Max response tokens.
        model: Claude model ID to use.

    Returns:
        Parsed JSON dict from Claude's response.

    Raises:
        RuntimeError: If the API call fails or the response is not valid JSON.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic") from exc

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set.")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    # Strip markdown code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        stripped = inner.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.debug("LLM did not return valid JSON: %s", text[:200])
        raise RuntimeError(f"LLM response was not valid JSON: {text[:200]}") from exc
