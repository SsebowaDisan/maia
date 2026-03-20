"""Workflow REST router.

Routes:
    POST /api/workflows/generate           — NL description → workflow JSON
    POST /api/workflows/validate           — validate a workflow definition dict
    GET  /api/workflows/templates          — curated starter templates
    GET  /api/workflows                    — list saved workflows for this tenant
    POST /api/workflows                    — save a new workflow definition
    GET  /api/workflows/{id}               — get a saved workflow
    PUT  /api/workflows/{id}               — update a saved workflow
    DELETE /api/workflows/{id}             — delete a workflow (204)
    POST /api/workflows/{id}/run           — execute workflow; stream SSE events
    GET  /api/workflows/{id}/runs          — list past run records for a workflow
    GET  /api/workflows/{id}/runs/{run_id} — get a single run record
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.services.marketplace.abuse_prevention import DailyQuotaExceededError

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    description: str
    max_steps: int = 8


class ValidateRequest(BaseModel):
    definition: dict[str, Any]


class SaveWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    definition: dict[str, Any]


class RunWorkflowRequest(BaseModel):
    initial_inputs: dict[str, Any] = {}


# ── DB-backed workflow store ───────────────────────────────────────────────────

from api.services.workflows.store import (
    create_workflow as _db_create,
    get_workflow as _db_get,
    list_workflows as _db_list,
    update_workflow as _db_update,
    delete_workflow as _db_delete,
    workflow_to_dict as _db_to_dict,
)
from api.services.agents.workflow_run_store import (
    create_run as _db_create_run,
    complete_run as _db_complete_run,
    fail_run as _db_fail_run,
    record_step_output as _db_record_step,
    list_runs as _db_list_runs,
    get_run as _db_get_run,
)


# ── Templates ─────────────────────────────────────────────────────────────────

from api.routers.workflow_templates import WORKFLOW_TEMPLATES
from api.routers.workflow_templates_ext import WORKFLOW_TEMPLATES_EXT

_TEMPLATES = WORKFLOW_TEMPLATES + WORKFLOW_TEMPLATES_EXT


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE message."""
    payload = json.dumps({"event_type": event_type, **data}, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


# ── Assemble and run (Brain builds + executes in one stream) ──────────────────

class AssembleAndRunRequest(BaseModel):
    description: str = Field(min_length=5, max_length=2000)


@router.post("/assemble-and-run")
def assemble_and_run(
    body: AssembleAndRunRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Brain assembles a workflow from description, saves it, and runs it — all streamed live."""
    import queue
    import threading
    from api.services.agent.brain.workflow_assembly import assemble_workflow

    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
    pipeline_started_at = time.monotonic()
    pipeline_last_emit_at = pipeline_started_at

    def _emit_live(event: dict[str, Any]) -> None:
        nonlocal pipeline_last_emit_at
        pipeline_last_emit_at = time.monotonic()
        event_queue.put(event)

    def _run_pipeline() -> None:
        try:
            # Phase 1: Assembly (events stream live via _emit_live)
            result = assemble_workflow(
                description=body.description,
                tenant_id=user_id,
                on_event=_emit_live,
            )
            definition = result.get("definition")
            if not definition:
                if not result.get("error"):
                    _emit_live({"event_type": "assembly_error", "detail": "Assembly failed"})
                return

            # Save the workflow
            try:
                record = _db_create(
                    tenant_id=user_id,
                    name=definition.get("name", "Untitled"),
                    description=definition.get("description", ""),
                    definition=definition,
                    created_by=user_id,
                )
                workflow_id = str(record.id)
                _emit_live({"event_type": "workflow_saved", "data": {"workflow_id": workflow_id, "name": definition.get("name", "")}})
            except Exception as exc:
                _emit_live({"event_type": "assembly_error", "detail": f"Failed to save: {exc}"})
                return

            # Create schedule if detected
            schedule = result.get("schedule")
            if schedule and schedule.get("detected"):
                try:
                    from api.services.agent.report_scheduler import get_report_scheduler
                    get_report_scheduler().create(
                        user_id=user_id,
                        name=f"{definition.get('name', 'Workflow')} — {schedule.get('description', '')}",
                        prompt=f"Run workflow {workflow_id}",
                        frequency=schedule.get("cron", "0 9 * * 1"),
                    )
                    _emit_live({"event_type": "schedule_created", "data": schedule})
                except Exception:
                    pass

            # Phase 2: Execute (events also stream live via _emit_live)
            _emit_live({"event_type": "execution_starting", "data": {"workflow_id": workflow_id}})
            try:
                from api.services.agents.workflow_executor import execute_workflow
                from api.schemas.workflow_definition import WorkflowDefinitionSchema

                wf = WorkflowDefinitionSchema.model_validate(definition)
                outputs = execute_workflow(wf, tenant_id=user_id, on_event=_emit_live)
                _emit_live({"event_type": "execution_complete", "data": {
                    "workflow_id": workflow_id,
                    "outputs": {k: str(v)[:500] for k, v in outputs.items()},
                }})
            except Exception as exc:
                _emit_live({"event_type": "execution_error", "detail": str(exc)[:500]})
        except Exception as exc:
            _emit_live({"event_type": "assembly_error", "detail": f"Pipeline crashed: {str(exc)[:500]}"})
        finally:
            event_queue.put(None)  # Signal end of stream

    # Run pipeline in background thread so events stream immediately
    pipeline_thread = threading.Thread(target=_run_pipeline, daemon=True)
    pipeline_thread.start()
    _emit_live({
        "event_type": "assembly_started",
        "title": "Brain started assembling the workflow",
        "detail": "Planning team roles and dependencies...",
    })

    def _stream():
        heartbeat_interval_seconds = 10.0
        max_pipeline_seconds = float(os.getenv("MAIA_ASSEMBLE_RUN_MAX_SECONDS", "1800"))
        if max_pipeline_seconds < 60:
            max_pipeline_seconds = 60.0
        while True:
            elapsed = time.monotonic() - pipeline_started_at
            if elapsed > max_pipeline_seconds:
                yield _sse(
                    "assembly_error",
                    {"detail": f"Pipeline exceeded max runtime of {int(max_pipeline_seconds)}s and was stopped."},
                )
                yield "data: [DONE]\n\n"
                break
            try:
                event = event_queue.get(timeout=heartbeat_interval_seconds)
            except queue.Empty:
                # Keep connection alive while background pipeline is still running.
                # This prevents false timeout errors during long execution phases.
                if not pipeline_thread.is_alive() and event_queue.empty():
                    yield "data: [DONE]\n\n"
                    break
                idle_seconds = int(time.monotonic() - pipeline_last_emit_at)
                if idle_seconds >= 30 and (idle_seconds % 30 == 0):
                    yield _sse(
                        "execution_progress",
                        {
                            "title": "Workflow still running",
                            "detail": f"Waiting for next event... ({idle_seconds}s since last update)",
                        },
                    )
                yield ": heartbeat\n\n"
                continue
            if event is None:
                yield "data: [DONE]\n\n"
                break
            yield _sse(event.get("event_type", "event"), event)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static / collection routes (must be before /{workflow_id}) ─────────────────

@router.post("/generate")
def generate_workflow(
    body: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Generate a workflow definition from a plain-English description."""
    from api.services.agents.nl_workflow_builder import generate_workflow as _gen

    if not body.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty.")
    try:
        definition = _gen(
            body.description,
            tenant_id=user_id,
            max_steps=max(1, min(body.max_steps, 20)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"definition": definition}


@router.post("/generate/stream")
def generate_workflow_stream(
    body: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Stream a workflow definition token-by-token as it is generated by the LLM."""
    from api.services.agents.nl_workflow_builder import generate_workflow_stream as _gen_stream

    if not body.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty.")

    def _generate():
        try:
            for chunk in _gen_stream(
                body.description,
                tenant_id=user_id,
                max_steps=max(1, min(body.max_steps, 20)),
            ):
                yield _sse("nl_build_delta", {"delta": chunk.get("delta", ""), "done": chunk.get("done", False), "definition": chunk.get("definition")})
        except Exception as exc:
            yield _sse("nl_build_error", {"error": str(exc)[:300]})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/validate")
def validate_workflow(
    body: ValidateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Validate a workflow definition dict — schema, DAG, and agent resolution."""
    from api.services.agents.nl_workflow_builder import validate_workflow as _val

    result = _val(body.definition)
    if not result["valid"]:
        return result

    # Extended checks: agent resolution and tool availability
    warnings: list[str] = []
    try:
        from api.services.agents.definition_store import get_agent
        from api.services.marketplace.installer import get_tenant_connector_status

        steps = body.definition.get("steps") or []
        for step in steps:
            step_id = step.get("step_id", "?")
            agent_id = step.get("agent_id", "")
            if not agent_id:
                continue

            agent_record = get_agent(user_id, agent_id)
            if not agent_record:
                warnings.append(
                    f"step '{step_id}': agent '{agent_id}' is not registered for this tenant."
                )
                continue

            # B5 — check that the agent's required connectors are bound for this tenant.
            # Surface as warnings (not errors) so the user can design workflows before
            # completing connector setup.
            try:
                definition = agent_record.definition or {}
                required_connectors: list[str] = list(definition.get("required_connectors") or [])
                if required_connectors:
                    connector_status = get_tenant_connector_status(user_id, required_connectors)
                    missing = [c for c, s in connector_status.items() if s == "missing"]
                    if missing:
                        warnings.append(
                            f"step '{step_id}': agent '{agent_id}' requires connectors that are "
                            f"not yet configured for this tenant: {', '.join(missing)}."
                        )
            except Exception:
                pass  # connector check is best-effort
    except Exception:
        pass  # agent store unavailable — skip resolution check

    # DAG cycle check (already done by pydantic validator, but surface the path)
    try:
        from api.schemas.workflow_definition import WorkflowDefinitionSchema
        wf = WorkflowDefinitionSchema.model_validate(body.definition)
        wf.topological_order()
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "warnings": warnings}

    return {"valid": True, "errors": [], "warnings": warnings}


@router.get("/templates")
def list_templates() -> list[dict[str, Any]]:
    """Return curated starter workflow templates."""
    return _TEMPLATES


@router.get("/templates/{template_id}/preview")
def get_template_preview(template_id: str) -> dict[str, Any]:
    """Get or generate a sample output preview for a template."""
    template = next((t for t in _TEMPLATES if t.get("template_id") == template_id), None)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found.")
    from api.services.workflows.template_preview import generate_preview
    return generate_preview(template_id, template.get("definition", {}))


@router.get("/team-archetypes")
def list_team_archetypes() -> list[dict[str, Any]]:
    """Return available team archetypes for multi-agent workflows."""
    from api.services.workflows.team_archetypes import list_archetypes
    return list_archetypes()


@router.get("/team-archetypes/{archetype_id}")
def get_team_archetype(archetype_id: str) -> dict[str, Any]:
    """Return a specific team archetype with full agent definitions."""
    from api.services.workflows.team_archetypes import get_archetype
    result = get_archetype(archetype_id)
    if not result:
        raise HTTPException(status_code=404, detail="Archetype not found.")
    return {"id": archetype_id, **result}


@router.get("")
def list_workflows(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    records = _db_list(user_id)
    return [_db_to_dict(r) for r in records]


@router.post("", status_code=status.HTTP_201_CREATED)
def save_workflow(
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    record = _db_create(
        tenant_id=user_id,
        name=body.name,
        description=body.description,
        definition=body.definition,
        created_by=user_id,
    )
    # Record initial version for audit trail
    try:
        from api.services.versions.store import create_version
        create_version(
            resource_type="workflow",
            resource_id=record.id,
            tenant_id=user_id,
            version="1.0.0",
            definition=json.dumps(body.definition, default=str),
            created_by=user_id,
            changelog="Initial creation",
        )
    except Exception:
        pass
    return _db_to_dict(record)


# ── Item routes (/{workflow_id} and sub-paths) ────────────────────────────────

@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    record = _db_get(workflow_id, user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return _db_to_dict(record)


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: str,
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    record = _db_update(workflow_id, user_id, body.name, body.description, body.definition)
    if not record:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    # Record new version for audit trail
    try:
        from api.services.versions.store import create_version, get_latest_version, next_version
        latest = get_latest_version("workflow", workflow_id)
        ver = next_version(latest.version) if latest else "1.0.0"
        create_version(
            resource_type="workflow",
            resource_id=workflow_id,
            tenant_id=user_id,
            version=ver,
            definition=json.dumps(body.definition, default=str),
            created_by=user_id,
            changelog="Updated workflow",
        )
    except Exception:
        pass
    return _db_to_dict(record)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    if not _db_delete(workflow_id, user_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")


@router.post("/{workflow_id}/run")
def run_workflow(
    workflow_id: str,
    body: RunWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Execute a workflow and stream SSE events for every state transition.

    Event types (``event_type`` field in each SSE payload):
      workflow_started, workflow_step_started, workflow_step_progress,
      workflow_step_completed, workflow_step_skipped, workflow_step_failed,
      workflow_completed, workflow_failed
    """
    # Load + parse the workflow definition
    wf_record = _db_get(workflow_id, user_id)
    if not wf_record:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    row = _db_to_dict(wf_record)

    from api.schemas.workflow_definition import WorkflowDefinitionSchema
    from pydantic import ValidationError

    try:
        wf = WorkflowDefinitionSchema.model_validate(row["definition"])
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid workflow definition: {exc}") from exc

    started_at = time.time()

    # Initialise run record in DB
    db_run = _db_create_run(tenant_id=user_id, workflow_id=workflow_id, triggered_by="manual")
    run_id = db_run.id

    # In-memory dict for SSE streaming state (not persisted directly)
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "status": "running",
        "step_results": [],
        "final_outputs": {},
        "error": "",
        "duration_ms": 0,
    }

    # Queue-based bridge: executor thread → SSE generator (bounded to prevent OOM)
    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=10_000)
    step_start_times: dict[str, float] = {}

    from api.services.agent.live_events import get_live_event_broker
    _broker = get_live_event_broker()

    def _on_event(evt: dict[str, Any]) -> None:
        event_queue.put(evt)
        try:
            _broker.publish(user_id=user_id, event=evt, run_id=run_id)
        except Exception:
            pass

    def _executor_thread() -> None:
        from api.services.agents.workflow_executor import execute_workflow, WorkflowExecutionError
        try:
            outputs = execute_workflow(
                wf,
                tenant_id=user_id,
                initial_inputs=body.initial_inputs,
                on_event=_on_event,
                run_id=run_id,
            )
            finished = time.time()
            run_record.update({
                "status": "completed",
                "duration_ms": int((finished - started_at) * 1000),
                "final_outputs": {k: str(v)[:500] for k, v in outputs.items()},
            })
            _db_complete_run(run_id)
        except (WorkflowExecutionError, Exception) as exc:
            finished = time.time()
            run_record.update({
                "status": "failed",
                "duration_ms": int((finished - started_at) * 1000),
                "error": str(exc)[:500],
            })
            _db_fail_run(run_id, str(exc)[:500])
        finally:
            event_queue.put(None)  # sentinel — signals end of stream

    thread = threading.Thread(target=_executor_thread, daemon=True)
    thread.start()

    def _generate():
        # Emit run_id immediately so the frontend can correlate events
        yield _sse("run_started", {"run_id": run_id, "workflow_id": workflow_id})

        while True:
            try:
                evt = event_queue.get(timeout=60)
            except queue.Empty:
                yield _sse("workflow_failed", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "error": "Execution timed out.",
                })
                break

            if evt is None:
                # Executor finished — emit final summary event
                if run_record["status"] == "completed":
                    yield _sse("workflow_completed", {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "outputs": run_record["final_outputs"],
                        "duration_ms": run_record["duration_ms"],
                    })
                else:
                    yield _sse("workflow_failed", {
                        "workflow_id": workflow_id,
                        "run_id": run_id,
                        "error": run_record.get("error", "Unknown error"),
                        "duration_ms": run_record["duration_ms"],
                    })
                break

            event_type = evt.get("event_type", "")

            if event_type == "workflow_started":
                yield _sse("workflow_started", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_count": evt.get("step_count", 0),
                    "step_order": evt.get("step_order", []),
                })

            elif event_type == "workflow_step_started":
                step_id = evt.get("step_id", "")
                step_start_times[step_id] = time.time()
                yield _sse("workflow_step_started", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": step_id,
                    "agent_id": evt.get("agent_id", ""),
                })

            elif event_type == "workflow_step_completed":
                step_id = evt.get("step_id", "")
                duration_ms = int((time.time() - step_start_times.pop(step_id, time.time())) * 1000)
                step_result = {
                    "step_id": step_id,
                    "agent_id": evt.get("agent_id", ""),
                    "status": "completed",
                    "output_preview": evt.get("result_preview", "")[:2000],
                    "duration_ms": duration_ms,
                }
                run_record.setdefault("step_results", []).append(step_result)
                yield _sse("workflow_step_completed", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": step_id,
                    "agent_id": evt.get("agent_id", ""),
                    "output_key": evt.get("output_key", ""),
                    "result_preview": evt.get("result_preview", "")[:2000],
                    "duration_ms": duration_ms,
                })

            elif event_type == "workflow_step_skipped":
                step_id = evt.get("step_id", "")
                run_record.setdefault("step_results", []).append({
                    "step_id": step_id,
                    "agent_id": "",
                    "status": "skipped",
                    "output_preview": "",
                    "duration_ms": 0,
                })
                yield _sse("workflow_step_skipped", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": step_id,
                    "reason": evt.get("reason", "condition_false"),
                })

            elif event_type == "workflow_step_retrying":
                yield _sse("workflow_step_retrying", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": evt.get("step_id", ""),
                    "attempt": evt.get("attempt", 1),
                    "max_attempts": evt.get("max_attempts", 1),
                    "delay_s": evt.get("delay_s", 0),
                    "error": evt.get("error", ""),
                })

            elif event_type == "workflow_step_failed":
                step_id = evt.get("step_id", "")
                duration_ms = int((time.time() - step_start_times.pop(step_id, time.time())) * 1000)
                run_record.setdefault("step_results", []).append({
                    "step_id": step_id,
                    "agent_id": evt.get("agent_id", ""),
                    "status": "failed",
                    "error": evt.get("error", "")[:2000],
                    "duration_ms": duration_ms,
                })
                yield _sse("workflow_step_failed", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": step_id,
                    "error": evt.get("error", ""),
                    "retryable": False,
                })

            elif event_type == "workflow_step_output_invalid":
                yield _sse("workflow_step_output_invalid", {
                    "workflow_id": workflow_id,
                    "run_id": run_id,
                    "step_id": evt.get("step_id", ""),
                    "validation_error": evt.get("validation_error", ""),
                })

            else:
                # Pass-through for any agent-level deltas (text chunks from _run_step)
                text = evt.get("text") or evt.get("content") or ""
                if text:
                    step_agent = evt.get("step_agent_id", "")
                    # Find the currently running step_id from step_start_times
                    active_step = next(iter(step_start_times), "")
                    if active_step:
                        yield _sse("workflow_step_progress", {
                            "workflow_id": workflow_id,
                            "run_id": run_id,
                            "step_id": active_step,
                            "agent_id": step_agent,
                            "delta": str(text),
                        })

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{workflow_id}/runs")
def list_runs(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return run history for a workflow, newest first."""
    records = _db_list_runs(tenant_id=user_id, workflow_id=workflow_id, limit=limit, offset=offset)
    return [
        {
            "run_id": r.id,
            "workflow_id": r.workflow_id,
            "tenant_id": r.tenant_id,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.completed_at,
            "duration_ms": int((r.completed_at - r.started_at) * 1000) if r.completed_at else 0,
            "step_results": [
                {"step_id": sid, **sdata}
                for sid, sdata in (r.step_outputs or {}).items()
            ],
            "error": r.error or "",
        }
        for r in records
    ]


@router.get("/{workflow_id}/runs/{run_id}")
def get_run(
    workflow_id: str,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return a single run record including per-step results."""
    r = _db_get_run(run_id)
    if not r or r.workflow_id != workflow_id or r.tenant_id != user_id:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {
        "run_id": r.id,
        "workflow_id": r.workflow_id,
        "tenant_id": r.tenant_id,
        "status": r.status,
        "started_at": r.started_at,
        "finished_at": r.completed_at,
        "duration_ms": int((r.completed_at - r.started_at) * 1000) if r.completed_at else 0,
        "step_results": [
            {"step_id": sid, **sdata}
            for sid, sdata in (r.step_outputs or {}).items()
        ],
        "error": r.error or "",
    }


class ReplayRequest(BaseModel):
    from_step_id: str
    initial_inputs: dict[str, Any] = {}


@router.post("/{workflow_id}/share")
def share_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Publish (or update) a workflow in the public marketplace and return share URL."""
    workflow = _db_get(workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    payload = _db_to_dict(workflow)
    definition = payload.get("definition") or {}
    published = None
    try:
        from api.services.marketplace.workflow_publisher import publish_workflow

        published = publish_workflow(
            creator_id=user_id,
            source_workflow_id=workflow_id,
            name=str(payload.get("name") or definition.get("name") or "Untitled team"),
            description=str(payload.get("description") or definition.get("description") or ""),
            readme_md=str(definition.get("readme_md") or definition.get("readme") or ""),
            definition=definition if isinstance(definition, dict) else {},
            category=str(definition.get("category") or "other"),
            tags=[str(tag).strip() for tag in (definition.get("tags") or []) if str(tag).strip()],
            screenshots=[
                str(item).strip()
                for item in (definition.get("screenshots") or [])
                if str(item).strip()
            ],
        )
    except DailyQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to share workflow: {exc}") from exc

    slug = str((published or {}).get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=500, detail="Failed to generate share slug.")
    public_path = f"/marketplace/teams/{slug}"
    public_base = str(os.getenv("MAIA_PUBLIC_APP_URL") or "").strip().rstrip("/")
    public_url = f"{public_base}{public_path}" if public_base else public_path
    og_url = (
        f"{public_base}/api/og/image/teams/{slug}.svg"
        if public_base
        else f"/api/og/image/teams/{slug}.svg"
    )
    return {
        "workflow_id": workflow_id,
        "slug": slug,
        "public_path": public_path,
        "public_url": public_url,
        "og_image_url": og_url,
    }


@router.post("/{workflow_id}/runs/{run_id}/replay")
def replay_workflow_from_step(
    workflow_id: str,
    run_id: str,
    body: ReplayRequest,
    user_id: str = Depends(get_current_user_id),
) -> StreamingResponse:
    """Re-execute a workflow from a specific step using stored prior-step outputs.

    B11: Useful for debugging failed runs — re-runs from the failed step without
    re-running all prior steps.  Steps before from_step_id are seeded from the
    stored step_outputs of the original run.
    """
    # Load original run record to seed prior step outputs
    original_run = _db_get_run(run_id)
    if not original_run or original_run.tenant_id != user_id:
        raise HTTPException(status_code=404, detail="Original run not found.")

    # Load + parse workflow definition
    wf_record = _db_get(workflow_id, user_id)
    if not wf_record:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    row = _db_to_dict(wf_record)

    from api.schemas.workflow_definition import WorkflowDefinitionSchema
    from pydantic import ValidationError

    try:
        wf = WorkflowDefinitionSchema.model_validate(row["definition"])
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid workflow definition: {exc}") from exc

    # Seed outputs from the stored step_results of the original run
    ordered = wf.topological_order()
    # Build step_id → output_key mapping so replay seeds by output_key
    step_output_keys = {s.step_id: s.output_key for s in wf.steps}
    seeded_outputs: dict[str, Any] = dict(body.initial_inputs)
    from api.services.agents.workflow_run_store import get_step_outputs_for_replay
    prior_outputs = get_step_outputs_for_replay(run_id, body.from_step_id, ordered, step_output_keys)
    seeded_outputs.update(prior_outputs)

    started_at = time.time()
    replay_db_run = _db_create_run(tenant_id=user_id, workflow_id=workflow_id, triggered_by="replay")
    new_run_id = replay_db_run.id
    run_record: dict[str, Any] = {
        "run_id": new_run_id,
        "status": "running",
        "final_outputs": {},
        "error": "",
        "duration_ms": 0,
    }

    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    from api.services.agent.live_events import get_live_event_broker
    _replay_broker = get_live_event_broker()

    def _on_event(evt: dict[str, Any]) -> None:
        event_queue.put(evt)
        try:
            _replay_broker.publish(user_id=user_id, event=evt, run_id=new_run_id)
        except Exception:
            pass

    def _replay_thread() -> None:
        from api.services.agents.workflow_executor import execute_workflow, WorkflowExecutionError
        try:
            outputs = execute_workflow(
                wf,
                tenant_id=user_id,
                initial_inputs=seeded_outputs,
                on_event=_on_event,
                run_id=new_run_id,
            )
            finished = time.time()
            run_record.update({
                "status": "completed",
                "duration_ms": int((finished - started_at) * 1000),
                "final_outputs": {k: str(v)[:500] for k, v in outputs.items()},
            })
            _db_complete_run(new_run_id)
        except Exception as exc:
            finished = time.time()
            run_record.update({
                "status": "failed",
                "duration_ms": int((finished - started_at) * 1000),
                "error": str(exc)[:500],
            })
            _db_fail_run(new_run_id, str(exc)[:500])
        finally:
            event_queue.put(None)

    threading.Thread(target=_replay_thread, daemon=True).start()

    def _generate():
        yield _sse("run_started", {"run_id": new_run_id, "workflow_id": workflow_id, "replay": True})
        while True:
            try:
                evt = event_queue.get(timeout=60)
            except queue.Empty:
                yield _sse("workflow_failed", {"run_id": new_run_id, "error": "Replay timed out."})
                break
            if evt is None:
                if run_record["status"] == "completed":
                    yield _sse("workflow_completed", {"run_id": new_run_id, "outputs": run_record["final_outputs"]})
                else:
                    yield _sse("workflow_failed", {"run_id": new_run_id, "error": run_record.get("error", "")})
                break
            yield _sse(evt.get("event_type", "event"), evt)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Dead-letter introspection ────────────────────────────────────────────────

@router.get("/{workflow_id}/dead-letters")
def list_dead_letters(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List dead-letter entries for failed steps in a workflow."""
    from api.services.workflows.dead_letter import list_dead_letters as _dl_list

    entries = _dl_list(tenant_id=user_id, workflow_id=workflow_id, limit=limit)
    return [
        {
            "id": e.id,
            "run_id": e.run_id,
            "step_id": e.step_id,
            "step_type": e.step_type,
            "error": e.error,
            "inputs": e.inputs,
            "attempt": e.attempt,
            "date_created": e.date_created.isoformat() if e.date_created else "",
        }
        for e in entries
    ]
