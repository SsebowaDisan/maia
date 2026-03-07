from __future__ import annotations

from api.services.agent.connectors.browser_goal import capability


def test_goal_page_capability_disabled_when_flag_is_off() -> None:
    decision = capability.resolve_goal_page_discovery_capability(
        settings={"agent.capabilities.goal_page_discovery_enabled": False}
    )

    assert decision["enabled"] is False
    assert decision["source"] == "flag"
    assert decision["reason"] == "Capability flag disabled."


def test_goal_page_capability_uses_llm_when_available(monkeypatch) -> None:
    monkeypatch.setattr(capability, "has_openai_credentials", lambda: True)
    monkeypatch.setattr(
        capability,
        "call_json_response",
        lambda **_: {
            "enable_capability": True,
            "confidence": 0.89,
            "reason": "Contract and role plan indicate reusable goal-page navigation.",
        },
    )
    decision = capability.resolve_goal_page_discovery_capability(
        settings={
            "agent.capabilities.goal_page_discovery_enabled": True,
            "__intent_tags": ["goal_page_navigation"],
        }
    )

    assert decision["enabled"] is True
    assert decision["source"] == "llm"
    assert decision["confidence"] == 0.89
    assert decision["signals"]["intent_tags"] == ["goal_page_navigation"]


def test_goal_page_capability_fallback_enables_for_contact_execution_path(monkeypatch) -> None:
    monkeypatch.setattr(capability, "has_openai_credentials", lambda: False)
    decision = capability.resolve_goal_page_discovery_capability(
        settings={
            "agent.capabilities.goal_page_discovery_enabled": True,
            "__intent_tags": ["web_research"],
            "__task_contract": {"required_actions": ["submit_contact_form"]},
            "__capability_required_domains": ["outreach"],
        }
    )

    assert decision["enabled"] is True
    assert decision["source"] == "fallback"
    assert "Structured task signals" in str(decision["reason"])


def test_goal_page_capability_fallback_stays_disabled_without_signals(monkeypatch) -> None:
    monkeypatch.setattr(capability, "has_openai_credentials", lambda: False)
    decision = capability.resolve_goal_page_discovery_capability(
        settings={"agent.capabilities.goal_page_discovery_enabled": True}
    )

    assert decision["enabled"] is False
    assert decision["source"] == "fallback"

