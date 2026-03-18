"""Deterministic node handler registry for workflow step types."""
from __future__ import annotations

from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep

# Handler signature: (step, inputs, on_event) -> result
StepHandler = Callable[[WorkflowStep, dict[str, Any], Optional[Callable]], Any]

_HANDLERS: dict[str, StepHandler] = {}


def register(step_type: str) -> Callable[[StepHandler], StepHandler]:
    """Decorator to register a node handler for a step_type."""
    def decorator(fn: StepHandler) -> StepHandler:
        _HANDLERS[step_type] = fn
        return fn
    return decorator


def get_handler(step_type: str) -> StepHandler | None:
    """Look up the handler for a step_type, lazy-importing on first call."""
    if not _HANDLERS:
        _load_all()
    return _HANDLERS.get(step_type)


def _load_all() -> None:
    """Import all node modules so their @register decorators run."""
    from api.services.workflows.nodes import (  # noqa: F401
        http_request,
        condition,
        switch,
        foreach,
        delay,
        transform,
        code_sandbox,
        merge,
        knowledge_search,
        multi_perspective,
    )
