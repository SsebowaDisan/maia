"""B1-CU-03 — Computer Use agent loop dispatcher.

Responsibility: resolve the active model and delegate to the correct provider.

Provider selection (based on model name):
  claude-*   → AnthropicProvider  (computer-use-2025-11-24 beta)
  everything else → OpenAIProvider  (vision + function calling;
                    works with GPT-4o, Ollama, LM Studio, vLLM, etc.)

Default model: read from OPENAI_CHAT_MODEL env var (i.e. whatever the user
has configured for the rest of the system).  Falls back to gpt-4o if not set.
ANTHROPIC_API_KEY users who want the claude loop should set
COMPUTER_USE_MODEL=claude-opus-4-6 (or any claude-* model).
"""
from __future__ import annotations

import logging
import os
from collections.abc import Generator
from typing import Any

from .browser_session import BrowserSession
from .providers import run_provider_loop

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 25


def _resolve_default_model(user_settings: dict[str, Any] | None = None) -> str:
    """Return the model to use when none is explicitly requested.

    Priority:
      1. user settings  — agent.computer_use_model (per-user persisted override)
      2. COMPUTER_USE_MODEL  — server-level dedicated override for computer use
      3. OPENAI_CHAT_MODEL   — whatever the user set for the whole system
      4. "gpt-4o"            — safe default that supports vision + tool use
    """
    if user_settings:
        stored = str(user_settings.get("agent.computer_use_model", "")).strip()
        if stored:
            return stored
    for env_var in ("COMPUTER_USE_MODEL", "OPENAI_CHAT_MODEL"):
        value = str(os.environ.get(env_var, "")).strip()
        if value:
            return value
    return "gpt-4o"


def run_agent_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str | None = None,
    max_iterations: int = _MAX_ITERATIONS,
    system: str | None = None,
    user_settings: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield SSE event dicts while running the Computer Use loop.

    Each event dict has at least:
      - ``event_type`` (str)
      - ``iteration``  (int)
      - optional ``screenshot_b64``, ``action``, ``text``, ``url``

    Args:
        session:        Active BrowserSession.
        task:           Natural-language task for the agent.
        model:          Model to use. Explicit value wins over all fallbacks.
        max_iterations: Hard cap on loop iterations (default 25).
        system:         Optional system-prompt override.
        user_settings:  Loaded user settings dict; consulted when model is None.
    """
    resolved_model = (str(model).strip() if model else "") or _resolve_default_model(user_settings)
    logger.info("Computer Use loop starting — model=%s task_preview=%.120s", resolved_model, task)

    yield from run_provider_loop(
        session,
        task,
        model=resolved_model,
        max_iterations=max_iterations,
        system=system,
    )
