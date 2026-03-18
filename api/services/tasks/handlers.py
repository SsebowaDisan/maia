"""Task handler registry — maps task_type strings to handler functions.

Each handler receives a payload dict and returns a result dict.
Handlers are imported lazily to avoid circular imports.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

TaskHandler = Callable[[dict[str, Any]], Any]
_HANDLERS: dict[str, TaskHandler] = {}


def register(task_type: str, handler: TaskHandler) -> None:
    _HANDLERS[task_type] = handler
    logger.debug("Registered task handler: %s", task_type)


def get_handler(task_type: str) -> TaskHandler | None:
    _load_defaults()
    return _HANDLERS.get(task_type)


_loaded = False


def _load_defaults() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True

    # ── agent.scheduled_run ────────────────────────────────────────────────
    def _handle_scheduled_run(payload: dict[str, Any]) -> Any:
        from api.services.agents.scheduler import _fire_agent
        _fire_agent(payload["tenant_id"], payload["agent_id"])
        return {"status": "completed"}

    register("agent.scheduled_run", _handle_scheduled_run)

    # ── agent.event_run ────────────────────────────────────────────────────
    def _handle_event_run(payload: dict[str, Any]) -> Any:
        from api.services.agents.event_triggers import _run_agent_for_event
        from api.services.agents.run_store import create_run
        run = create_run(payload["tenant_id"], payload["agent_id"], trigger_type="event")
        _run_agent_for_event(
            payload["tenant_id"],
            payload["agent_id"],
            run.id,
            payload.get("event_type", "unknown"),
            payload.get("event_payload", {}),
        )
        return {"status": "completed"}

    register("agent.event_run", _handle_event_run)

    # ── workflow.run_step ──────────────────────────────────────────────────
    def _handle_workflow_step(payload: dict[str, Any]) -> Any:
        from api.services.agents.workflow_executor import WorkflowExecutor
        # This is a simplified handler — full workflow execution still uses
        # the executor directly. This handler is for individual step dispatch
        # in future distributed mode.
        return {"status": "delegated", "step_id": payload.get("step_id")}

    register("workflow.run_step", _handle_workflow_step)
