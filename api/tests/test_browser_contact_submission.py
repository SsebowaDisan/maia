from __future__ import annotations

from api.services.agent.connectors.browser_contact import submission as submission_module
from api.services.agent.connectors.browser_contact.submission import (
    _detect_human_verification_barrier,
    _heuristic_submission_status,
)


def test_heuristic_submission_status_detects_submitted_when_form_disappears() -> None:
    status, confidence, reason = _heuristic_submission_status(
        before_state={
            "url": "https://example.com/contact",
            "required_empty_count": 2,
        },
        after_state={
            "url": "https://example.com/contact?ok=1",
            "required_empty_count": 0,
            "form_visible": False,
        },
    )

    assert status == "submitted"
    assert confidence >= 0.8
    assert "no longer visible" in reason.lower()


def test_heuristic_submission_status_detects_not_submitted_without_changes() -> None:
    status, confidence, reason = _heuristic_submission_status(
        before_state={
            "url": "https://example.com/contact",
            "required_empty_count": 1,
        },
        after_state={
            "url": "https://example.com/contact",
            "required_empty_count": 1,
            "form_visible": True,
        },
    )

    assert status == "not_submitted"
    assert confidence >= 0.6
    assert "no structural change" in reason.lower()


def test_detect_human_verification_barrier_from_structural_fallback(monkeypatch) -> None:
    monkeypatch.setattr(submission_module, "has_openai_credentials", lambda: False)
    required, confidence, reason, barrier_type = _detect_human_verification_barrier(
        before_state={
            "required_empty_count": 2,
            "form_visible": True,
        },
        after_state={
            "required_empty_count": 0,
            "form_visible": True,
            "enabled_controls": 3,
        },
    )

    assert required is True
    assert confidence > 0.5
    assert barrier_type == "verification_challenge"
    assert "verification" in reason.lower()


def test_detect_human_verification_barrier_prefers_llm_signal(monkeypatch) -> None:
    monkeypatch.setattr(submission_module, "has_openai_credentials", lambda: True)
    monkeypatch.setattr(
        submission_module,
        "call_json_response",
        lambda **kwargs: {
            "human_verification_required": True,
            "confidence": 0.93,
            "barrier_type": "captcha",
            "reason": "A third-party challenge gate is visible and needs user interaction.",
        },
    )

    required, confidence, reason, barrier_type = _detect_human_verification_barrier(
        before_state={"required_empty_count": 1, "form_visible": True},
        after_state={"required_empty_count": 1, "form_visible": True, "enabled_controls": 4},
    )

    assert required is True
    assert confidence >= 0.9
    assert barrier_type == "captcha"
    assert "challenge" in reason.lower()
