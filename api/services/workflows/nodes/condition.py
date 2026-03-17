"""Condition node — evaluates a boolean expression and returns true/false.

step_config:
    expression: str — condition expression (same syntax as edge conditions)
                      e.g. "output.score > 0.8 AND output.status == 'ready'"

Returns {"result": True/False} so downstream edges can branch on it.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)


@register("condition")
def handle_condition(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    from api.services.agents.workflow_executor import _eval_condition

    expression = step.step_config.get("expression", "")
    if not expression:
        raise ValueError(f"Step {step.step_id}: condition requires 'expression' in step_config")

    result = _eval_condition(expression, inputs)
    return {"result": result, "expression": expression}
