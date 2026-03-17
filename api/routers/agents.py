"""B2-06 — Agent runtime REST router.

Responsibility: HTTP layer for agent execution, management, and gate control.

Endpoints:
  POST   /api/agents                         — create agent definition
  GET    /api/agents                         — list tenant's agents
  GET    /api/agents/{agent_id}             — get agent definition
  PUT    /api/agents/{agent_id}             — update agent (bumps version)
  DELETE /api/agents/{agent_id}             — soft-delete agent
  POST   /api/agents/{agent_id}/run         — start agent run (SSE stream)
  GET    /api/agents/{agent_id}/runs        — run history
  GET    /api/agents/runs/{run_id}          — get run status
  POST   /api/agents/runs/{run_id}/gates/{gate_id}/approve — approve gate
  POST   /api/agents/runs/{run_id}/gates/{gate_id}/reject  — reject gate
  GET    /api/agents/runs/{run_id}/gates    — list pending gates
  POST   /api/webhooks/{tenant_id}/{connector_id}          — webhook receiver
"""
from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.services.agents import definition_store, run_store
from api.services.agents.gate_engine import (
    approve_gate,
    reject_gate,
    list_pending_gates,
    cleanup_run,
)
from api.services.agents.resolver import resolve_agent
from api.schemas.agent_definition.schema import AgentDefinitionSchema

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])
webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    context: dict[str, Any] = {}
    max_delegation_depth: int = 3


class SimulateRequest(BaseModel):
    input: str = "Simulate agent run."
    mocked_tools: dict[str, Any] = {}


# ── Agent CRUD ─────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_agent(
    schema: AgentDefinitionSchema,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        record = definition_store.create_agent(user_id, user_id, schema)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": record.id, "agent_id": record.agent_id, "version": record.version}


@router.get("")
def list_agents(
    user_id: Annotated[str, Depends(get_current_user_id)],
    trigger_family: str | None = Query(default=None, description="Filter by trigger family: conversational, scheduled, on_event"),
) -> list[dict[str, Any]]:
    records = definition_store.list_agents(user_id)
    result = []
    for r in records:
        try:
            schema = definition_store.load_schema(r)
            tf = str(getattr(schema.trigger, "family", "") or "")
            if trigger_family and tf != trigger_family:
                continue
            result.append({
                "id": r.id,
                "agent_id": r.agent_id,
                "name": r.name,
                "version": r.version,
                "description": schema.description or "",
                "tags": list(schema.tags or []),
                "trigger_family": tf,
            })
        except Exception:
            if trigger_family:
                continue
            result.append({
                "id": r.id,
                "agent_id": r.agent_id,
                "name": r.name,
                "version": r.version,
                "description": "",
                "tags": [],
                "trigger_family": "",
            })
    return result


@router.get("/recent")
def list_recent_agents(
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=5, ge=1, le=20),
) -> list[dict[str, Any]]:
    """Return the most recently run agents for the current user, newest first."""
    runs = run_store.list_runs(user_id, agent_id=None, limit=200)
    seen: set[str] = set()
    recent_ids: list[str] = []
    for r in sorted(runs, key=lambda x: str(x.started_at or ""), reverse=True):
        if r.agent_id not in seen:
            seen.add(r.agent_id)
            recent_ids.append(r.agent_id)
        if len(recent_ids) >= limit:
            break

    result = []
    for aid in recent_ids:
        record = definition_store.get_agent(user_id, aid)
        if not record:
            continue
        try:
            schema = definition_store.load_schema(record)
            tf = str(getattr(schema.trigger, "family", "") or "")
            result.append({
                "id": record.id,
                "agent_id": record.agent_id,
                "name": record.name,
                "version": record.version,
                "description": schema.description or "",
                "tags": list(schema.tags or []),
                "trigger_family": tf,
            })
        except Exception:
            result.append({
                "id": record.id,
                "agent_id": record.agent_id,
                "name": record.name,
                "version": record.version,
                "description": "",
                "tags": [],
                "trigger_family": "",
            })
    return result


@router.get("/{agent_id}")
def get_agent(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    version: str | None = None,
) -> dict[str, Any]:
    record = definition_store.get_agent(user_id, agent_id, version)
    if not record:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return {"id": record.id, "agent_id": record.agent_id, "name": record.name, "version": record.version,
            "definition": record.definition}


