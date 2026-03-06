from __future__ import annotations

from api.services.agent.orchestration.contract_slots import classify_missing_requirement_slots


def test_classify_missing_requirement_slots_uses_llm_response(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_CONTRACT_SLOT_ENABLED", "1")
    monkeypatch.setattr(
        "api.services.agent.orchestration.contract_slots.call_json_response",
        lambda **_: {
            "slots": [
                {
                    "requirement_index": 0,
                    "description": "Recipient address still required",
                    "discoverable": False,
                    "blocking": True,
                    "confidence": 0.91,
                    "evidence_sources": ["website"],
                    "resolved_value": "",
                    "question": "Please share the recipient email address.",
                }
            ]
        },
    )
    slots = classify_missing_requirement_slots(
        missing_requirements=["Recipient email address for delivery"],
        message="Send the report to leadership",
        agent_goal="Email delivery",
        rewritten_task="Prepare and deliver findings",
        intent_tags=["email_delivery"],
        conversation_summary="",
    )
    assert len(slots) == 1
    assert slots[0]["requirement"] == "Recipient email address for delivery"
    assert slots[0]["blocking"] is True
    assert slots[0]["discoverable"] is False
    assert slots[0]["question"] == "Please share the recipient email address."


def test_classify_missing_requirement_slots_falls_back_when_llm_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_CONTRACT_SLOT_ENABLED", "0")
    slots = classify_missing_requirement_slots(
        missing_requirements=["Provide sender identity details required for outreach"],
        message="Send website outreach",
        agent_goal="",
        rewritten_task="",
        intent_tags=["contact_form_submission"],
        conversation_summary="",
    )
    assert len(slots) == 1
    assert slots[0]["blocking"] is True
    assert slots[0]["discoverable"] is False

