from __future__ import annotations

from api.services.agent.orchestration.execution_checkpoints import (
    append_execution_checkpoint,
    build_role_dispatch_plan,
)
from api.services.agent.planner import PlannedStep


def test_build_role_dispatch_plan_groups_adjacent_role_segments() -> None:
    steps = [
        PlannedStep(tool_id="marketing.web_research", title="research", params={}),
        PlannedStep(tool_id="marketing.web_research", title="research-2", params={}),
        PlannedStep(tool_id="browser.playwright.inspect", title="inspect", params={}),
        PlannedStep(tool_id="workspace.docs.research_notes", title="write-note", params={}),
        PlannedStep(tool_id="report.generate", title="draft", params={}),
    ]
    dispatch = build_role_dispatch_plan(steps=steps)
    assert [row["role"] for row in dispatch] == ["research", "browser", "writer"]
    assert dispatch[0]["start_step"] == 1
    assert dispatch[0]["end_step"] == 2
    assert dispatch[1]["start_step"] == 3
    assert dispatch[2]["start_step"] == 4
    assert dispatch[2]["end_step"] == 5


def test_append_execution_checkpoint_persists_recent_history() -> None:
    settings: dict[str, object] = {}
    for idx in range(85):
        append_execution_checkpoint(
            settings=settings,
            name=f"checkpoint_{idx}",
            status="completed",
            cycle=1,
            step_cursor=idx,
            pending_steps=max(0, 85 - idx),
            active_role="writer",
        )
    history = settings.get("__execution_checkpoints")
    assert isinstance(history, list)
    assert len(history) == 80
    last = settings.get("__execution_last_checkpoint")
    assert isinstance(last, dict)
    assert last.get("name") == "checkpoint_84"
    assert last.get("status") == "completed"