@router.put("/{agent_id}")
def update_agent(
    agent_id: str,
    schema: AgentDefinitionSchema,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    try:
        record = definition_store.update_agent(user_id, agent_id, user_id, schema)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": record.id, "agent_id": record.agent_id, "version": record.version}


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_agent(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    try:
        definition_store.delete_agent(user_id, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── Agent execution ────────────────────────────────────────────────────────────

@router.post("/{agent_id}/run")
def run_agent(
    agent_id: str,
    body: RunRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> StreamingResponse:
    """Start an agent run and stream activity events + final result as SSE."""
    tenant_id = user_id
    record = definition_store.get_agent(tenant_id, agent_id)
    if not record:
        raise HTTPException(status_code=404, detail="Agent not found.")

    schema = definition_store.load_schema(record)
    run = run_store.create_run(
        tenant_id,
        agent_id,
        conversation_id=body.conversation_id,
        trigger_type="manual",
    )

    def _generate():
        from api.services.agents.gate_engine import GateRejectedError
        from api.services.agents.memory import record_episode, WorkingMemory
        from api.services.agents.runner import run_agent_task
        from api.services.observability.telemetry import record_run_start, record_run_end
        from api.services.observability.cost_tracker import assert_budget_ok, BudgetExceededError

        try:
            assert_budget_ok(tenant_id)
        except BudgetExceededError as exc:
            yield f"data: {json.dumps({'event_type': 'budget_exceeded', 'detail': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"
            run_store.fail_run(run.id, error=str(exc)[:300])
            return

        record_run_start(run.id, agent_id, tenant_id, trigger_type="manual")

        ttl = 3600
        if schema.memory and schema.memory.working:
            ttl = schema.memory.working.ttl_seconds

        working_mem = WorkingMemory(
            tenant_id=tenant_id,
            conversation_id=body.conversation_id or run.id,
            ttl_seconds=ttl,
        )

        # Inject prior context into working memory
        for k, v in (body.context or {}).items():
            working_mem.set(k, v)

        # BUG-02 fix: schema.gates is a list[GateConfig]
        gates = schema.gates or []

        result_parts: list[str] = []
        try:
            for chunk in run_agent_task(
                body.message,
                tenant_id=tenant_id,
                run_id=run.id,
                conversation_id=body.conversation_id,
                system_prompt=schema.system_prompt or None,
                allowed_tool_ids=list(schema.tools) if schema.tools else None,
            ):
                yield f"data: {json.dumps(chunk)}\n\n"
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    result_parts.append(str(text))

            summary = ("".join(result_parts))[:500]
            record_episode(tenant_id, agent_id, run.id, summary=summary, outcome="success")
            run_store.complete_run(run.id, result_summary=summary)
            record_run_end(run.id, status="completed")
            yield f"data: {json.dumps({'event_type': 'run_completed', 'run_id': run.id})}\n\n"

        except GateRejectedError as exc:
            run_store.fail_run(run.id, error=str(exc))
            record_run_end(run.id, status="failed", error=str(exc)[:300])
            yield f"data: {json.dumps({'event_type': 'gate_rejected', 'run_id': run.id, 'detail': str(exc)})}\n\n"
        except Exception as exc:
            logger.error("Agent run %s failed: %s", run.id, exc, exc_info=True)
            run_store.fail_run(run.id, error=str(exc)[:300])
            record_run_end(run.id, status="failed", error=str(exc)[:300])
            yield f"data: {json.dumps({'event_type': 'run_failed', 'run_id': run.id, 'detail': str(exc)[:300]})}\n\n"
        finally:
            cleanup_run(run.id)
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Run history ────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/runs")
def list_runs(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = 50,
) -> list[dict[str, Any]]:
    runs = run_store.list_runs(user_id, agent_id, limit=limit)
    return [
        {
            "run_id": r.id,
            "agent_id": r.agent_id,
            "status": r.status,
            "trigger_type": r.trigger_type,
            "started_at": r.started_at,
            "ended_at": r.ended_at,
            "result_summary": r.result_summary,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    record = run_store.get_run(run_id)
    if not record or record.tenant_id != user_id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "run_id": record.id,
        "agent_id": record.agent_id,
        "status": record.status,
        "trigger_type": record.trigger_type,
        "started_at": record.started_at,
        "ended_at": record.ended_at,
        "error": record.error,
        "result_summary": record.result_summary,
    }


# ── Gate control ───────────────────────────────────────────────────────────────

@router.post("/runs/{run_id}/gates/{gate_id}/approve")
def approve(
    run_id: str,
    gate_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    ok = approve_gate(run_id, gate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Gate not found or already decided.")
    return {"status": "approved", "gate_id": gate_id}


@router.post("/runs/{run_id}/gates/{gate_id}/reject")
def reject(
    run_id: str,
    gate_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    ok = reject_gate(run_id, gate_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Gate not found or already decided.")
    return {"status": "rejected", "gate_id": gate_id}


@router.get("/runs/{run_id}/gates")
def pending_gates(
    run_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    return list_pending_gates(run_id)


# ── Agent simulation (P8-02) ──────────────────────────────────────────────────

@router.post("/{agent_id}/simulate")
def simulate_agent(
    agent_id: str,
    body: SimulateRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Run the agent in dry-run mode against a canned scenario.

    No real tool calls are executed — mocked_tools responses are substituted.
    Returns a full step trace for display in the activity panel.
    """
    from api.services.agents.simulation import run_simulation
    return run_simulation(
        tenant_id=user_id,
        agent_id=agent_id,
        scenario={"input": body.input, "mocked_tools": body.mocked_tools},
    )


# ── Agent memory (P7-05 REST surface) ─────────────────────────────────────────

@router.get("/{agent_id}/memory")
def list_agent_memory(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    """Return all stored long-term memories for this agent."""
    from api.services.agents.long_term_memory import list_memories
    return list_memories(user_id, agent_id)


@router.delete("/{agent_id}/memory", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def clear_agent_memory(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Delete all long-term memories for this agent."""
    from api.services.agents.long_term_memory import clear_memories
    clear_memories(user_id, agent_id)


@router.delete("/{agent_id}/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_agent_memory_entry(
    agent_id: str,
    memory_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Delete a single long-term memory entry."""
    from api.services.agents.long_term_memory import delete_memory
    if not delete_memory(user_id, agent_id, memory_id):
        raise HTTPException(status_code=404, detail="Memory entry not found.")


# ── B10/B12: Schedule health + budget controls ─────────────────────────────────

class RunCapRequest(BaseModel):
    max_runs_per_day: int | None = None  # None clears the cap


@router.get("/{agent_id}/schedule/health")
def get_schedule_health(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """B10: Return failure count, last success/failure for a scheduled agent."""
    from api.services.agents.scheduler import get_schedule_health as _health
    return _health(tenant_id=user_id, agent_id=agent_id)


@router.get("/{agent_id}/usage")
def get_agent_usage(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """B12: Return daily run count and current cap for a scheduled agent."""
    from api.services.agents.scheduler import get_agent_usage as _usage
    return _usage(tenant_id=user_id, agent_id=agent_id)


@router.patch("/{agent_id}/schedule/cap")
def set_run_cap(
    agent_id: str,
    body: RunCapRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """B12: Set or clear the daily run cap for a scheduled agent."""
    from api.services.agents.scheduler import set_agent_run_cap
    if body.max_runs_per_day is not None and body.max_runs_per_day < 1:
        raise HTTPException(status_code=400, detail="max_runs_per_day must be >= 1 or null to clear.")
    updated = set_agent_run_cap(
        tenant_id=user_id,
        agent_id=agent_id,
        max_runs_per_day=body.max_runs_per_day,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="No schedule found for this agent.")
    return {"agent_id": agent_id, "max_runs_per_day": body.max_runs_per_day}


# ── B8: Install history ────────────────────────────────────────────────────────

@router.get("/{agent_id}/install-history")
def get_install_history(
    agent_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    """B8 — Return install/update audit log for this agent in the calling tenant."""
    from api.services.marketplace.installer import get_install_history
    events = get_install_history(user_id, agent_id=agent_id)
    return events[:limit]


# ── Webhook receiver ───────────────────────────────────────────────────────────

@webhook_router.post("/{tenant_id}/{connector_id}")
async def receive_webhook(
    tenant_id: str,
    connector_id: str,
    request: Request,
) -> dict[str, Any]:
    """Receive an external webhook and fan out to subscribed agents."""
    from api.services.agents.event_triggers import handle_webhook_event

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    event_type = str(payload.get("event_type") or payload.get("type") or "unknown")
    run_ids = handle_webhook_event(tenant_id, connector_id, event_type, payload)
    return {"status": "queued", "run_ids": run_ids, "count": len(run_ids)}
