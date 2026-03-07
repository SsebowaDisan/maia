from __future__ import annotations

from typing import Any, Literal

from .browser_action_models import BrowserActionEvent, BrowserActionName, BrowserActionPhase
from .browser_event_contract import normalize_browser_event

_ACTION_BY_EVENT_TYPE: dict[str, BrowserActionName] = {
    "web_result_opened": "click",
    "web_search_started": "extract",
    "retrieval_query_rewrite": "extract",
    "retrieval_fused": "extract",
    "retrieval_quality_assessed": "verify",
    "api_call_started": "extract",
    "api_call_completed": "verify",
    "tool_progress": "extract",
    "tool_completed": "verify",
    "tool_failed": "verify",
    "approval_required": "verify",
    "document_opened": "navigate",
    "document_scanned": "extract",
    "highlights_detected": "extract",
    "pdf_open": "navigate",
    "pdf_page_change": "navigate",
    "pdf_scan_region": "extract",
    "pdf_evidence_linked": "verify",
    "doc_open": "navigate",
    "doc_locate_anchor": "extract",
    "doc_insert_text": "type",
    "doc_type_text": "type",
    "doc_paste_clipboard": "type",
    "doc_copy_clipboard": "extract",
    "doc_save": "verify",
    "docs.create_started": "navigate",
    "docs.create_completed": "verify",
    "docs.insert_started": "type",
    "docs.insert_completed": "verify",
    "docs.replace_started": "type",
    "docs.replace_completed": "verify",
    "drive.go_to_doc": "navigate",
    "drive.go_to_sheet": "navigate",
    "drive.share_started": "verify",
    "drive.share_completed": "verify",
    "drive.share_failed": "verify",
    "drive.search_completed": "extract",
    "sheet_open": "navigate",
    "sheet_cell_update": "type",
    "sheet_append_row": "type",
    "sheet_save": "verify",
    "sheets.create_started": "navigate",
    "sheets.create_completed": "verify",
    "sheets.append_started": "type",
    "sheets.append_completed": "verify",
    "email_open_compose": "navigate",
    "email_draft_create": "navigate",
    "email_set_to": "type",
    "email_set_subject": "type",
    "email_set_body": "type",
    "email_type_body": "type",
    "email_ready_to_send": "verify",
    "email_click_send": "click",
    "email_sent": "verify",
    "clipboard_copy": "extract",
}


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _owner_role_from_data(data: dict[str, Any]) -> str:
    for key in ("owner_role", "__owner_role", "agent_role", "role"):
        value = " ".join(str(data.get(key) or "").split()).strip().lower()
        if value:
            return value[:40]
    return "system"


def _phase_for_event_type(event_type: str) -> BrowserActionPhase:
    normalized = str(event_type or "").strip().lower()
    if normalized.endswith("_started"):
        return "start"
    if normalized.endswith("_completed"):
        return "completed"
    if normalized.endswith("_failed"):
        return "failed"
    return "active"


def _status_for_event_type(event_type: str) -> Literal["ok", "failed"]:
    normalized = str(event_type or "").strip().lower()
    return "failed" if normalized.endswith("_failed") else "ok"


def _infer_scene_surface(
    *,
    event_type: str,
    data: dict[str, Any],
    default_scene_surface: str,
) -> str:
    normalized = str(event_type or "").strip().lower()
    declared = str(data.get("scene_surface") or "").strip().lower()
    if declared:
        return declared
    default_surface = str(default_scene_surface or "system").strip().lower() or "system"
    if normalized.startswith(("browser_", "web_", "brave.", "bing.")):
        return "website"
    if normalized.startswith(("email_", "gmail_")):
        return "email"
    if normalized.startswith(("sheet_", "sheets.")):
        if default_surface in {"google_sheets"}:
            return default_surface
        return "google_sheets"
    if normalized.startswith(("doc_", "docs.")):
        if default_surface in {"google_docs", "document"}:
            return default_surface
        return "google_docs"
    if normalized.startswith("drive."):
        if default_surface in {"google_docs", "google_sheets", "document"}:
            return default_surface
        return "document"
    if normalized.startswith(("document_", "pdf_")):
        return "document"
    return default_surface


