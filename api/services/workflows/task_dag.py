"""Task DAG with dynamic dependency resolution and auto-unblocking.

Inspired by ClawTeam's TaskStore with blocked_by and _resolve_dependents.
Instead of pre-computing all batches upfront, this tracks step dependencies
at runtime and dynamically unblocks steps as their predecessors complete.

This handles cases the static batch model misses:
- Step C depends on A and B. A completes, B fails. C should NOT run.
- Step D depends only on A. A completes, D should run immediately
  (not wait for B to finish in the same batch).
- Step E has no dependencies. It should start immediately.

Usage:
    dag = TaskDAG(workflow)
    dag.mark_completed("step_research")
    ready = dag.get_ready_steps()  # returns steps whose deps are all done
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Literal

logger = logging.getLogger(__name__)

StepStatus = Literal["pending", "running", "completed", "failed", "skipped", "blocked"]


class TaskNode:
    """A single step in the DAG with runtime status tracking."""

    __slots__ = ("step_id", "status", "blocked_by", "dependents", "result")

    def __init__(self, step_id: str, blocked_by: set[str]):
        self.step_id = step_id
        self.status: StepStatus = "blocked" if blocked_by else "pending"
        self.blocked_by: set[str] = set(blocked_by)
        self.dependents: list[str] = []
        self.result: Any = None


class TaskDAG:
    """Runtime DAG that tracks step status and auto-unblocks dependents."""

    def __init__(self, steps: list[dict[str, Any]], edges: list[dict[str, Any]]):
        self._lock = threading.Lock()
        self._nodes: dict[str, TaskNode] = {}
        self._completed_order: list[str] = []

        # Build dependency graph
        deps: dict[str, set[str]] = {}
        for step in steps:
            sid = str(step.get("step_id", ""))
            deps[sid] = set()
        for edge in edges:
            from_step = str(edge.get("from_step", ""))
            to_step = str(edge.get("to_step", ""))
            if to_step in deps:
                deps[to_step].add(from_step)

        # Create nodes
        for step in steps:
            sid = str(step.get("step_id", ""))
            node = TaskNode(sid, deps.get(sid, set()))
            self._nodes[sid] = node

        # Wire dependents (reverse edges)
        for sid, dep_set in deps.items():
            for dep in dep_set:
                if dep in self._nodes:
                    self._nodes[dep].dependents.append(sid)

    def get_ready_steps(self) -> list[str]:
        """Return step IDs that are pending (all dependencies met)."""
        with self._lock:
            return [
                sid for sid, node in self._nodes.items()
                if node.status == "pending"
            ]

    def get_status(self, step_id: str) -> StepStatus | None:
        """Return the current status of a step."""
        node = self._nodes.get(step_id)
        return node.status if node else None

    def mark_running(self, step_id: str) -> None:
        """Mark a step as currently executing."""
        with self._lock:
            node = self._nodes.get(step_id)
            if node and node.status == "pending":
                node.status = "running"

    def mark_completed(self, step_id: str, result: Any = None) -> list[str]:
        """Mark a step as completed and return newly unblocked step IDs."""
        with self._lock:
            node = self._nodes.get(step_id)
            if not node:
                return []
            node.status = "completed"
            node.result = result
            self._completed_order.append(step_id)
            return self._resolve_dependents(step_id)

    def mark_failed(self, step_id: str, error: str = "") -> list[str]:
        """Mark a step as failed. Dependents stay blocked (won't auto-unblock)."""
        with self._lock:
            node = self._nodes.get(step_id)
            if not node:
                return []
            node.status = "failed"
            # Cascade: mark all transitive dependents as blocked
            return self._cascade_block(step_id)

    def mark_skipped(self, step_id: str) -> list[str]:
        """Mark a step as skipped. Dependents that have other paths may still run."""
        with self._lock:
            node = self._nodes.get(step_id)
            if not node:
                return []
            node.status = "skipped"
            # Try to unblock dependents — skipped counts as "done" for dep resolution
            return self._resolve_dependents(step_id)

    def is_all_done(self) -> bool:
        """Check if all steps are in a terminal state."""
        with self._lock:
            return all(
                n.status in ("completed", "failed", "skipped")
                for n in self._nodes.values()
            )

    def summary(self) -> dict[str, int]:
        """Return count of steps in each status."""
        with self._lock:
            counts: dict[str, int] = {}
            for node in self._nodes.values():
                counts[node.status] = counts.get(node.status, 0) + 1
            return counts

    def _resolve_dependents(self, completed_step_id: str) -> list[str]:
        """Check dependents of a completed step and unblock any that are ready.

        Must be called while holding self._lock.
        """
        node = self._nodes.get(completed_step_id)
        if not node:
            return []
        newly_ready: list[str] = []
        for dep_id in node.dependents:
            dep_node = self._nodes.get(dep_id)
            if not dep_node or dep_node.status != "blocked":
                continue
            dep_node.blocked_by.discard(completed_step_id)
            if not dep_node.blocked_by:
                dep_node.status = "pending"
                newly_ready.append(dep_id)
                logger.debug("Step '%s' unblocked (all deps met)", dep_id)
        return newly_ready

    def _cascade_block(self, failed_step_id: str) -> list[str]:
        """Mark all transitive dependents as blocked when a step fails.

        Must be called while holding self._lock.
        """
        blocked: list[str] = []
        queue = list(self._nodes[failed_step_id].dependents) if failed_step_id in self._nodes else []
        visited: set[str] = set()
        while queue:
            sid = queue.pop(0)
            if sid in visited:
                continue
            visited.add(sid)
            node = self._nodes.get(sid)
            if node and node.status in ("pending", "blocked"):
                node.status = "blocked"
                blocked.append(sid)
                queue.extend(node.dependents)
        return blocked

    @classmethod
    def from_workflow(cls, workflow: Any) -> "TaskDAG":
        """Build from a WorkflowDefinitionSchema."""
        steps = [{"step_id": s.step_id} for s in workflow.steps]
        edges = [{"from_step": e.from_step, "to_step": e.to_step} for e in workflow.edges]
        return cls(steps, edges)
