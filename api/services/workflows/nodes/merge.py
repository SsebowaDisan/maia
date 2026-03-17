"""Merge node — combines outputs from multiple upstream steps.

step_config:
    keys: list[str]         — input keys to merge (from input_mapping)
    strategy: str           — "dict" (default), "list", "concat"

Returns the merged result based on strategy:
  - dict:   shallow-merge all dict inputs into one
  - list:   collect all values into a list
  - concat: join all string values with separator
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)


@register("merge")
def handle_merge(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> Any:
    cfg = step.step_config
    keys = cfg.get("keys", list(inputs.keys()))
    strategy = cfg.get("strategy", "dict")
    separator = cfg.get("separator", "\n")

    values = [inputs[k] for k in keys if k in inputs]

    if strategy == "list":
        return {"merged": values}

    if strategy == "concat":
        return {"merged": separator.join(str(v) for v in values)}

    # Default: dict merge
    merged: dict[str, Any] = {}
    for v in values:
        if isinstance(v, dict):
            merged.update(v)
        else:
            merged[f"value_{len(merged)}"] = v
    return {"merged": merged}
