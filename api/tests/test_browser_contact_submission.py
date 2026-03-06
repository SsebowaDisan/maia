from __future__ import annotations

from api.services.agent.connectors.browser_contact.submission import _heuristic_submission_status


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

