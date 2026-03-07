from __future__ import annotations

from api.services.agent.orchestration.discovery_gate import (
    attempted_discovery_requirements_from_slots,
    blocking_requirements_from_slots,
    clarification_questions_from_slots,
    unresolved_requirements_from_slots,
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


def test_blocking_requirements_from_slots_defers_discoverable_until_attempts_exhausted() -> None:
    rows = blocking_requirements_from_slots(
        slots=[
            {
                "requirement": "Target website URL",
                "discoverable": True,
                "blocking": True,
                "state": "attempting_discovery",
                "attempt_count": 1,
            }
        ],
        fallback_requirements=["Target website URL"],
        discovery_attempts_required=2,
    )
    assert rows == []


def test_unresolved_and_attempted_requirement_helpers() -> None:
    slots = [
        {
            "requirement": "Target website URL",
            "discoverable": True,
            "blocking": True,
            "state": "attempting_discovery",
            "attempt_count": 1,
            "resolved_value": "",
        },
        {
            "requirement": "Recipient email address",
            "discoverable": False,
            "blocking": True,
            "state": "open",
            "resolved_value": "",
        },
        {
            "requirement": "Company name",
            "discoverable": True,
            "blocking": False,
            "state": "resolved",
            "resolved_value": "Axon Group",
        },
    ]
    unresolved = unresolved_requirements_from_slots(
        slots=slots,
        fallback_requirements=[],
    )
    attempted = attempted_discovery_requirements_from_slots(
        slots=slots,
    )
    assert "Target website URL" in unresolved
    assert "Recipient email address" in unresolved
    assert "Company name" not in unresolved
    assert attempted == ["Target website URL"]
