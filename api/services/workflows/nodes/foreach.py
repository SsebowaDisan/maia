"""ForEach node — iterates over a list and collects results.

step_config:
    items_key: str      — input key containing the list to iterate
    body_step_type: str — step_type to run for each item (default "transform")
    body_config: dict   — step_config passed to the body handler per item
    max_items: int      — safety cap (default 100)

Each iteration receives the item as "item" and index as "index" in inputs.
Returns {"results": [...], "count": N, "errors": [...]}.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register, get_handler

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITEMS = 100


@register("foreach")
def handle_foreach(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    cfg = step.step_config
    items_key = cfg.get("items_key", "items")
    body_type = cfg.get("body_step_type", "transform")
    body_config = cfg.get("body_config", {})
    max_items = cfg.get("max_items", _DEFAULT_MAX_ITEMS)

    raw_items = inputs.get(items_key, [])
    if isinstance(raw_items, str):
        import json
        try:
            raw_items = json.loads(raw_items)
        except (json.JSONDecodeError, ValueError):
            raw_items = [raw_items]

    if not isinstance(raw_items, list):
        raw_items = [raw_items]

    items = raw_items[:max_items]
    handler = get_handler(body_type)
    if handler is None:
        logger.warning("ForEach body_step_type '%s' has no handler — using passthrough", body_type)

    results: list[Any] = []
    errors: list[dict[str, Any]] = []

    for idx, item in enumerate(items):
        iter_inputs = {**inputs, "item": item, "index": idx}
        try:
            if handler is not None:
                body_step = WorkflowStep(
                    step_id=f"{step.step_id}__iter_{idx}",
                    step_type=body_type,
                    step_config=body_config,
                    output_key=f"{step.output_key}__iter_{idx}",
                )
                result = handler(body_step, iter_inputs, on_event)
            else:
                result = item  # passthrough if no body handler
            results.append(result)
        except Exception as exc:
            logger.warning("ForEach iteration %d failed: %s", idx, exc)
            errors.append({"index": idx, "error": str(exc)[:500]})
            results.append(None)

    if len(items) < len(raw_items):
        logger.info(
            "ForEach truncated %d items to max_items=%d",
            len(raw_items), max_items,
        )

    return {"results": results, "count": len(results), "errors": errors}