def _target_from_data(data: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = {}
    for key in (
        "url",
        "source_url",
        "target_url",
        "candidate_url",
        "selector",
        "field",
        "page_index",
        "page_total",
        "pdf_page",
        "page_label",
        "query",
        "provider",
        "source_name",
        "file_id",
    ):
        value = data.get(key)
        if value in (None, ""):
            continue
        target[key] = value
    return target


_KNOWN_ACTIONS: set[str] = {
    "navigate",
    "hover",
    "click",
    "type",
    "scroll",
    "extract",
    "verify",
    "other",
}


def _infer_action_from_event_type(event_type: str) -> BrowserActionName:
    normalized = str(event_type or "").strip().lower()
    mapped = _ACTION_BY_EVENT_TYPE.get(normalized)
    if mapped:
        return mapped
    if normalized.startswith(("brave.search.", "bing.search.", "retrieval_", "document_", "pdf_")):
        return "extract"
    if normalized.startswith(("web_", "browser_", "doc_", "docs.", "sheet_", "sheets.", "drive.")):
        if "navigate" in normalized or "open" in normalized:
            return "navigate"
        if "hover" in normalized:
            return "hover"
        if "click" in normalized:
            return "click"
        if "type" in normalized or "fill" in normalized or "insert" in normalized or "append" in normalized:
            return "type"
        if "scroll" in normalized:
            return "scroll"
        if "verify" in normalized or "confirm" in normalized or normalized.endswith("_saved"):
            return "verify"
        return "extract"
    if normalized.startswith(("email_", "gmail_")):
        if "click_send" in normalized:
            return "click"
        if "sent" in normalized or "ready_to_send" in normalized:
            return "verify"
        if "set_" in normalized or "type" in normalized:
            return "type"
        return "navigate"
    return "other"


def normalize_interaction_event(
    event: dict[str, Any],
    *,
    default_scene_surface: str = "system",
) -> dict[str, Any]:
    payload = dict(event or {})
    event_type = str(payload.get("event_type") or "").strip() or "tool_progress"
    if event_type.startswith("browser_"):
        browser_default_surface = str(default_scene_surface or "").strip().lower() or "website"
        if browser_default_surface in {"", "system"}:
            browser_default_surface = "website"
        return normalize_browser_event(
            payload,
            default_scene_surface=browser_default_surface,
        )

    existing_data = payload.get("data")
    data = dict(existing_data) if isinstance(existing_data, dict) else {}
    declared_action = str(data.get("action") or "").strip().lower()
    action = (
        declared_action
        if declared_action in _KNOWN_ACTIONS
        else _infer_action_from_event_type(event_type)
    )
    snapshot_ref = str(payload.get("snapshot_ref") or "").strip()
    event_model = BrowserActionEvent(
        event_type=event_type,
        action=action,
        phase=_phase_for_event_type(event_type),
        status=_status_for_event_type(event_type),
        scene_surface=_infer_scene_surface(
            event_type=event_type,
            data=data,
            default_scene_surface=default_scene_surface,
        ),
        owner_role=_owner_role_from_data(data),
        cursor_x=_as_float(data.get("cursor_x")),
        cursor_y=_as_float(data.get("cursor_y")),
        scroll_direction=str(data.get("scroll_direction") or "").strip().lower(),
        scroll_percent=_as_float(data.get("scroll_percent")),
        target=_target_from_data(data),
        metadata={
            "event_type": event_type,
            "elapsed_ms": data.get("elapsed_ms"),
            "snapshot_ref": snapshot_ref or None,
            "contract_source": "interaction_event_contract_v1",
        },
    )
    normalized_data = dict(data)
    normalized_data.update(event_model.to_data())
    payload["event_type"] = event_type
    payload["data"] = normalized_data
    payload.setdefault("title", "Interaction activity")
    payload.setdefault("detail", "")
    if snapshot_ref:
        payload["snapshot_ref"] = snapshot_ref
    elif "snapshot_ref" in payload:
        payload["snapshot_ref"] = None
    return payload
