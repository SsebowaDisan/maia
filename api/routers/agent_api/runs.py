from __future__ import annotations

import json
import logging
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import get_current_user_id
from api.services.agent.activity import get_activity_store
from api.services.agent.memory import get_memory_service

router = APIRouter(tags=["agent"])

_logger = logging.getLogger(__name__)


def _merge_telemetry_into_runs(
    legacy_rows: list[dict[str, Any]],
    user_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Merge legacy JSON-file runs with structured telemetry DB records.

    Telemetry records that don't exist in legacy store are added as new rows.
    Legacy rows are enriched with telemetry fields (status, duration, cost, tokens).
    """
    try:
        from api.services.observability.telemetry import query_runs
        from api.services.observability.cost_tracker import get_daily_cost
        from api.services.observability.model_pricing import calculate_token_cost_usd
    except Exception:
        return legacy_rows

    # Index legacy rows by run_id for fast lookup
    legacy_by_id: dict[str, dict[str, Any]] = {}
    for row in legacy_rows:
        rid = str(row.get("run_id") or row.get("id") or "").strip()
        if rid:
            legacy_by_id[rid] = row

    try:
        telemetry_runs = query_runs(tenant_id=user_id, limit=limit)
    except Exception:
        telemetry_runs = []

    for t_run in telemetry_runs:
        started_iso = (
            datetime.fromtimestamp(t_run.started_at, tz=timezone.utc).isoformat()
            if t_run.started_at
            else None
        )
        ended_iso = (
            datetime.fromtimestamp(t_run.ended_at, tz=timezone.utc).isoformat()
            if t_run.ended_at
            else None
        )
        duration_ms = (
            int((t_run.ended_at - t_run.started_at) * 1000)
            if t_run.ended_at and t_run.started_at
            else None
        )

        # Calculate LLM cost from token counts
        llm_cost = 0.0
        try:
            llm_cost = calculate_token_cost_usd(
                model=None,
                tokens_in=t_run.tokens_in or 0,
                tokens_out=t_run.tokens_out or 0,
            )
        except Exception:
            pass

        tool_calls_list = []
        try:
            tool_calls_list = json.loads(t_run.tool_calls_json) if t_run.tool_calls_json else []
        except Exception:
            pass

        telemetry_fields = {
            "status": t_run.status,
            "trigger_type": t_run.trigger_type,
            "started_at": started_iso,
            "ended_at": ended_iso,
            "duration_ms": duration_ms,
            "tokens_in": t_run.tokens_in,
            "tokens_out": t_run.tokens_out,
            "llm_cost_usd": round(llm_cost, 6),
            "tool_call_count": len(tool_calls_list),
            "computer_use_steps": t_run.computer_use_steps,
            "error": t_run.error,
        }

        if t_run.run_id in legacy_by_id:
            # Enrich existing legacy row
            legacy_by_id[t_run.run_id].update(telemetry_fields)
        else:
            # Create a new row from telemetry-only data
            new_row: dict[str, Any] = {
                "id": t_run.run_id,
                "run_id": t_run.run_id,
                "agent_id": t_run.agent_id,
                "date_created": started_iso or datetime.now(timezone.utc).isoformat(),
                **telemetry_fields,
            }
            legacy_rows.append(new_row)

    # Sort by most recent first
    legacy_rows.sort(
        key=lambda r: r.get("started_at") or r.get("date_created") or "",
        reverse=True,
    )
    return legacy_rows[:limit]


@router.get("/runs")
def list_agent_runs(
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    legacy_rows = get_memory_service().list_runs(limit=limit)
    return _merge_telemetry_into_runs(legacy_rows, user_id, limit)


@router.get("/runs/{run_id}")
def get_agent_run(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    row = get_memory_service().runs.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return row


@router.get("/runs/{run_id}/events")
def get_agent_run_events(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")
    # Unwrap stored {type, payload} rows to return event payloads directly,
    # matching the SSE stream shape the frontend already expects.
    events: list[dict[str, Any]] = [
        row["payload"]
        for row in rows
        if isinstance(row, dict) and row.get("type") == "event" and isinstance(row.get("payload"), dict)
    ]
    return events if events else rows


@router.get("/runs/{run_id}/collaboration")
def get_agent_run_collaboration(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    """Return inter-agent collaboration log entries for a run.

    Primary source is the collaboration log service. If empty, fall back to
    activity events so historical runs still expose a conversation thread.
    """
    try:
        from api.services.agent.collaboration_logs import get_collaboration_service

        entries = get_collaboration_service().get_log(run_id)
        if entries:
            return entries
    except Exception:
        _logger.debug("Collaboration service unavailable for run %s", run_id, exc_info=True)

    rows = get_activity_store().load_events(run_id)
    if not rows:
        return []

    fallback_entries: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or row.get("type") != "event":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        event_type = str(payload.get("event_type") or "").strip().lower()
        if event_type not in {
            "team_chat_message",
            "agent_dialogue_turn",
        }:
            continue

        data = payload.get("data")
        data_map = data if isinstance(data, dict) else {}
        from_agent = str(
            data_map.get("from_agent")
            or data_map.get("speaker_id")
            or data_map.get("speaker_name")
            or data_map.get("source_agent")
            or payload.get("agent_id")
            or "agent"
        ).strip()
        to_agent = str(
            data_map.get("to_agent")
            or data_map.get("audience")
            or data_map.get("recipient")
            or data_map.get("target_agent")
            or data_map.get("next_agent")
            or "agent"
        ).strip()
        message = str(
            data_map.get("message")
            or data_map.get("content")
            or data_map.get("question")
            or data_map.get("answer")
            or data_map.get("reasoning")
            or data_map.get("feedback")
            or data_map.get("summary")
            or payload.get("detail")
            or payload.get("title")
            or ""
        ).strip()
        timestamp = data_map.get("timestamp") or payload.get("timestamp") or payload.get("ts")
        turn_type = str(data_map.get("turn_type") or "").strip().lower()
        turn_role = str(data_map.get("turn_role") or "").strip().lower()
        if event_type == "team_chat_message":
            entry_type = str(
                data_map.get("entry_type")
                or data_map.get("message_type")
                or "chat"
            ).strip().lower()
        elif event_type == "agent_dialogue_turn":
            if turn_role in {"request", "response", "integration", "review", "handoff", "message"}:
                entry_type = turn_role
            elif turn_type.endswith("_response") or turn_type.endswith("_answer") or turn_type == "answer":
                entry_type = "response"
            elif turn_type.endswith("_request") or turn_type.endswith("_question") or turn_type == "question":
                entry_type = "question"
            else:
                entry_type = turn_type or "message"
        else:
            entry_type = "message"

        fallback_entries.append(
            {
                "run_id": run_id,
                "from_agent": from_agent or "agent",
                "to_agent": to_agent or "agent",
                "message": message or "Agent handoff",
                "entry_type": entry_type,
                "timestamp": timestamp,
                "metadata": {
                    **data_map,
                    "turn_role": turn_role,
                    "turn_type": turn_type,
                    "interaction_label": str(data_map.get("interaction_label") or "").strip(),
                },
            }
        )

    return fallback_entries


@router.get("/runs/{run_id}/graph-snapshots")
def get_agent_run_graph_snapshots(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = get_activity_store().load_graph_snapshots(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run graph snapshots not found.")
    return rows


@router.get("/runs/{run_id}/evidence-snapshots")
def get_agent_run_evidence_snapshots(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = get_activity_store().load_evidence_snapshots(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run evidence snapshots not found.")
    return rows


@router.get("/runs/{run_id}/artifact-snapshots")
def get_agent_run_artifact_snapshots(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = get_activity_store().load_artifact_snapshots(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run artifact snapshots not found.")
    return rows


@router.get("/runs/{run_id}/work-graph-snapshots")
def get_agent_run_work_graph_snapshots(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    rows = get_activity_store().load_work_graph_snapshots(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run work-graph snapshots not found.")
    return rows


@router.get("/runs/{run_id}/replay-state")
def get_agent_run_replay_state(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")
    return get_activity_store().load_replay_state(run_id)


@router.get("/runs/{run_id}/events/{event_id}/snapshot")
def get_agent_event_snapshot(
    run_id: str,
    event_id: str,
    user_id: str = Depends(get_current_user_id),
):
    del user_id  # Current run store is user-scoped at write time; keep endpoint signature auth-guarded.

    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")

    snapshot_ref = ""
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if str(payload.get("event_id") or "") != event_id:
            continue
        snapshot_ref = str(payload.get("snapshot_ref") or "").strip()
        break

    if not snapshot_ref:
        raise HTTPException(status_code=404, detail="Snapshot not found for this event.")

    candidate = Path(snapshot_ref).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = [
        (Path.cwd() / ".maia_agent").resolve(),
        (Path.cwd() / "flow_tmp").resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Snapshot path is outside allowed directories.")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Snapshot file is missing.")

    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(
        path=str(candidate),
        media_type=media_type or "application/octet-stream",
        filename=candidate.name,
    )


@router.get("/runs/{run_id}/events/export")
def export_agent_run_events(
    run_id: str,
    _user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    store = get_activity_store()
    rows = store.load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")
    run_started = next((row.get("payload", {}) for row in rows if row.get("type") == "run_started"), {})
    run_completed = next(
        (row.get("payload", {}) for row in reversed(rows) if row.get("type") == "run_completed"),
        {},
    )
    events = [row.get("payload", {}) for row in rows if row.get("type") == "event"]
    graph_snapshots = store.load_graph_snapshots(run_id)
    evidence_snapshots = store.load_evidence_snapshots(run_id)
    artifact_snapshots = store.load_artifact_snapshots(run_id)
    work_graph_snapshots = store.load_work_graph_snapshots(run_id)
    replay_state = store.load_replay_state(run_id)
    return {
        "run_id": run_id,
        "run_started": run_started,
        "run_completed": run_completed,
        "total_rows": len(rows),
        "total_events": len(events),
        "total_graph_snapshots": len(graph_snapshots),
        "total_evidence_snapshots": len(evidence_snapshots),
        "total_artifact_snapshots": len(artifact_snapshots),
        "total_work_graph_snapshots": len(work_graph_snapshots),
        "graph_snapshots": graph_snapshots,
        "evidence_snapshots": evidence_snapshots,
        "artifact_snapshots": artifact_snapshots,
        "work_graph_snapshots": work_graph_snapshots,
        "replay_state": replay_state,
        "events": events,
    }
