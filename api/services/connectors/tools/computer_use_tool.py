"""B1-CU-06 — Computer Use as a connector tool.

Responsibility: wrap the Computer Use agent loop as a connector tool handler
so agents can invoke browser automation via the standard tool execution bus.

Tool ID: computer_use.run_task
Params:
  - url (str, required): starting URL for the task
  - task (str, required): natural-language instruction for Claude
  - max_iterations (int, default 15): loop limit
  - model (str, default 'claude-opus-4-6'): Claude model
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

TOOL_ID = "computer_use.run_task"


def _run_task(params: dict[str, Any], *, tenant_id: str, agent_id: str) -> dict[str, Any]:
    """Execute a Computer Use task and return a summary of what happened."""
    url: str = str(params.get("url") or "about:blank")
    task: str = str(params.get("task") or "")
    max_iterations: int = int(params.get("max_iterations") or 15)
    model: str = str(params.get("model") or "claude-opus-4-6")

    if not task:
        return {"status": "error", "detail": "Parameter 'task' is required."}

    from api.services.computer_use.session_registry import get_session_registry
    from api.services.computer_use.agent_loop import run_agent_loop

    registry = get_session_registry()
    try:
        session = registry.create()
    except Exception as exc:
        return {"status": "error", "detail": f"Could not start browser session: {exc}"}

    events: list[dict[str, Any]] = []
    final_url = url

    try:
        if url and url != "about:blank":
            session.navigate(url)

        for event in run_agent_loop(session, task, model=model, max_iterations=max_iterations):
            event_type = event.get("event_type")
            # Collect lightweight events (skip raw screenshots to keep payload small)
            if event_type != "screenshot":
                events.append(event)
            if event_type in ("done", "max_iterations", "error"):
                final_url = str(event.get("url") or final_url)
    except Exception as exc:
        logger.error("Computer Use task failed: %s", exc, exc_info=True)
        return {"status": "error", "detail": str(exc)[:400], "events": events}
    finally:
        registry.close(session.session_id)

    last = events[-1] if events else {}
    return {
        "status": "ok" if last.get("event_type") == "done" else "max_iterations",
        "final_url": final_url,
        "iterations": last.get("iteration", 0),
        "events": events,
    }


def register(registry: Any) -> None:
    """Register the computer_use.run_task handler in the given tool registry."""
    registry.register_handler(TOOL_ID, _run_task)
    logger.debug("Registered tool handler: %s", TOOL_ID)
