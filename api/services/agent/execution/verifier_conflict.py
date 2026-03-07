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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value) in {"1", "true", "yes", "on"}


def apply_verifier_conflict_policy(
    *,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(data or {})
    normalized_event = _normalized_text(event_type)
    action = _normalized_text(payload.get("action"))
    explicit_conflict = (
        _as_bool(payload.get("verifier_conflict"))
        or _as_bool(payload.get("conflict_detected"))
        or _as_bool(payload.get("contradiction_detected"))
    )

    support_ratio = _as_float(payload.get("citation_support_ratio"))
    if support_ratio is None:
        support_ratio = _as_float(payload.get("support_ratio"))
    support_threshold = _as_float(payload.get("citation_support_threshold"))
    if support_threshold is None:
        support_threshold = 0.6
    low_support = support_ratio is not None and support_ratio < float(support_threshold)

    confidence = _as_float(payload.get("verification_confidence"))
    if confidence is None:
        confidence = _as_float(payload.get("confidence"))
    low_confidence = confidence is not None and confidence <= 0.55

    verify_phase = action == "verify" or normalized_event.startswith(("verification_", "verify_"))
    conflict = explicit_conflict or (verify_phase and (low_support or low_confidence))
    if not conflict:
        return payload

    reason = (
        _clean_text(payload.get("verifier_conflict_reason"))
        or _clean_text(payload.get("blocked_reason"))
        or _clean_text(payload.get("reason"))
    )
    if not reason:
        if low_support and low_confidence:
            reason = "low citation support and low confidence"
        elif low_support:
            reason = "citation support below threshold"
        elif low_confidence:
            reason = "verification confidence below threshold"
        else:
            reason = "verifier detected conflicting evidence"

    payload["verifier_conflict"] = True
    payload["verifier_conflict_reason"] = reason
    payload["verifier_recheck_required"] = True
    payload["verifier_escalation"] = True
    payload["zoom_escalation_requested"] = True
    return payload


__all__ = ["apply_verifier_conflict_policy"]
