from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return _clean_text(value).lower()


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _read_side(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = _clean_text(data.get(key))
        if text:
            return text
    return ""


def apply_compare_contract(*, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data or {})
    normalized_event = _normalized_text(event_type)
    compare_mode_raw = payload.get("compare_mode")
    compare_mode = dict(compare_mode_raw) if isinstance(compare_mode_raw, dict) else {}
    left = _read_side(payload, "compare_left", "compare_region_a", "compare_a")
    if not left:
        left = _read_side(compare_mode, "left", "region_a")
    right = _read_side(payload, "compare_right", "compare_region_b", "compare_b")
    if not right:
        right = _read_side(compare_mode, "right", "region_b")
    enabled = bool(left and right) or "compare" in normalized_event
    if not enabled:
        return payload

    verdict = _clean_text(payload.get("compare_verdict") or compare_mode.get("verdict"))
    confidence = _as_float(payload.get("compare_confidence"))
    if confidence is None:
        confidence = _as_float(compare_mode.get("confidence"))
    if confidence is not None:
        confidence = max(0.0, min(1.0, round(float(confidence), 3)))

    mode_payload = {
        "surface": _clean_text(payload.get("scene_surface") or compare_mode.get("surface")),
        "left": left,
        "right": right,
        "verdict": verdict,
        "confidence": confidence,
    }
    mode_payload = {
        key: value
        for key, value in mode_payload.items()
        if value not in (None, "", [])
    }
    if left:
        payload["compare_left"] = left
    if right:
        payload["compare_right"] = right
    if verdict:
        payload["compare_verdict"] = verdict
    if confidence is not None:
        payload["compare_confidence"] = confidence
    payload["compare_mode_enabled"] = True
    if mode_payload:
        payload["compare_mode"] = mode_payload
    return payload


__all__ = ["apply_compare_contract"]
