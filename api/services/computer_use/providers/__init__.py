"""Computer Use provider registry."""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from ..runtime_config import is_anthropic_model
from .anthropic_provider import run_anthropic_loop
from .openai_provider import run_openai_loop


def run_provider_loop(
    session: Any,
    task: str,
    *,
    model: str,
    max_iterations: int,
    system: str | None,
    user_settings: dict[str, Any] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Dispatch to the correct provider loop based on model name."""
    if is_anthropic_model(model):
        yield from run_anthropic_loop(
            session,
            task,
            model=model,
            max_iterations=max_iterations,
            system=system,
        )
    else:
        yield from run_openai_loop(
            session,
            task,
            model=model,
            max_iterations=max_iterations,
            system=system,
            user_settings=user_settings,
        )
