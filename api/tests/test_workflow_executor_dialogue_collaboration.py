from __future__ import annotations

from types import SimpleNamespace

from api.services.agents import workflow_executor as module


class _FakeRunContext:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    def read(self, key: str):
        if key == "__workflow_agent_ids":
            return ["researcher", "analyst", "writer"]
        if key == "__workflow_agent_roster":
            return [
                {"agent_id": "researcher", "step_description": "collect sources"},
                {"agent_id": "analyst", "step_description": "analyze findings"},
            ]
        return None


def test_dialogue_detection_integrates_real_teammate_response(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [{"target_agent": "analyst", "question": "Can you validate the trend?"}],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            return "Trend validated with competitor benchmark."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", description="Research findings")
    calls: list[tuple[str, str]] = []

    def _run_agent_as(agent_id: str, prompt: str) -> str:
        calls.append((agent_id, prompt))
        return "Integrated output with validated benchmark context."

    events: list[dict] = []
    result = module._run_dialogue_detection(
        step=step,
        output="Initial draft output",
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=lambda event: events.append(dict(event)),
        run_agent_for_agent_fn=_run_agent_as,
    )

    assert result == "Integrated output with validated benchmark context."
    assert calls and calls[0][0] == "researcher"
    event_types = {str(event.get("event_type")) for event in events}
    assert "agent_dialogue_started" in event_types
    assert "agent_dialogue_resolved" in event_types
    assert "agent_dialogue_turn" in event_types


def test_dialogue_detection_falls_back_to_enrichment_when_no_agent_callback(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [{"target_agent": "analyst", "question": "Need numbers?"}],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            return "Use Q3 dataset only."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", description="Research findings")

    result = module._run_dialogue_detection(
        step=step,
        output="Initial draft output",
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=None,
        run_agent_for_agent_fn=None,
    )

    assert "Additional context from team dialogue" in result
    assert "[From analyst]: Use Q3 dataset only." in result


def test_dialogue_detection_derives_response_turn_type_without_hardcoded_map(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [
            {
                "target_agent": "analyst",
                "interaction_type": "cross_check_request",
                "interaction_label": "cross-check evidence",
                "scene_family": "email",
                "scene_surface": "email",
                "operation_label": "Rewrite draft email",
                "question": "Please cross-check this claim with independent data.",
            }
        ],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    captured_kwargs: dict[str, str] = {}

    class _FakeDialogueService:
        def ask(self, **kwargs):
            captured_kwargs["ask_turn_type"] = str(kwargs.get("ask_turn_type", ""))
            captured_kwargs["answer_turn_type"] = str(kwargs.get("answer_turn_type", ""))
            captured_kwargs["interaction_label"] = str(kwargs.get("interaction_label", ""))
            captured_kwargs["scene_family"] = str(kwargs.get("scene_family", ""))
            captured_kwargs["scene_surface"] = str(kwargs.get("scene_surface", ""))
            captured_kwargs["operation_label"] = str(kwargs.get("operation_label", ""))
            return "Cross-check complete."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", description="Research findings")
    result = module._run_dialogue_detection(
        step=step,
        output="Initial draft output",
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=None,
        run_agent_for_agent_fn=None,
    )

    assert "Additional context from team dialogue" in result
    assert captured_kwargs["ask_turn_type"] == "cross_check_request"
    assert captured_kwargs["answer_turn_type"] == "cross_check_response"
    assert captured_kwargs["interaction_label"] == "cross-check evidence"
    assert captured_kwargs["scene_family"] == "email"
    assert captured_kwargs["scene_surface"] == "email"
    assert captured_kwargs["operation_label"] == "Rewrite draft email"
