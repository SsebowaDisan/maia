from __future__ import annotations

from api.services.agent.orchestration.discovery_gate import (
    blocking_requirements_from_slots,
    clarification_questions_from_slots,
)


def test_blocking_requirements_from_slots_prefers_non_discoverable_slots() -> None:
    rows = blocking_requirements_from_slots(
        slots=[
            {
                "requirement": "Recipient email address for delivery",
                "discoverable": False,
                "blocking": True,
            },
            {
                "requirement": "Target website URL",
                "discoverable": True,
                "blocking": True,
            },
        ],
        fallback_requirements=["Recipient email address for delivery", "Target website URL"],
    )
    assert rows == ["Recipient email address for delivery"]


def test_clarification_questions_from_slots_uses_slot_questions() -> None:
    questions = clarification_questions_from_slots(
        slots=[
            {
                "requirement": "Recipient email address for delivery",
                "question": "Please provide the destination email.",
            }
        ],
        requirements=["Recipient email address for delivery"],
    )
    assert questions == ["Please provide the destination email."]

