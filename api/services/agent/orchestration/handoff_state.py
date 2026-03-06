from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, *, limit: int = 320) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


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
) -> dict[str, Any]:
    state = {
        "state": "paused_for_human",
        "pause_reason": _clean_text(pause_reason, limit=180) or "human_verification_required",
        "handoff_url": _clean_text(handoff_url, limit=400),
        "note": _clean_text(note, limit=420),
        "resume_token": str(uuid4()),
        "paused_at": _utc_iso_now(),
        "resumed_at": "",
        "resume_status": "awaiting_user",
    }
    settings["__handoff_state"] = state
    settings["__barrier_handoff_required"] = True
    settings["__barrier_handoff_note"] = state["note"]
    settings["__barrier_handoff_url"] = state["handoff_url"]
    settings["__barrier_handoff_reason"] = state["pause_reason"]
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
    return resume_handoff(settings=settings, resume_token=requested_token)

