from __future__ import annotations

from api.services.agent.orchestration.role_router import (
    build_role_owned_steps,
    role_owned_steps_to_payload,
)
from api.services.agent.orchestration.step_planner_sections.events import (
    plan_ready_event,
    plan_step_event,
)
from api.services.agent.planner import PlannedStep


def _event_factory(**kwargs):
    return kwargs


def test_build_role_owned_steps_assigns_owner_roles_and_handoffs() -> None:
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="Research", params={}),
        PlannedStep(tool_id="browser.playwright.inspect", title="Inspect", params={}),
        PlannedStep(tool_id="report.generate", title="Write report", params={}),
    ]

    role_steps = build_role_owned_steps(steps=steps)

    assert [row.owner_role for row in role_steps] == ["research", "browser", "writer"]
    assert role_steps[0].handoff_from_role is None
    assert role_steps[1].handoff_from_role == "research"
    assert role_steps[2].handoff_from_role == "browser"

    payload = role_owned_steps_to_payload(steps=role_steps)
    assert payload[0]["owner_role"] == "research"
    assert payload[1]["handoff_from_role"] == "research"


def test_plan_events_carry_role_owned_metadata() -> None:
    step = PlannedStep(tool_id="report.generate", title="Write report", params={})

    step_event = plan_step_event(
        activity_event_factory=_event_factory,
        step_number=3,
        planned_step=step,
        owner_role="writer",
        handoff_from_role="browser",
    )
    assert step_event["metadata"]["owner_role"] == "writer"
    assert step_event["metadata"]["handoff_from_role"] == "browser"

    ready_event = plan_ready_event(
        activity_event_factory=_event_factory,
        steps=[step],
        role_owned_steps=[
            {
                "step": 1,
                "owner_role": "writer",
                "tool_id": "report.generate",
                "title": "Write report",
            }
        ],
    )
    assert ready_event["metadata"]["role_owned_steps"][0]["owner_role"] == "writer"

