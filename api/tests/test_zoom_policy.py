from __future__ import annotations

from api.services.agent.execution.zoom_policy import apply_zoom_policy


def test_apply_zoom_policy_triggers_zoom_reason_for_zoom_event() -> None:
    payload = apply_zoom_policy(
        event_type="pdf_zoom_to_region",
        data={
            "action": "zoom_to_region",
            "content_density": 0.86,
            "confidence": 0.44,
            "target_region": {"x": 0.1, "y": 0.2, "width": 0.15, "height": 0.09},
        },
    )
    assert payload["zoom_policy_triggered"] is True
    assert payload["zoom_policy_recommended"] is False
    assert "text_density_high" in payload["zoom_policy_triggers"]
    assert "confidence_low" in payload["zoom_policy_triggers"]
    assert "target_region_small" in payload["zoom_policy_triggers"]
    assert isinstance(payload.get("zoom_reason"), str) and payload.get("zoom_reason")


def test_apply_zoom_policy_recommends_zoom_for_non_zoom_event() -> None:
    payload = apply_zoom_policy(
        event_type="browser_extract",
        data={
            "action": "extract",
            "verification_confidence": 0.41,
            "verifier_requested": True,
        },
    )
    assert payload["zoom_policy_triggered"] is False
    assert payload["zoom_policy_recommended"] is True
    assert "confidence_low" in payload["zoom_policy_triggers"]
    assert "verifier_escalation" in payload["zoom_policy_triggers"]
