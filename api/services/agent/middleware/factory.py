"""Factory to build the default middleware pipeline for a run."""
from __future__ import annotations
import logging
from typing import Any

from .base import StepMiddleware
from .builtin import (
    AuditLoggingMiddleware,
    CheckpointMiddleware,
    CostEstimationMiddleware,
    DepthGuardMiddleware,
    MemoryInjectionMiddleware,
    RateLimitMiddleware,
)
from .pipeline import MiddlewarePipeline

logger = logging.getLogger(__name__)


def build_default_pipeline(
    *,
    max_cost_usd: float = 0.0,
    max_depth: int = 5,
    max_steps_per_minute: int = 60,
    checkpoint_fn: Any = None,
    recall_fn: Any = None,
    store_fn: Any = None,
    extra: list[StepMiddleware] | None = None,
) -> MiddlewarePipeline:
    """Assemble the standard middleware chain for an agent run.

    Order:
      1. DepthGuard -- block runaway delegation
      2. RateLimit -- throttle step execution
      3. CostEstimation -- enforce budget
      4. MemoryInjection -- recall/store facts
      5. AuditLogging -- structured logs
      6. Checkpoint -- fine-grained persistence
      + any extras appended at the end
    """
    pipeline = MiddlewarePipeline()
    pipeline.add(DepthGuardMiddleware(max_depth=max_depth))
    pipeline.add(RateLimitMiddleware(max_steps_per_minute=max_steps_per_minute))
    if max_cost_usd > 0:
        pipeline.add(CostEstimationMiddleware(max_cost_usd=max_cost_usd))
    pipeline.add(MemoryInjectionMiddleware(recall_fn=recall_fn, store_fn=store_fn))
    pipeline.add(AuditLoggingMiddleware())
    if checkpoint_fn is not None:
        pipeline.add(CheckpointMiddleware(checkpoint_fn=checkpoint_fn))
    for mw in extra or []:
        pipeline.add(mw)
    logger.debug("Built middleware pipeline: %s", pipeline.stage_names)
    return pipeline
