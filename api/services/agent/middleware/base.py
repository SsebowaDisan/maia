"""Base middleware contract for the agent orchestration pipeline."""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)

@dataclass
class StepContext:
    """Immutable-ish context bag flowing through the middleware chain."""
    run_id: str
    tenant_id: str
    user_id: str
    step_index: int
    step_name: str
    tool_id: str | None = None
    tool_params: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    parent_run_id: str | None = None
    depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    # Populated after execution
    result: Any = None
    error: Exception | None = None
    duration_ms: float = 0
    tokens_in: int = 0
    tokens_out: int = 0

class StepMiddleware(ABC):
    """Single middleware stage in the orchestration pipeline."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def enabled(self) -> bool:
        return True

    def before_step(self, ctx: StepContext) -> StepContext:
        """Called before step execution. Can modify context or raise to abort."""
        return ctx

    def after_step(self, ctx: StepContext) -> StepContext:
        """Called after step execution (success or failure). Can modify context."""
        return ctx

    def on_error(self, ctx: StepContext, error: Exception) -> StepContext:
        """Called when step execution raises. Default: propagate."""
        ctx.error = error
        return ctx
