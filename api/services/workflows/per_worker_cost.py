"""Per-worker cost tracking for multi-agent workflows.

Inspired by ClawTeam's CostTracker with per-agent budget limits.
Tracks token usage and estimated cost per workflow step/agent,
enabling per-worker cost breakdown and budget enforcement.

Usage:
    tracker = WorkflowCostTracker(run_id="run_abc", budget_usd=5.0)
    tracker.record(step_id="step_research", agent_id="researcher", tokens_in=1200, tokens_out=800)
    tracker.record(step_id="step_analyse", agent_id="analyst", tokens_in=2000, tokens_out=1500)
    print(tracker.summary())
    # {"total_cost_usd": 0.042, "steps": {"step_research": {...}, "step_analyse": {...}}}
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Approximate pricing per 1K tokens (input/output) — conservative estimates
_MODEL_PRICING: dict[str, dict[str, float]] = {
    "default": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "gpt-4o": {"input_per_1k": 0.0025, "output_per_1k": 0.01},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "claude-3-5-sonnet": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-3-haiku": {"input_per_1k": 0.00025, "output_per_1k": 0.00125},
}


def _estimate_cost(tokens_in: int, tokens_out: int, model: str = "default") -> float:
    pricing = _MODEL_PRICING.get(model, _MODEL_PRICING["default"])
    cost = (tokens_in / 1000) * pricing["input_per_1k"] + (tokens_out / 1000) * pricing["output_per_1k"]
    return round(cost, 6)


class StepCostRecord:
    """Cost record for a single workflow step."""

    __slots__ = ("step_id", "agent_id", "tokens_in", "tokens_out", "cost_usd",
                 "tool_calls", "started_at", "ended_at", "model")

    def __init__(self, step_id: str, agent_id: str):
        self.step_id = step_id
        self.agent_id = agent_id
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.tool_calls = 0
        self.started_at: float = 0
        self.ended_at: float = 0
        self.model = "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "agent_id": self.agent_id,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "tool_calls": self.tool_calls,
            "duration_ms": round((self.ended_at - self.started_at) * 1000) if self.ended_at and self.started_at else 0,
            "model": self.model,
        }


class WorkflowCostTracker:
    """Tracks per-step token usage and cost for a workflow run."""

    def __init__(self, run_id: str, budget_usd: float = 0.0):
        self.run_id = run_id
        self.budget_usd = budget_usd
        self._lock = threading.Lock()
        self._steps: dict[str, StepCostRecord] = {}
        self._started_at = time.time()

    def start_step(self, step_id: str, agent_id: str = "") -> None:
        """Mark a step as started for duration tracking."""
        with self._lock:
            if step_id not in self._steps:
                self._steps[step_id] = StepCostRecord(step_id, agent_id)
            self._steps[step_id].started_at = time.time()

    def record(
        self,
        *,
        step_id: str,
        agent_id: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        tool_calls: int = 0,
        model: str = "default",
    ) -> dict[str, Any]:
        """Record token usage for a step. Accumulates across multiple calls."""
        with self._lock:
            if step_id not in self._steps:
                self._steps[step_id] = StepCostRecord(step_id, agent_id)
            rec = self._steps[step_id]
            rec.tokens_in += tokens_in
            rec.tokens_out += tokens_out
            rec.tool_calls += tool_calls
            rec.model = model or rec.model
            rec.cost_usd = _estimate_cost(rec.tokens_in, rec.tokens_out, rec.model)
            if not rec.agent_id and agent_id:
                rec.agent_id = agent_id
            return rec.to_dict()

    def end_step(self, step_id: str) -> None:
        """Mark a step as ended for duration tracking."""
        with self._lock:
            rec = self._steps.get(step_id)
            if rec:
                rec.ended_at = time.time()

    def total_cost_usd(self) -> float:
        """Return total cost across all steps."""
        with self._lock:
            return round(sum(r.cost_usd for r in self._steps.values()), 6)

    def is_over_budget(self) -> bool:
        """Check if total cost exceeds budget. Returns False if no budget set."""
        if self.budget_usd <= 0:
            return False
        return self.total_cost_usd() > self.budget_usd

    def budget_remaining_usd(self) -> float:
        """Return remaining budget in USD. Returns -1 if no budget set."""
        if self.budget_usd <= 0:
            return -1
        return round(max(0, self.budget_usd - self.total_cost_usd()), 6)

    def summary(self) -> dict[str, Any]:
        """Return full cost breakdown."""
        with self._lock:
            steps = {sid: rec.to_dict() for sid, rec in self._steps.items()}
            total_in = sum(r.tokens_in for r in self._steps.values())
            total_out = sum(r.tokens_out for r in self._steps.values())
            total_cost = sum(r.cost_usd for r in self._steps.values())
            return {
                "run_id": self.run_id,
                "total_tokens_in": total_in,
                "total_tokens_out": total_out,
                "total_cost_usd": round(total_cost, 6),
                "budget_usd": self.budget_usd,
                "over_budget": self.is_over_budget(),
                "step_count": len(self._steps),
                "duration_ms": round((time.time() - self._started_at) * 1000),
                "steps": steps,
                "top_cost_steps": sorted(
                    steps.values(),
                    key=lambda s: s["cost_usd"],
                    reverse=True,
                )[:5],
            }

    def agent_breakdown(self) -> dict[str, dict[str, Any]]:
        """Return cost breakdown grouped by agent_id."""
        with self._lock:
            agents: dict[str, dict[str, Any]] = {}
            for rec in self._steps.values():
                aid = rec.agent_id or "unknown"
                if aid not in agents:
                    agents[aid] = {"agent_id": aid, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "step_count": 0}
                agents[aid]["tokens_in"] += rec.tokens_in
                agents[aid]["tokens_out"] += rec.tokens_out
                agents[aid]["cost_usd"] = round(agents[aid]["cost_usd"] + rec.cost_usd, 6)
                agents[aid]["step_count"] += 1
            return agents
