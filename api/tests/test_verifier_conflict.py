from __future__ import annotations

from api.services.agent.execution.verifier_conflict import apply_verifier_conflict_policy


def test_apply_verifier_conflict_policy_triggers_on_low_support() -> None:
    payload = apply_verifier_conflict_policy(
        event_type="verification_check",
        data={
            "action": "verify",
            "citation_support_ratio": 0.42,
            "citation_support_threshold": 0.6,
        },
    )
    assert payload["verifier_conflict"] is True
    assert payload["verifier_recheck_required"] is True
    assert payload["zoom_escalation_requested"] is True
    assert isinstance(payload.get("verifier_conflict_reason"), str) and payload.get(
        "verifier_conflict_reason"
    )


def test_apply_verifier_conflict_policy_respects_explicit_conflict_flag() -> None:
    payload = apply_verifier_conflict_policy(
        event_type="tool_progress",
        data={
            "action": "extract",
            "conflict_detected": True,
            "reason": "source statements conflict",
        },
    )
    assert payload["verifier_conflict"] is True
    assert payload["verifier_conflict_reason"] == "source statements conflict"
