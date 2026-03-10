from __future__ import annotations

from datetime import datetime, timezone
import os
import uuid
from typing import Any

from api.services.agent.event_envelope import build_event_envelope, merge_event_envelope_data
from api.services.agent.events import EVENT_SCHEMA_VERSION, infer_stage, infer_status
from api.services.agent.llm_execution_support import summarize_conversation_window
from api.services.agent.zoom_history import enrich_event_data_with_zoom

STAGED_THEATRE_ENABLED = (
    str(os.getenv("MAIA_STAGED_THEATRE_ENABLED", "1")).strip().lower() not in {"0", "false", "no"}
)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _first_http_url(*candidates: Any) -> str:
    for item in candidates:
        value = _clean_text(item)
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def _infer_ui_stage(*, event_type: str, stage: str, payload_data: dict[str, Any]) -> str:
    explicit = _clean_text(payload_data.get("ui_stage"))
    if explicit:
        return explicit
    if event_type == "response_written":
        return "done"
    if event_type == "approval_required":
        return "confirm"
    if event_type == "policy_blocked":
        return "blocked"
    normalized_event = _clean_text(event_type).lower()
    if stage in {"understanding", "contract", "clarification"}:
        return "understand"
    if stage == "planning":
        return "breakdown"
    if stage == "execution":
        return "execute"
    if stage == "verification":
        return "review"
    if stage == "delivery":
        return "confirm"
    if normalized_event.startswith(("task_understanding_", "llm.intent_", "llm.task_")):
        return "understand"
    if normalized_event.startswith(("plan_", "planning_", "llm.plan_")):
        return "breakdown"
    if normalized_event.startswith(
        (
            "tool_",
            "web_",
            "browser_",
            "browser.",
            "document_",
            "pdf_",
            "doc_",
            "docs.",
            "sheet_",
            "sheets.",
            "drive.",
            "email_",
            "email.",
            "gmail_",
            "gmail.",
            "api_",
            "api.",
        )
    ):
        return "execute"
    return "idle"


def _infer_ui_target(payload_data: dict[str, Any]) -> str:
    explicit = _clean_text(payload_data.get("ui_target"))
    if explicit:
        return explicit
    surface = _clean_text(payload_data.get("scene_surface")).lower()
    if surface in {"website", "browser", "web"}:
        return "browser"
    if surface in {"document", "google_docs", "google_sheets", "docs", "sheets"}:
        return "document"
    if surface in {"email", "gmail"}:
        return "email"
    return "system"


def _infer_ui_commit(*, event_type: str, payload_data: dict[str, Any], ui_target: str) -> dict[str, Any] | None:
    explicit = payload_data.get("ui_commit")
    if isinstance(explicit, dict):
        return explicit
    url = _first_http_url(
        payload_data.get("url"),
        payload_data.get("source_url"),
        payload_data.get("target_url"),
        payload_data.get("page_url"),
        payload_data.get("final_url"),
        payload_data.get("link"),
        payload_data.get("document_url"),
        payload_data.get("spreadsheet_url"),
    )
    normalized_type = _clean_text(event_type).lower()
    if ui_target == "browser" and url:
        return {"surface": "browser", "commit": "navigate", "url": url}
    if ui_target == "document" and url:
        commit = "open_sheet" if "spreadsheets" in url else "open_document"
        return {"surface": "document", "commit": commit, "url": url}
    if ui_target == "email" and (
        normalized_type.startswith("email_")
        or normalized_type.startswith("email.")
        or normalized_type.startswith("gmail_")
        or normalized_type.startswith("gmail.")
    ):
        return {"surface": "email", "commit": normalized_type}
    if ui_target == "system":
        family = _clean_text(payload_data.get("event_family")).lower()
        if family == "api" or normalized_type.startswith(("api_", "api.")):
            return {"surface": "api", "commit": normalized_type or "api_event"}
    return None


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
    if STAGED_THEATRE_ENABLED:
        payload_data.setdefault(
            "ui_stage",
            _infer_ui_stage(event_type=event_type, stage=resolved_stage, payload_data=payload_data),
        )
        ui_target = _infer_ui_target(payload_data)
        payload_data.setdefault("ui_target", ui_target)
        ui_commit = _infer_ui_commit(event_type=event_type, payload_data=payload_data, ui_target=ui_target)
        if ui_commit:
            payload_data["ui_commit"] = ui_commit
        payload_data.setdefault("ui_contract_version", "v1")
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
