from __future__ import annotations

from typing import Any

ZOOM_POLICY_VERSION = "zoom_policy_v1"
_ZOOM_ACTIONS = {"zoom_in", "zoom_out", "zoom_reset", "zoom_to_region"}


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _clamp01(value: Any) -> float | None:
    parsed = _as_float(value)
    if parsed is None:
        return None
    return max(0.0, min(1.0, parsed))


def _target_region_small(data: dict[str, Any]) -> bool:
    width = _clamp01(data.get("region_width"))
    if width is None:
        width = _clamp01(data.get("target_region_width"))
    if width is None:
        region = data.get("target_region")
        if isinstance(region, dict):
            width = _clamp01(region.get("width"))
    height = _clamp01(data.get("region_height"))
    if height is None:
        height = _clamp01(data.get("target_region_height"))
    if height is None:
        region = data.get("target_region")
        if isinstance(region, dict):
            height = _clamp01(region.get("height"))
    if width is None or height is None:
        return False
    area = float(width * height)
    return area <= 0.08 or min(width, height) <= 0.22


def _text_density_high(data: dict[str, Any]) -> bool:
    for key in ("text_density", "content_density", "page_text_density"):
        value = _clamp01(data.get(key))
        if value is not None and value >= 0.74:
            return True
    return False


def _confidence_low(data: dict[str, Any]) -> bool:
    for key in ("confidence", "verification_confidence", "support_ratio", "citation_support_ratio"):
        value = _clamp01(data.get(key))
        if value is not None and value <= 0.58:
            return True
    return False


def _verifier_requested(data: dict[str, Any]) -> bool:
    return _as_bool(data.get("verifier_requested")) or _as_bool(data.get("verifier_escalation"))


def _user_detail_requested(data: dict[str, Any]) -> bool:
    return _as_bool(data.get("user_detail_requested")) or _as_bool(data.get("detail_intent_requested"))


def _is_zoom_event(event_type: str, action: str) -> bool:
    normalized_event = str(event_type or "").strip().lower()
    normalized_action = str(action or "").strip().lower()
    if normalized_action in _ZOOM_ACTIONS:
        return True
    return (
        normalized_event.startswith(("browser_zoom_", "pdf_zoom_", "sheet_zoom_"))
        or ".zoom_" in normalized_event
    )


def _reason_from_triggers(triggers: list[str]) -> str:
    if not triggers:
        return ""
    labels: list[str] = []
    for trigger in triggers:
        if trigger == "text_density_high":
            labels.append("high text density")
        elif trigger == "target_region_small":
            labels.append("small target region")
        elif trigger == "confidence_low":
            labels.append("low confidence")
        elif trigger == "verifier_escalation":
            labels.append("verifier escalation")
        elif trigger == "user_detail_intent":
            labels.append("user detail intent")
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def apply_zoom_policy(
    *,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(data or {})
    triggers: list[str] = []
    if _text_density_high(payload):
        triggers.append("text_density_high")
    if _target_region_small(payload):
        triggers.append("target_region_small")
    if _confidence_low(payload):
        triggers.append("confidence_low")
    if _verifier_requested(payload):
        triggers.append("verifier_escalation")
    if _user_detail_requested(payload):
        triggers.append("user_detail_intent")

    zoom_event = _is_zoom_event(event_type, str(payload.get("action") or ""))
    existing_reason = " ".join(str(payload.get("zoom_reason") or "").split()).strip()
    if zoom_event:
        payload["zoom_policy_triggered"] = bool(triggers)
        payload["zoom_policy_recommended"] = False
    else:
        payload["zoom_policy_recommended"] = bool(triggers)
        payload["zoom_policy_triggered"] = False
    if triggers:
        payload["zoom_policy_triggers"] = triggers
    if zoom_event and not existing_reason:
        inferred_reason = _reason_from_triggers(triggers)
        if inferred_reason:
            payload["zoom_reason"] = inferred_reason

    zoom_level = _as_float(payload.get("zoom_level"))
    if zoom_level is None:
        zoom_level = _as_float(payload.get("zoom_to"))
    if zoom_level is not None and zoom_level > 0:
        payload["zoom_level"] = round(float(zoom_level), 3)

    payload["zoom_policy_version"] = ZOOM_POLICY_VERSION
    return payload


__all__ = ["ZOOM_POLICY_VERSION", "apply_zoom_policy"]
