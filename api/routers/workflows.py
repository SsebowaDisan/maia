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


# ── Workflow definition store (JSON file) ─────────────────────────────────────

_store_lock = threading.Lock()


def _store_path():
    from pathlib import Path
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "workflows.json"


def _load_all() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_all(rows: list[dict[str, Any]]) -> None:
    _store_path().write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ── Run history store (JSON file) ─────────────────────────────────────────────

_runs_lock = threading.Lock()


def _runs_path():
    from pathlib import Path
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "workflow_runs.json"


def _load_runs() -> list[dict[str, Any]]:
    path = _runs_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_runs(rows: list[dict[str, Any]]) -> None:
    _runs_path().write_text(json.dumps(rows, indent=2), encoding="utf-8")


def _upsert_run(record: dict[str, Any]) -> None:
    with _runs_lock:
        runs = _load_runs()
        idx = next((i for i, r in enumerate(runs) if r.get("run_id") == record["run_id"]), None)
        if idx is not None:
            runs[idx] = record
        else:
            runs.append(record)
        _save_runs(runs)


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
    with _store_lock:
        rows = _load_all()
    return [r for r in rows if r.get("tenant_id") == user_id]


@router.post("", status_code=status.HTTP_201_CREATED)
def save_workflow(
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    now = time.time()
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "tenant_id": user_id,
        "name": body.name.strip() or "Untitled workflow",
        "description": body.description,
        "definition": body.definition,
        "created_at": now,
        "updated_at": now,
    }
    with _store_lock:
        rows = _load_all()
        rows.append(row)
        _save_all(rows)
    return row


# ── Item routes (/{workflow_id} and sub-paths) ────────────────────────────────

@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with _store_lock:
        rows = _load_all()
    row = next((r for r in rows if r["id"] == workflow_id and r.get("tenant_id") == user_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return row


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: str,
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with _store_lock:
        rows = _load_all()
        for i, row in enumerate(rows):
            if row["id"] == workflow_id and row.get("tenant_id") == user_id:
                rows[i] = {
                    **row,
                    "name": body.name.strip() or row["name"],
                    "description": body.description,
                    "definition": body.definition,
                    "updated_at": time.time(),
                }
                _save_all(rows)
                return rows[i]
    raise HTTPException(status_code=404, detail="Workflow not found.")


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    with _store_lock:
        rows = _load_all()
        before = len(rows)
        rows = [r for r in rows if not (r["id"] == workflow_id and r.get("tenant_id") == user_id)]
        if len(rows) == before:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        _save_all(rows)


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
    with _store_lock:
        rows = _load_all()
    row = next((r for r in rows if r["id"] == workflow_id and r.get("tenant_id") == user_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    from api.schemas.workflow_definition import WorkflowDefinitionSchema
    from pydantic import ValidationError

    try:
        wf = WorkflowDefinitionSchema.model_validate(row["definition"])
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid workflow definition: {exc}") from exc

    run_id = str(uuid.uuid4())
    started_at = time.time()

    # Initialise run record in history store
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "tenant_id": user_id,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": 0,
        "step_results": [],
        "final_outputs": {},
        "error": "",
    }
    _upsert_run(run_record)

    # Queue-based bridge: executor thread → SSE generator
    event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
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
            )
            finished = time.time()
            run_record.update({
                "status": "completed",
                "finished_at": finished,
                "duration_ms": int((finished - started_at) * 1000),
                "final_outputs": {k: str(v)[:500] for k, v in outputs.items()},
            })
        except WorkflowExecutionError as exc:
            finished = time.time()
            run_record.update({
                "status": "failed",
                "finished_at": finished,
                "duration_ms": int((finished - started_at) * 1000),
                "error": str(exc)[:500],
            })
        except Exception as exc:
            finished = time.time()
            run_record.update({
                "status": "failed",
                "finished_at": finished,
                "duration_ms": int((finished - started_at) * 1000),
                "error": str(exc)[:500],
            })
        finally:
            _upsert_run(run_record)
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
    """Return run history for a workflow, newest first. Supports limit/offset pagination."""
    with _runs_lock:
        runs = _load_runs()
    filtered = [
        r for r in runs
        if r.get("workflow_id") == workflow_id and r.get("tenant_id") == user_id
    ]
    sorted_runs = sorted(filtered, key=lambda r: r.get("started_at", 0), reverse=True)
    return sorted_runs[offset: offset + limit]


@router.get("/{workflow_id}/runs/{run_id}")
def get_run(
    workflow_id: str,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Return a single run record including per-step results."""
    with _runs_lock:
        runs = _load_runs()
    record = next(
        (
            r for r in runs
            if r.get("run_id") == run_id
            and r.get("workflow_id") == workflow_id
            and r.get("tenant_id") == user_id
        ),
        None,
    )
    if not record:
        raise HTTPException(status_code=404, detail="Run not found.")
    return record


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
    with _runs_lock:
        runs = _load_runs()
    original = next(
        (r for r in runs if r.get("run_id") == run_id and r.get("tenant_id") == user_id),
        None,
    )
    if not original:
        raise HTTPException(status_code=404, detail="Original run not found.")

    # Load + parse workflow definition
    with _store_lock:
        rows = _load_all()
    row = next((r for r in rows if r["id"] == workflow_id and r.get("tenant_id") == user_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    from api.schemas.workflow_definition import WorkflowDefinitionSchema
    from pydantic import ValidationError

    try:
        wf = WorkflowDefinitionSchema.model_validate(row["definition"])
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid workflow definition: {exc}") from exc

    # Seed outputs from the stored step_results of the original run
    ordered = wf.topological_order()
    seeded_outputs: dict[str, Any] = dict(body.initial_inputs)
    prior_steps = original.get("step_results") or []
    for step_result in prior_steps:
        sid = step_result.get("step_id", "")
        if sid == body.from_step_id:
            break
        seeded_outputs[sid] = step_result.get("output_preview", "")

    new_run_id = str(uuid.uuid4())
    started_at = time.time()
    run_record: dict[str, Any] = {
        "run_id": new_run_id,
        "workflow_id": workflow_id,
        "tenant_id": user_id,
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": 0,
        "step_results": [],
        "final_outputs": {},
        "error": "",
        "replayed_from_run": run_id,
        "replayed_from_step": body.from_step_id,
    }
    _upsert_run(run_record)

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
                "finished_at": finished,
                "duration_ms": int((finished - started_at) * 1000),
                "final_outputs": {k: str(v)[:500] for k, v in outputs.items()},
            })
        except Exception as exc:
            finished = time.time()
            run_record.update({
                "status": "failed",
                "finished_at": finished,
                "duration_ms": int((finished - started_at) * 1000),
                "error": str(exc)[:500],
            })
        finally:
            _upsert_run(run_record)
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
