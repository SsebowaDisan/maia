from __future__ import annotations

import os

from api.services.agent.orchestration.discovery_gate import (
    update_slot_lifecycle,
    with_slot_lifecycle_defaults,
)


def test_with_slot_lifecycle_defaults_sets_open_state() -> None:
    slots = with_slot_lifecycle_defaults(
        slots=[
            {
                "requirement": "Target website URL",
                "discoverable": True,
                "blocking": True,
                "confidence": 0.8,
                "resolved_value": "",
            }
        ]
    )
    assert slots
    assert slots[0].get("state") == "open"
    assert slots[0].get("attempt_count") == 0


def test_update_slot_lifecycle_marks_blocked_when_unresolved() -> None:
    previous = os.environ.get("MAIA_AGENT_LLM_SLOT_LIFECYCLE_ENABLED")
    os.environ["MAIA_AGENT_LLM_SLOT_LIFECYCLE_ENABLED"] = "0"
    try:
        slots = update_slot_lifecycle(
            slots=[
                {
                    "requirement": "Recipient email address",
                    "discoverable": False,
                    "blocking": True,
                    "confidence": 0.9,
                    "resolved_value": "",
                }
            ],
            unresolved_requirements=["Recipient email address"],
            attempted_requirements=["Recipient email address"],
            evidence_sources=["email.send"],
        )
    finally:
        if previous is None:
            os.environ.pop("MAIA_AGENT_LLM_SLOT_LIFECYCLE_ENABLED", None)
        else:
            os.environ["MAIA_AGENT_LLM_SLOT_LIFECYCLE_ENABLED"] = previous
    assert slots
    assert slots[0].get("state") == "blocked"
    assert int(slots[0].get("attempt_count") or 0) >= 1

