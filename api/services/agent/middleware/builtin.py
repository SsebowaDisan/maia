"""Built-in middleware stages for common orchestration concerns."""
from __future__ import annotations
import logging
import time
from typing import Any

from .base import StepContext, StepMiddleware

logger = logging.getLogger(__name__)


class CostEstimationMiddleware(StepMiddleware):
    """Pre-flight cost estimation and budget enforcement."""

    def __init__(self, max_cost_usd: float = 0.0) -> None:
        self._max_cost_usd = max_cost_usd
        self._accumulated_usd = 0.0

    def before_step(self, ctx: StepContext) -> StepContext:
        if self._max_cost_usd > 0 and self._accumulated_usd >= self._max_cost_usd:
            raise RuntimeError(
                f"Cost budget exhausted: ${self._accumulated_usd:.4f} >= ${self._max_cost_usd:.4f}"
            )
        return ctx

    def after_step(self, ctx: StepContext) -> StepContext:
        step_cost = ctx.metadata.get("cost_usd", 0.0)
        self._accumulated_usd += step_cost
        ctx.metadata["accumulated_cost_usd"] = self._accumulated_usd
        return ctx


class AuditLoggingMiddleware(StepMiddleware):
    """Structured audit log for every step execution."""

    def before_step(self, ctx: StepContext) -> StepContext:
        logger.info(
            "STEP_START run=%s step=%d tool=%s",
            ctx.run_id,
            ctx.step_index,
            ctx.tool_id or "none",
        )
        ctx.metadata["_step_start_time"] = time.time()
        return ctx

    def after_step(self, ctx: StepContext) -> StepContext:
        logger.info(
            "STEP_END run=%s step=%d tool=%s duration=%.1fms tokens_in=%d tokens_out=%d",
            ctx.run_id,
            ctx.step_index,
            ctx.tool_id or "none",
            ctx.duration_ms,
            ctx.tokens_in,
            ctx.tokens_out,
        )
        return ctx

    def on_error(self, ctx: StepContext, error: Exception) -> StepContext:
        logger.error(
            "STEP_ERROR run=%s step=%d tool=%s error=%s",
            ctx.run_id,
            ctx.step_index,
            ctx.tool_id or "none",
            str(error),
        )
        ctx.error = error
        return ctx


class CheckpointMiddleware(StepMiddleware):
    """Automatic fine-grained checkpoints per step."""

    def __init__(self, checkpoint_fn: Any = None) -> None:
        self._checkpoint_fn = checkpoint_fn

    def after_step(self, ctx: StepContext) -> StepContext:
        if self._checkpoint_fn is None:
            return ctx
        try:
            self._checkpoint_fn(
                name=f"step_{ctx.step_index}_{ctx.step_name}",
                status="completed" if ctx.error is None else "failed",
                metadata={
                    "run_id": ctx.run_id,
                    "tool_id": ctx.tool_id,
                    "duration_ms": ctx.duration_ms,
                    "tokens_in": ctx.tokens_in,
                    "tokens_out": ctx.tokens_out,
                },
            )
        except Exception as exc:
            logger.debug("Checkpoint write failed: %s", exc)
        return ctx


class MemoryInjectionMiddleware(StepMiddleware):
    """Recall relevant memories before execution and store new facts after."""

    def __init__(self, recall_fn: Any = None, store_fn: Any = None) -> None:
        self._recall_fn = recall_fn
        self._store_fn = store_fn

    def before_step(self, ctx: StepContext) -> StepContext:
        if self._recall_fn is None:
            return ctx
        try:
            query = ctx.step_name or ctx.tool_id or ""
            memories = self._recall_fn(ctx.agent_id, query, top_k=3)
            if memories:
                ctx.metadata["recalled_memories"] = memories
        except Exception as exc:
            logger.debug("Memory recall failed: %s", exc)
        return ctx

    def after_step(self, ctx: StepContext) -> StepContext:
        if self._store_fn is None:
            return ctx
        facts = ctx.metadata.get("learned_facts")
        if facts and isinstance(facts, list):
            for fact in facts:
                try:
                    self._store_fn(ctx.agent_id, str(fact))
                except Exception:
                    pass
        return ctx


class RateLimitMiddleware(StepMiddleware):
    """Simple token-bucket rate limiter per run."""

    def __init__(self, max_steps_per_minute: int = 60) -> None:
        self._max_rpm = max_steps_per_minute
        self._timestamps: list[float] = []

    def before_step(self, ctx: StepContext) -> StepContext:
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self._max_rpm:
            raise RuntimeError(
                f"Rate limit exceeded: {self._max_rpm} steps/minute"
            )
        self._timestamps.append(now)
        return ctx


class DepthGuardMiddleware(StepMiddleware):
    """Prevent runaway sub-agent delegation chains."""

    def __init__(self, max_depth: int = 5) -> None:
        self._max_depth = max_depth

    def before_step(self, ctx: StepContext) -> StepContext:
        if ctx.depth > self._max_depth:
            raise RuntimeError(
                f"Agent delegation depth {ctx.depth} exceeds max {self._max_depth}"
            )
        return ctx
