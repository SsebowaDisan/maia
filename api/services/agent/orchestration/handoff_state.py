from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from api.services.agent.policy import (
    BARRIER_TYPE_HUMAN_VERIFICATION,
    normalize_barrier_type,
)


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, *, limit: int = 320) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def _clean_dict(value: Any, *, key_limit: int = 40, value_limit: int = 320) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _clean_text(raw_key, limit=key_limit).lower()
        if not key:
            continue
        text = _clean_text(raw_value, limit=value_limit)
        if not text:
            continue
        cleaned[key] = text
        if len(cleaned) >= 24:
            break
    return cleaned


def read_handoff_state(*, settings: dict[str, Any]) -> dict[str, Any]:
    raw = settings.get("__handoff_state")
    if not isinstance(raw, dict):
        return {}
    state = dict(raw)
    state["state"] = _clean_text(state.get("state"), limit=48).lower() or "running"
    state["pause_reason"] = _clean_text(state.get("pause_reason"), limit=180)
    state["handoff_url"] = _clean_text(state.get("handoff_url"), limit=400)
    state["note"] = _clean_text(state.get("note"), limit=420)
    state["resume_token"] = _clean_text(state.get("resume_token"), limit=80)
    state["paused_at"] = _clean_text(state.get("paused_at"), limit=64)
    state["resumed_at"] = _clean_text(state.get("resumed_at"), limit=64)
    state["resume_status"] = _clean_text(state.get("resume_status"), limit=48).lower()
    state["barrier_type"] = normalize_barrier_type(
        state.get("barrier_type"),
        default=BARRIER_TYPE_HUMAN_VERIFICATION,
    )
    state["barrier_scope"] = _clean_text(state.get("barrier_scope"), limit=120)
    state["requires_post_resume_verification"] = bool(
        state.get("requires_post_resume_verification", True)
    )
    state["verification_context"] = _clean_dict(state.get("verification_context"))
    return state


def is_handoff_paused(*, settings: dict[str, Any]) -> bool:
    state = read_handoff_state(settings=settings)
    return str(state.get("state") or "").strip().lower() == "paused_for_human"


def pause_for_handoff(
    *,
    settings: dict[str, Any],
    pause_reason: str,
    handoff_url: str,
    note: str,
    barrier_type: str = BARRIER_TYPE_HUMAN_VERIFICATION,
    barrier_scope: str = "",
    verification_context: dict[str, Any] | None = None,
    requires_post_resume_verification: bool = True,
) -> dict[str, Any]:
    normalized_barrier_type = normalize_barrier_type(
        barrier_type,
        default=BARRIER_TYPE_HUMAN_VERIFICATION,
    )
    state = {
        "state": "paused_for_human",
        "pause_reason": _clean_text(pause_reason, limit=180) or "human_verification_required",
        "handoff_url": _clean_text(handoff_url, limit=400),
        "note": _clean_text(note, limit=420),
        "resume_token": str(uuid4()),
        "paused_at": _utc_iso_now(),
        "resumed_at": "",
        "resume_status": "awaiting_user",
        "barrier_type": normalized_barrier_type,
        "barrier_scope": _clean_text(barrier_scope, limit=120),
        "requires_post_resume_verification": bool(requires_post_resume_verification),
        "verification_context": _clean_dict(verification_context or {}),
    }
    settings["__handoff_state"] = state
    settings["__barrier_handoff_required"] = True
    settings["__barrier_handoff_note"] = state["note"]
    settings["__barrier_handoff_url"] = state["handoff_url"]
    settings["__barrier_handoff_reason"] = state["pause_reason"]
    settings["__barrier_type"] = state["barrier_type"]
    settings["__barrier_scope"] = state["barrier_scope"]
    settings["__barrier_resume_pending_verification"] = bool(
        state["requires_post_resume_verification"]
    )
    settings["__barrier_handoff_verification_context"] = state["verification_context"]
    return state


def resume_handoff(
    *,
    settings: dict[str, Any],
    resume_token: str = "",
) -> dict[str, Any] | None:
    state = read_handoff_state(settings=settings)
    if not state:
        return None
    if str(state.get("state") or "").strip().lower() != "paused_for_human":
        return state
    current_token = _clean_text(state.get("resume_token"), limit=80)
    requested_token = _clean_text(resume_token, limit=80)
    if requested_token and current_token and requested_token != current_token:
        return None
    next_state = {
        **state,
        "state": "resumed",
        "resume_status": "user_completed",
        "resumed_at": _utc_iso_now(),
    }
    settings["__handoff_state"] = next_state
    settings["__barrier_handoff_required"] = False
    settings["__barrier_resume_pending_verification"] = bool(
        next_state.get("requires_post_resume_verification", True)
    )
    return next_state


def maybe_resume_handoff_from_settings(*, settings: dict[str, Any]) -> dict[str, Any] | None:
    requested_token = _clean_text(
        settings.get("__handoff_resume_token") or settings.get("agent.handoff_resume_token"),
        limit=80,
    )
    requested_flag = bool(
        settings.get("__handoff_resume_requested")
        or settings.get("agent.handoff_resume_requested")
    )
    if not requested_token and not requested_flag:
        return None
    settings["__handoff_resume_requested_at"] = _utc_iso_now()
    return resume_handoff(settings=settings, resume_token=requested_token)


def handoff_pause_notice(*, settings: dict[str, Any]) -> dict[str, Any]:
    state = read_handoff_state(settings=settings)
    pause_note = _clean_text(state.get("note"), limit=240)
    pause_reason = _clean_text(state.get("pause_reason"), limit=140)
    barrier_type = normalize_barrier_type(state.get("barrier_type"))
    detail = pause_note or pause_reason or "Human verification is required before execution can continue."
    return {
        "event_type": "handoff_paused",
        "title": "Execution paused for human verification",
        "detail": detail,
        "metadata": {
            "handoff_state": state,
            "pause_reason": pause_reason,
            "barrier_type": barrier_type,
            "barrier_scope": _clean_text(state.get("barrier_scope"), limit=120),
            "requires_post_resume_verification": bool(
                state.get("requires_post_resume_verification", True)
            ),
            "verification_context": _clean_dict(state.get("verification_context")),
        },
    }


def handoff_resume_notice(*, resumed_handoff: dict[str, Any]) -> dict[str, Any]:
    state = read_handoff_state(settings={"__handoff_state": resumed_handoff})
    return {
        "event_type": "handoff_resumed",
        "title": "Resumed after human verification",
        "detail": "Human handoff marked complete. Continuing autonomous execution.",
        "metadata": {
            "handoff_state": str(state.get("state") or ""),
            "resume_status": str(state.get("resume_status") or ""),
            "barrier_type": str(state.get("barrier_type") or ""),
            "requires_post_resume_verification": bool(
                state.get("requires_post_resume_verification", True)
            ),
            "verification_context": _clean_dict(state.get("verification_context")),
        },
    }
