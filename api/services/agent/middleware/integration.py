"""Integration bridge — connects the middleware pipeline to the orchestration loop."""
from __future__ import annotations
import logging
from typing import Any, Callable

from .base import StepContext
from .factory import build_default_pipeline
from .pipeline import MiddlewarePipeline

logger = logging.getLogger(__name__)


def create_pipeline_for_run(
    settings: dict[str, Any],
    *,
    checkpoint_fn: Any = None,
    recall_fn: Any = None,
    store_fn: Any = None,
) -> MiddlewarePipeline:
    """Build a middleware pipeline from agent run settings.

    Reads configuration from the settings dict:
      - middleware.max_cost_usd (float, default 0 = unlimited)
      - middleware.max_depth (int, default 5)
      - middleware.max_steps_per_minute (int, default 60)
      - middleware.disabled_stages (list[str], stages to skip)
      - middleware.extra (list of custom middleware instances)
    """
    mw_config = settings.get("middleware", {})
    if not isinstance(mw_config, dict):
        mw_config = {}

    pipeline = build_default_pipeline(
        max_cost_usd=float(mw_config.get("max_cost_usd", 0)),
        max_depth=int(mw_config.get("max_depth", 5)),
        max_steps_per_minute=int(mw_config.get("max_steps_per_minute", 60)),
        checkpoint_fn=checkpoint_fn,
        recall_fn=recall_fn,
        store_fn=store_fn,
    )

    # Remove disabled stages
    for stage_name in mw_config.get("disabled_stages", []):
        pipeline.remove(stage_name)

    return pipeline


def build_step_context(
    *,
    run_id: str,
    tenant_id: str,
    user_id: str,
    step_index: int,
    step_name: str,
    tool_id: str | None = None,
    tool_params: dict[str, Any] | None = None,
    agent_id: str | None = None,
    parent_run_id: str | None = None,
    depth: int = 0,
    extra_metadata: dict[str, Any] | None = None,
) -> StepContext:
    """Convenience builder for StepContext from orchestration state."""
    return StepContext(
        run_id=run_id,
        tenant_id=tenant_id,
        user_id=user_id,
        step_index=step_index,
        step_name=step_name,
        tool_id=tool_id,
        tool_params=tool_params or {},
        agent_id=agent_id,
        parent_run_id=parent_run_id,
        depth=depth,
        metadata=extra_metadata or {},
    )


def wrap_step_execution(
    pipeline: MiddlewarePipeline,
    ctx: StepContext,
    step_fn: Callable[[StepContext], Any],
) -> tuple[Any, Exception | None]:
    """Execute a step through the middleware pipeline.

    Returns (result, error). If error is None, the step succeeded.
    """
    result_ctx = pipeline.execute(ctx, step_fn)
    return result_ctx.result, result_ctx.error
