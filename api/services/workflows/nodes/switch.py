"""Switch node — routes execution based on a value matching cases.

step_config:
    value_key: str          — input key to switch on
    cases: dict[str, str]   — mapping of value → label (for downstream edge matching)
    default: str            — fallback label if no case matches

Returns {"matched_case": <label>} so edges can use condition "output.matched_case == 'label'".
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)


@register("switch")
def handle_switch(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    cfg = step.step_config
    value_key = cfg.get("value_key", "")
    cases = cfg.get("cases", {})
    default = cfg.get("default", "none")

    if not value_key:
        raise ValueError(f"Step {step.step_id}: switch requires 'value_key' in step_config")

    actual_value = str(inputs.get(value_key, ""))
    matched = cases.get(actual_value, default)

    return {"matched_case": matched, "input_value": actual_value}
