from __future__ import annotations

from api.services.agent.orchestration.handoff_state import (
    is_handoff_paused,
    pause_for_handoff,
    read_handoff_state,
    resume_handoff,
)


def test_pause_for_handoff_sets_paused_state() -> None:
    settings: dict[str, object] = {}
    state = pause_for_handoff(
        settings=settings,  # type: ignore[arg-type]
        pause_reason="captcha",
        handoff_url="https://example.com",
        note="Complete human verification.",
    )
    assert state.get("state") == "paused_for_human"
    assert is_handoff_paused(settings=settings) is True
    assert settings.get("__barrier_handoff_required") is True
    assert isinstance(state.get("resume_token"), str) and state.get("resume_token")


def test_resume_handoff_clears_pause() -> None:
    settings: dict[str, object] = {}
    paused = pause_for_handoff(
        settings=settings,  # type: ignore[arg-type]
        pause_reason="captcha",
        handoff_url="https://example.com",
        note="Complete human verification.",
    )
    token = str(paused.get("resume_token") or "")
    resumed = resume_handoff(settings=settings, resume_token=token)  # type: ignore[arg-type]
    assert isinstance(resumed, dict)
    assert resumed.get("state") == "resumed"
    assert is_handoff_paused(settings=settings) is False
    read_back = read_handoff_state(settings=settings)  # type: ignore[arg-type]
    assert read_back.get("resume_status") == "user_completed"

