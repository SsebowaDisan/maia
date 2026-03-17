"""Delay node — pauses execution for a configured duration.

step_config:
    seconds: int | float — time to wait (default 1, max 300)

Returns {"waited_s": <actual_seconds>}.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)

_MAX_DELAY = 300  # 5 minutes cap


@register("delay")
def handle_delay(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    seconds = min(float(step.step_config.get("seconds", 1)), _MAX_DELAY)
    if seconds > 0:
        time.sleep(seconds)
    return {"waited_s": seconds}
