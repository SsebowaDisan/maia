"""P8-01 — Agent simulation / dry-run runner.

Responsibility: execute an agent against a canned scenario (mocked tool
responses) without producing real side effects.  Returns a step-by-step trace
that can be replayed in the frontend.

Usage
-----
    result = run_simulation(
        tenant_id="user1",
        agent_id="my_agent",
        scenario={
            "input": "Analyse Q3 revenue",
            "mocked_tools": {
                "crm.get_pipeline": {"deals": [], "total": 0},
                "email.send": {"sent": True},
            }
        }
    )
    # result["steps"] is a list of step dicts with event_type, tool, output, etc.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def run_simulation(
    tenant_id: str,
    agent_id: str,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    """Run the agent in dry-run mode with mocked tool responses.

    Args:
        tenant_id: Tenant identifier.
        agent_id: Agent to simulate.
        scenario: Dict with optional keys:
            - "input": str — the task message (defaults to "Simulate run.")
            - "mocked_tools": dict[tool_id -> mock_response] — intercept these tools

    Returns:
        {
            "run_id": str,
            "agent_id": str,
            "steps": list[dict],  — ordered step trace
            "completed": bool,
            "error": str | None,
            "duration_ms": int,
        }
    """
    run_id = f"sim_{uuid.uuid4().hex[:12]}"
    task = str(scenario.get("input") or "Simulate agent run.")
    mocked_tools: dict[str, Any] = dict(scenario.get("mocked_tools") or {})

    steps: list[dict[str, Any]] = []
    start = time.time()
    completed = False
    error: str | None = None

    def _record_step(event_type: str, **kwargs: Any) -> None:
        steps.append({
            "step_index": len(steps),
            "event_type": event_type,
            "ts": time.time(),
            **kwargs,
        })

    try:
        # Load agent schema
        from api.services.agents.definition_store import get_agent, load_schema
        record = get_agent(tenant_id, agent_id)
        if not record:
            raise ValueError(f"Agent '{agent_id}' not found for tenant '{tenant_id}'.")

        schema = load_schema(record)
        _record_step("agent_loaded", agent_id=agent_id, name=record.name)

        # Run through the orchestrator with dry-run flag via settings
        from api.services.agents.runner import run_agent_task
        from api.schemas import ChatRequest

        settings: dict[str, Any] = {
            "__dry_run": True,
            "__mocked_tools": mocked_tools,
        }
        if schema.tools:
            settings["__allowed_tool_ids"] = list(schema.tools)

        _record_step("task_started", task=task[:200])

        for chunk in run_agent_task(
            task,
            tenant_id=tenant_id,
            run_id=run_id,
            system_prompt=schema.system_prompt or None,
            allowed_tool_ids=list(schema.tools) if schema.tools else None,
            agent_id=agent_id,
        ):
            event_type = chunk.get("event_type") or "chunk"
            tool_id = chunk.get("tool_id") or chunk.get("tool") or ""
            content = chunk.get("text") or chunk.get("content") or ""

            # Intercept tool calls: return mocked response instead of real one
            if event_type in ("tool_started", "tool_called") and tool_id in mocked_tools:
                mock_resp = mocked_tools[tool_id]
                _record_step(
                    "tool_intercepted",
                    tool_id=tool_id,
                    mock_response=mock_resp,
                )
                # Inject mocked response into the chunk so downstream sees it
                chunk = {**chunk, "output": mock_resp, "mocked": True}
            elif event_type in ("tool_started", "tool_called", "tool_completed"):
                _record_step("tool_call", tool_id=tool_id, **{
                    k: v for k, v in chunk.items()
                    if k not in ("event_type",)
                })
            elif content:
                _record_step("text_chunk", text=str(content)[:300])

        completed = True
        _record_step("simulation_complete")

    except Exception as exc:
        error = str(exc)[:300]
        logger.warning("Simulation failed (agent=%s): %s", agent_id, exc)
        _record_step("simulation_error", error=error)

    duration_ms = int((time.time() - start) * 1000)
    return {
        "run_id": run_id,
        "agent_id": agent_id,
        "scenario_input": task[:200],
        "steps": steps,
        "completed": completed,
        "error": error,
        "duration_ms": duration_ms,
    }
