"""B1-CU-03 - Computer Use agent loop dispatcher.

Responsibility: resolve the active model and delegate to the correct provider.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from .browser_session import BrowserSession
from .providers import run_provider_loop
from .runtime_config import resolve_effective_model

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 25


def run_agent_loop(
    session: BrowserSession,
    task: str,
    *,
    model: str | None = None,
    max_iterations: int = _MAX_ITERATIONS,
    system: str | None = None,
    user_settings: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield SSE event dicts while running the Computer Use loop."""
    resolved_model, source = resolve_effective_model(
        explicit_model=model,
        user_settings=user_settings,
    )
    logger.info(
        "Computer Use loop starting - model=%s source=%s task_preview=%.120s",
        resolved_model,
        source,
        task,
    )

    yield from run_provider_loop(
        session,
        task,
        model=resolved_model,
        max_iterations=max_iterations,
        system=system,
        user_settings=user_settings,
    )
