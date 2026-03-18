"""Middleware pipeline -- composes and executes middleware stages in order."""
from __future__ import annotations
import logging
import time
from typing import Any, Callable

from .base import StepContext, StepMiddleware

logger = logging.getLogger(__name__)

class MiddlewarePipeline:
    """Ordered chain of StepMiddleware stages wrapping step execution."""

    def __init__(self) -> None:
        self._stages: list[StepMiddleware] = []

    # -- builder -----------------------------------------------------------
    def add(self, middleware: StepMiddleware) -> "MiddlewarePipeline":
        self._stages.append(middleware)
        return self

    def add_before(self, name: str, middleware: StepMiddleware) -> "MiddlewarePipeline":
        """Insert middleware before the stage with the given name."""
        for i, stage in enumerate(self._stages):
            if stage.name == name:
                self._stages.insert(i, middleware)
                return self
        self._stages.append(middleware)
        return self

    def add_after(self, name: str, middleware: StepMiddleware) -> "MiddlewarePipeline":
        """Insert middleware after the stage with the given name."""
        for i, stage in enumerate(self._stages):
            if stage.name == name:
                self._stages.insert(i + 1, middleware)
                return self
        self._stages.append(middleware)
        return self

    def remove(self, name: str) -> "MiddlewarePipeline":
        self._stages = [s for s in self._stages if s.name != name]
        return self

    @property
    def stage_names(self) -> list[str]:
        return [s.name for s in self._stages]

    # -- execution ---------------------------------------------------------
    def execute(
        self,
        ctx: StepContext,
        step_fn: Callable[[StepContext], Any],
    ) -> StepContext:
        """Run the full pipeline: before -> step_fn -> after, with error handling."""
        active = [s for s in self._stages if s.enabled]

        # -- before phase --------------------------------------------------
        for stage in active:
            try:
                ctx = stage.before_step(ctx)
            except Exception as exc:
                logger.warning("Middleware %s.before_step aborted: %s", stage.name, exc)
                ctx.error = exc
                # Run on_error for stages that already ran before_step
                idx = active.index(stage)
                for prev in reversed(active[: idx + 1]):
                    try:
                        ctx = prev.on_error(ctx, exc)
                    except Exception:
                        pass
                return ctx

        # -- step execution ------------------------------------------------
        t0 = time.perf_counter()
        try:
            ctx.result = step_fn(ctx)
        except Exception as exc:
            ctx.error = exc
            ctx.duration_ms = (time.perf_counter() - t0) * 1000
            for stage in reversed(active):
                try:
                    ctx = stage.on_error(ctx, exc)
                except Exception:
                    pass
            return ctx
        ctx.duration_ms = (time.perf_counter() - t0) * 1000

        # -- after phase ---------------------------------------------------
        for stage in reversed(active):
            try:
                ctx = stage.after_step(ctx)
            except Exception as exc:
                logger.warning("Middleware %s.after_step failed: %s", stage.name, exc)

        return ctx
