from __future__ import annotations

from typing import Any, Literal

from api.services.agent.event_envelope import build_event_envelope, merge_event_envelope_data
from api.services.agent.events import infer_stage, infer_status

from .browser_action_models import BrowserActionEvent, BrowserActionName, BrowserActionPhase
from .compare_contract import apply_compare_contract
from .semantic_find import apply_semantic_find
from .verifier_conflict import apply_verifier_conflict_policy
from .zoom_policy import apply_zoom_policy

_ACTION_BY_EVENT_TYPE: dict[str, BrowserActionName] = {
    "browser_open": "navigate",
    "browser_navigate": "navigate",
    "browser_hover": "hover",
    "browser_click": "click",
    "browser_type": "type",
    "browser_scroll": "scroll",
    "browser_extract": "extract",
    "browser_verify": "verify",
    "browser_keyword_highlight": "extract",
    "browser_copy_selection": "extract",
    "browser_find_in_page": "extract",
    "browser_cookie_accept": "verify",
    "browser_cookie_check": "verify",
    "browser_contact_fill": "type",
    "browser_contact_fill_name": "type",
    "browser_contact_fill_email": "type",
    "browser_contact_fill_company": "type",
    "browser_contact_fill_phone": "type",
    "browser_contact_fill_subject": "type",
    "browser_contact_fill_message": "type",
    "browser_contact_llm_fill": "type",
    "browser_contact_submit": "click",
    "browser_contact_confirmation": "verify",
    "browser_contact_human_verification_required": "verify",
    "browser_contact_form_detected": "extract",
    "browser_contact_required_scan": "extract",
    "browser_interaction_started": "verify",
    "browser_interaction_completed": "verify",
    "browser_interaction_failed": "verify",
    "browser_human_verification_required": "verify",
    "browser_zoom_in": "zoom_in",
    "browser_zoom_out": "zoom_out",
    "browser_zoom_reset": "zoom_reset",
    "browser_zoom_to_region": "zoom_to_region",
    "browser.zoom_in": "zoom_in",
    "browser.zoom_out": "zoom_out",
    "browser.zoom_reset": "zoom_reset",
    "browser.zoom_to_region": "zoom_to_region",
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
    return "browser"


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
    return "failed" if str(event_type or "").strip().lower().endswith("_failed") else "ok"


def _target_from_data(data: dict[str, Any]) -> dict[str, Any]:
    target: dict[str, Any] = {}
    for key in (
        "url",
        "source_url",
        "candidate_url",
        "title",
        "selector",
        "target_url",
        "field",
        "field_label",
        "mapped_intent",
        "contact_status",
        "page_index",
        "page_total",
        "query",
        "provider",
        "zoom_level",
        "zoom_from",
        "zoom_to",
        "zoom_reason",
        "target_region",
        "region_x",
        "region_y",
        "region_width",
        "region_height",
    ):
        value = data.get(key)
        if value in (None, ""):
            continue
        target[key] = value
    return target


def _infer_action(event_type: str) -> BrowserActionName:
    normalized = str(event_type or "").strip().lower()
    mapped = _ACTION_BY_EVENT_TYPE.get(normalized)
    if mapped:
        return mapped
    if not normalized.startswith(("browser_", "browser.")):
        return "other"
    if "navigate" in normalized or "open" in normalized:
        return "navigate"
    if "hover" in normalized:
        return "hover"
    if "click" in normalized:
        return "click"
    if "type" in normalized or "fill" in normalized:
        return "type"
    if "scroll" in normalized:
        return "scroll"
    if "zoom_to_region" in normalized:
        return "zoom_to_region"
    if "zoom_in" in normalized:
        return "zoom_in"
    if "zoom_out" in normalized:
        return "zoom_out"
    if "zoom_reset" in normalized:
        return "zoom_reset"
    if "extract" in normalized or "highlight" in normalized or "copy" in normalized or "find" in normalized:
        return "extract"
    if "verify" in normalized or "confirm" in normalized:
        return "verify"
    return "verify"


def normalize_browser_event(
    event: dict[str, Any],
    *,
    default_scene_surface: str = "website",
) -> dict[str, Any]:
    payload = dict(event or {})
    event_type = str(payload.get("event_type") or "").strip() or "browser_progress"
    existing_data = payload.get("data")
    data = dict(existing_data) if isinstance(existing_data, dict) else {}
    normalized_event_type = event_type.strip().lower()
    action = _infer_action(normalized_event_type)
    snapshot_ref = str(payload.get("snapshot_ref") or "").strip()
    event_model = BrowserActionEvent(
        event_type=event_type,
        action=action,
        phase=_phase_for_event_type(event_type),
        status=_status_for_event_type(event_type),
        scene_surface=str(data.get("scene_surface") or default_scene_surface or "website").strip().lower(),
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
            "contract_source": "browser_event_contract_v1",
        },
    )
    normalized_data = dict(data)
    normalized_data.update(event_model.to_data())
    normalized_data = apply_verifier_conflict_policy(
        event_type=event_type,
        data=normalized_data,
    )
    normalized_data = apply_zoom_policy(
        event_type=event_type,
        data=normalized_data,
    )
    normalized_data = apply_semantic_find(
        event_type=event_type,
        data=normalized_data,
    )
    normalized_data = apply_compare_contract(
        event_type=event_type,
        data=normalized_data,
    )
    envelope = build_event_envelope(
        event_type=event_type,
        stage=infer_stage(event_type),
        status=infer_status(event_type),
        data=normalized_data,
    )
    normalized_data = merge_event_envelope_data(
        data=normalized_data,
        envelope=envelope,
        event_schema_version="interaction_v2",
    )
    payload["event_type"] = event_type
    payload["data"] = normalized_data
    payload.setdefault("title", "Browser activity")
    payload.setdefault("detail", "")
    if snapshot_ref:
        payload["snapshot_ref"] = snapshot_ref
    elif "snapshot_ref" in payload:
        payload["snapshot_ref"] = None
    return payload
