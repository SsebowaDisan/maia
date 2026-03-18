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
import queue
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id

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

_TEMPLATES: list[dict[str, Any]] = [
    {
        "template_id": "research-summarise-email",
        "name": "Research → Summarise → Email",
        "description": "Search the web for a topic, summarise the findings, then draft and send an email report.",
        "step_count": 3,
        "tags": ["research", "email", "report"],
        "definition": {
            "workflow_id": "research-summarise-email",
            "name": "Research → Summarise → Email",
            "description": "Search the web for a topic, summarise the findings, then send an email.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_research",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Enter your research topic here"},
                    "output_key": "research_result",
                    "description": "Search the web and gather key findings on the topic.",
                },
                {
                    "step_id": "step_summarise",
                    "agent_id": "analyst",
                    "input_mapping": {"content": "research_result"},
                    "output_key": "summary",
                    "description": "Synthesise the research into a concise executive summary.",
                },
                {
                    "step_id": "step_email",
                    "agent_id": "deliverer",
                    "input_mapping": {"body": "summary", "subject": "literal:Research Summary"},
                    "output_key": "email_sent",
                    "description": "Draft and send the summary as an email.",
                },
            ],
            "edges": [
                {"from_step": "step_research", "to_step": "step_summarise"},
                {"from_step": "step_summarise", "to_step": "step_email"},
            ],
        },
    },
    {
        "template_id": "scrape-analyse-report",
        "name": "Scrape → Analyse → Report",
        "description": "Browse a URL, extract structured data, analyse it, and produce a markdown report.",
        "step_count": 3,
        "tags": ["scraping", "analysis", "report"],
        "definition": {
            "workflow_id": "scrape-analyse-report",
            "name": "Scrape → Analyse → Report",
            "description": "Browse a URL, extract data, and produce a markdown report.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_scrape",
                    "agent_id": "browser",
                    "input_mapping": {"url": "literal:https://example.com"},
                    "output_key": "raw_content",
                    "description": "Browse the target URL and extract the page content.",
                },
                {
                    "step_id": "step_analyse",
                    "agent_id": "analyst",
                    "input_mapping": {"data": "raw_content"},
                    "output_key": "analysis",
                    "description": "Identify key patterns, numbers, and insights in the extracted content.",
                },
                {
                    "step_id": "step_report",
                    "agent_id": "writer",
                    "input_mapping": {"content": "analysis"},
                    "output_key": "report",
                    "description": "Format the analysis as a structured markdown report with sections and tables.",
                },
            ],
            "edges": [
                {"from_step": "step_scrape", "to_step": "step_analyse"},
                {"from_step": "step_analyse", "to_step": "step_report"},
            ],
        },
    },
    {
        "template_id": "monitor-alert-escalate",
        "name": "Monitor → Alert → Escalate",
        "description": "Check a data source for anomalies, send an alert if found, escalate if critical.",
        "step_count": 3,
        "tags": ["monitoring", "alerting", "conditional"],
        "definition": {
            "workflow_id": "monitor-alert-escalate",
            "name": "Monitor → Alert → Escalate",
            "description": "Check a source, alert on anomaly, escalate if critical.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_monitor",
                    "agent_id": "analyst",
                    "input_mapping": {"source": "literal:Describe the data source to monitor"},
                    "output_key": "monitor_result",
                    "description": "Fetch and evaluate the data source for anomalies or threshold breaches.",
                },
                {
                    "step_id": "step_alert",
                    "agent_id": "deliverer",
                    "input_mapping": {"message": "monitor_result"},
                    "output_key": "alert_sent",
                    "description": "Send a Slack or email alert with the anomaly details.",
                },
                {
                    "step_id": "step_escalate",
                    "agent_id": "deliverer",
                    "input_mapping": {"message": "monitor_result", "channel": "literal:escalation-team"},
                    "output_key": "escalation_sent",
                    "description": "Escalate to the on-call team if the severity is critical.",
                },
            ],
            "edges": [
                {"from_step": "step_monitor", "to_step": "step_alert"},
                {
                    "from_step": "step_alert",
                    "to_step": "step_escalate",
                    "condition": "output.alert_sent == 'critical'",
                },
            ],
        },
    },
    {
        "template_id": "ingest-index-notify",
        "name": "Ingest → Index → Notify",
        "description": "Pull a document from a URL, index it into the knowledge base, then notify the team.",
        "step_count": 3,
        "tags": ["ingestion", "knowledge-base", "notification"],
        "definition": {
            "workflow_id": "ingest-index-notify",
            "name": "Ingest → Index → Notify",
            "description": "Fetch a document, index it, notify the team.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_fetch",
                    "agent_id": "browser",
                    "input_mapping": {"url": "literal:https://example.com/document.pdf"},
                    "output_key": "document_content",
                    "description": "Download and extract the raw text content of the document.",
                },
                {
                    "step_id": "step_index",
                    "agent_id": "indexer",
                    "input_mapping": {"content": "document_content"},
                    "output_key": "index_result",
                    "description": "Chunk, embed, and store the document in the vector knowledge base.",
                },
                {
                    "step_id": "step_notify",
                    "agent_id": "deliverer",
                    "input_mapping": {"message": "index_result"},
                    "output_key": "notification_sent",
                    "description": "Send a notification confirming the document was indexed successfully.",
                },
            ],
            "edges": [
                {"from_step": "step_fetch", "to_step": "step_index"},
                {"from_step": "step_index", "to_step": "step_notify"},
            ],
        },
    },
    {
        "template_id": "competitive-intel",
        "name": "Competitive Intelligence",
        "description": "Research competitors, extract positioning data, and produce a comparison table.",
        "step_count": 4,
        "tags": ["research", "competitive", "analysis"],
        "definition": {
            "workflow_id": "competitive-intel",
            "name": "Competitive Intelligence",
            "description": "Research competitors and produce a comparison report.",
            "version": "1.0.0",
            "steps": [
                {
                    "step_id": "step_research_a",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Competitor A pricing and features"},
                    "output_key": "competitor_a",
                    "description": "Research Competitor A — gather pricing, key features, and market positioning.",
                },
                {
                    "step_id": "step_research_b",
                    "agent_id": "researcher",
                    "input_mapping": {"query": "literal:Competitor B pricing and features"},
                    "output_key": "competitor_b",
                    "description": "Research Competitor B — gather pricing, key features, and market positioning.",
                },
                {
                    "step_id": "step_compare",
                    "agent_id": "analyst",
                    "input_mapping": {
                        "data_a": "competitor_a",
                        "data_b": "competitor_b",
                    },
                    "output_key": "comparison",
                    "description": "Compare both competitors across price, features, strengths, and weaknesses.",
                },
                {
                    "step_id": "step_report",
                    "agent_id": "writer",
                    "input_mapping": {"content": "comparison"},
                    "output_key": "report",
                    "description": "Produce a markdown report with an executive summary and comparison table.",
                },
            ],
            "edges": [
                {"from_step": "step_research_a", "to_step": "step_compare"},
                {"from_step": "step_research_b", "to_step": "step_compare"},
                {"from_step": "step_compare", "to_step": "step_report"},
            ],
        },
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict[str, Any]) -> str:
    """Format a single SSE message."""
    payload = json.dumps({"event_type": event_type, **data}, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


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
