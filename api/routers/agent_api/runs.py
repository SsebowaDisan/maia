from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.auth import get_current_user_id
from api.services.agent.activity import get_activity_store
from api.services.agent.memory import get_memory_service

router = APIRouter(tags=["agent"])


@router.get("/runs")
def list_agent_runs(
    limit: int = 50,
    _user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    return get_memory_service().list_runs(limit=limit)


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
