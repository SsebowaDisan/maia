"""Computer Use provider registry.

Selects the right provider based on the model name:
  - claude-*  → AnthropicProvider  (uses computer-use-2025-11-24 beta)
  - anything else → OpenAIProvider  (OpenAI-compatible vision + function calling;
                                     works with GPT-4o, Ollama, LM Studio, etc.)
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

from .anthropic_provider import run_anthropic_loop
from .openai_provider import run_openai_loop


def is_anthropic_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("claude")


def run_provider_loop(
    session: Any,
    task: str,
    *,
    model: str,
    max_iterations: int,
    system: str | None,
) -> Generator[dict[str, Any], None, None]:
    """Dispatch to the correct provider loop based on model name."""
    if is_anthropic_model(model):
        yield from run_anthropic_loop(
            session, task, model=model, max_iterations=max_iterations, system=system
        )
    else:
        yield from run_openai_loop(
            session, task, model=model, max_iterations=max_iterations, system=system
        )
