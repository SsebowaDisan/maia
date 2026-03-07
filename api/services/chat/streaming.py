from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any

from api.services.agent.event_envelope import build_event_envelope, merge_event_envelope_data
from api.services.agent.events import EVENT_SCHEMA_VERSION, infer_stage, infer_status
from api.services.agent.llm_execution_support import summarize_conversation_window
from api.services.agent.zoom_history import enrich_event_data_with_zoom


def make_activity_stream_event(
    *,
    run_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    metadata: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    seq: int = 0,
    stage: str | None = None,
    status: str | None = None,
    snapshot_ref: str | None = None,
) -> dict[str, Any]:
    payload_data = dict(data or {})
    if metadata:
        payload_data.update(metadata)
    resolved_stage = stage or infer_stage(event_type)
    resolved_status = status or infer_status(event_type)
    envelope = build_event_envelope(
        event_type=event_type,
        stage=resolved_stage,
        status=resolved_status,
        data=payload_data,
    )
    payload_data = merge_event_envelope_data(
        data=payload_data,
        envelope=envelope,
        event_schema_version=EVENT_SCHEMA_VERSION,
    )
    event_index = max(0, int(seq))
    if event_index > 0:
        payload_data["event_index"] = event_index
    replay_importance = str(payload_data.get("event_replay_importance") or "normal").strip() or "normal"
    payload_data["replay_importance"] = replay_importance
    timeline = payload_data.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}
    timeline.setdefault("event_index", payload_data.get("event_index") or None)
    timeline.setdefault("replay_importance", replay_importance)
    timeline.setdefault("graph_node_id", payload_data.get("graph_node_id"))
    timeline.setdefault("scene_ref", payload_data.get("scene_ref"))
    payload_data["timeline"] = timeline
    ts = datetime.now(timezone.utc).isoformat()
    event_id = f"evt_stream_{uuid.uuid4().hex}"
    payload_data = enrich_event_data_with_zoom(
        data=payload_data,
        event_type=event_type,
        event_id=event_id,
        event_index=event_index,
        timestamp=ts,
        graph_node_id=str(payload_data.get("graph_node_id") or "").strip(),
        scene_ref=str(payload_data.get("scene_ref") or "").strip(),
    )
    return {
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "run_id": run_id,
        "seq": event_index,
        "ts": ts,
        "type": event_type,
        "stage": resolved_stage,
        "status": resolved_status,
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "timestamp": ts,
        "data": payload_data,
        "snapshot_ref": snapshot_ref,
        "metadata": payload_data,
        "event_family": payload_data.get("event_family"),
        "event_priority": payload_data.get("event_priority"),
        "event_render_mode": payload_data.get("event_render_mode"),
        "event_replay_importance": payload_data.get("event_replay_importance"),
        "replay_importance": replay_importance,
        "event_index": payload_data.get("event_index"),
        "graph_node_id": payload_data.get("graph_node_id"),
        "scene_ref": payload_data.get("scene_ref"),
    }


def chunk_text_for_stream(text: str, chunk_size: int = 220) -> list[str]:
    if not text:
        return []
    size = max(32, int(chunk_size or 220))
    return [text[idx : idx + size] for idx in range(0, len(text), size)]


def build_agent_context_window(
    *,
    chat_history: list[list[str]],
    latest_message: str,
    agent_goal: str | None,
    max_turns: int = 6,
) -> tuple[list[str], str]:
    recent_rows = list(chat_history or [])[-max(1, int(max_turns)) :]
    turns: list[dict[str, str]] = []
    snippets: list[str] = []
    for row in recent_rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        user_text = " ".join(str(row[0] or "").split()).strip()
        assistant_text = " ".join(str(row[1] or "").split()).strip()
        if user_text:
            snippets.append(f"User: {user_text[:260]}")
        if assistant_text:
            snippets.append(f"Assistant: {assistant_text[:320]}")
        turns.append({"user": user_text, "assistant": assistant_text})
    summary = summarize_conversation_window(
        latest_user_message=f"{latest_message} {agent_goal or ''}".strip(),
        turns=turns,
    )
    return snippets[-10:], summary
