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
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
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
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
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
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
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


def test_dialogue_detection_skips_low_value_citation_hygiene_after_review(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [
            {
                "target_agent": "analyst",
                "interaction_type": "request_missing_citation_details",
                "interaction_label": "complete citations",
                "scene_family": "document",
                "scene_surface": "google_docs",
                "operation_label": "Finalize evidence citations",
                "question": "Please complete citation [3].",
                "reason": "The Evidence Citations section may be incomplete.",
            }
        ],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.propose_seed_dialogue_turn",
        lambda **_: {},
    )

    asked = {"value": False}

    class _FakeDialogueService:
        def ask(self, **kwargs):
            asked["value"] = True
            return "Filled citation."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", description="Research findings")
    reviewed_output = (
        "Executive Summary\nMachine learning adoption is accelerating [1][2][3].\n\n"
        "## Evidence Citations\n"
        "- [1] [Source 1](https://example.com/1)\n"
        "- [2] [Source 2](https://example.com/2)\n"
        "- [3] [Source 3](https://example.com/3)"
    )

    result = module._run_dialogue_detection(
        step=step,
        output=reviewed_output,
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=None,
        run_agent_for_agent_fn=lambda *_: "should not be used",
    )

    assert result == reviewed_output
    assert asked["value"] is False


def test_dialogue_detection_rejects_partial_integration_rewrite(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
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
    original = (
        "Executive Summary\nMachine learning improves forecast quality in structured settings [1][2].\n\n"
        "## Evidence Citations\n"
        "- [1] [Source 1](https://example.com/1)\n"
        "- [2] [Source 2](https://example.com/2)"
    )

    result = module._run_dialogue_detection(
        step=step,
        output=original,
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=None,
        run_agent_for_agent_fn=lambda *_: "—truncated fragment [1]",
    )

    assert result != "—truncated fragment [1]"
    assert "Additional context from team dialogue" in result
    assert "[From analyst]: Trend validated with competitor benchmark." in result


def test_should_skip_post_review_collaboration_when_deadline_is_near(monkeypatch) -> None:
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)
    assert module._should_skip_post_review_collaboration(
        step_deadline_ts=220.0,
        minimum_seconds_required=150.0,
    ) is True
    assert module._should_skip_post_review_collaboration(
        step_deadline_ts=320.0,
        minimum_seconds_required=150.0,
    ) is False


def test_dialogue_detection_uses_seed_turn_when_primary_detector_returns_none(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.propose_seed_dialogue_turn",
        lambda **_: {
            "target_agent": "analyst",
            "interaction_type": "peer_review_request",
            "interaction_label": "peer review",
            "scene_family": "document",
            "scene_surface": "google_docs",
            "operation_label": "Review draft summary",
            "question": "Please verify whether the margin conclusion needs caveats.",
        },
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            return "Yes, add a caveat about FX volatility."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(agent_id="writer", step_id="step_3", description="Draft the executive summary")
    events: list[dict] = []
    result = module._run_dialogue_detection(
        step=step,
        output="Draft summary: margins will recover next quarter.",
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=lambda event: events.append(dict(event)),
        run_agent_for_agent_fn=lambda *_: "Revised summary with FX caveat included.",
    )

    assert result == "Revised summary with FX caveat included."
    event_types = {str(event.get("event_type")) for event in events}
    assert "agent_dialogue_started" in event_types
    assert "agent_dialogue_resolved" in event_types


def test_inject_handoff_context_emits_agent_handoff_event(monkeypatch) -> None:
    class _FakeContext:
        from_agent = "researcher"
        to_agent = "analyst"
        summary = "Collected validated source evidence."

        def to_prompt_context(self) -> str:
            return "handoff prompt"

        def to_dict(self) -> dict:
            return {
                "from_agent": self.from_agent,
                "to_agent": self.to_agent,
                "summary": self.summary,
            }

    monkeypatch.setattr(
        "api.services.agent.handoff_manager.build_handoff_context",
        lambda **_: _FakeContext(),
    )

    predecessor = SimpleNamespace(
        step_id="step_1",
        step_type="agent",
        output_key="output_step_1",
        agent_id="researcher",
        description="Collect evidence",
    )
    current = SimpleNamespace(
        step_id="step_2",
        step_type="agent",
        output_key="output_step_2",
        agent_id="analyst",
        description="Analyze findings",
    )
    workflow = SimpleNamespace(
        edges=[SimpleNamespace(from_step="step_1", to_step="step_2")],
        get_step=lambda step_id: predecessor if step_id == "step_1" else current if step_id == "step_2" else None,
    )
    step_inputs: dict = {}
    events: list[dict] = []

    module._inject_handoff_context(
        workflow=workflow,
        step=current,
        step_inputs=step_inputs,
        outputs={"output_step_1": "Prior output"},
        run_id="run_1",
        on_event=lambda event: events.append(dict(event)),
    )

    assert step_inputs.get("__handoff_context") == "handoff prompt"
    assert any(str(event.get("event_type")) == "agent_handoff" for event in events)


def test_brain_review_short_output_still_runs_dialogue(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [{"target_agent": "analyst", "question": "Can you verify this quickly?"}],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            return "Confirmed with latest source."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())
    monkeypatch.setattr(
        "api.services.agent.llm_runtime.call_text_response",
        lambda **kwargs: "Integrated short output with teammate verification.",
    )

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", step_type="agent", description="Quick validation")
    events: list[dict] = []
    result = module._run_brain_review(
        step=step,
        result="Short output",
        step_inputs={"message": "Validate quickly"},
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=lambda event: events.append(dict(event)),
    )

    assert "Integrated short output" in str(result)
    assert any(str(event.get("event_type")) == "agent_dialogue_started" for event in events)


def test_brain_review_nested_agent_runs_pass_run_id_and_on_event(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [{"target_agent": "analyst", "question": "Can you verify this quickly?"}],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            answer_fn = kwargs["answer_fn"]
            return answer_fn("analyst", "Provide a source-backed check.")

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())
    monkeypatch.setattr(
        "api.services.agent.llm_runtime.call_text_response",
        lambda **kwargs: "Source-backed verification complete.",
    )

    step = SimpleNamespace(agent_id="researcher", step_id="step_1", step_type="agent", description="Quick validation")
    events: list[dict] = []
    on_event = lambda event: events.append(dict(event))
    result = module._run_brain_review(
        step=step,
        result="Short output",
        step_inputs={"message": "Validate quickly"},
        tenant_id="tenant_1",
        run_id="run_123",
        on_event=on_event,
    )

    assert "Source-backed verification complete." in str(result)
    assert any(str(event.get("event_type")) == "agent_dialogue_started" for event in events)


def test_dialogue_detection_does_not_append_team_dialogue_to_customer_email(monkeypatch) -> None:
    monkeypatch.setattr("api.services.agents.workflow_context.WorkflowRunContext", _FakeRunContext)
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.infer_dialogue_scene",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.detect_dialogue_needs",
        lambda **_: [{"target_agent": "analyst", "question": "Can you confirm citation [2] is strong enough?"}],
    )
    monkeypatch.setattr(
        "api.services.agent.brain.dialogue_detector.evaluate_dialogue_follow_up",
        lambda **_: {"requires_follow_up": False},
    )

    class _FakeDialogueService:
        def ask(self, **kwargs):
            return "Citation [2] is supported by the Stanford AI Index and should stay."

    monkeypatch.setattr("api.services.agent.dialogue_turns.get_dialogue_service", lambda: _FakeDialogueService())

    step = SimpleNamespace(
        agent_id="email-specialist",
        step_id="step_2",
        description="Compose a polished, citation-rich email draft about machine learning for ssebowadisan1@gmail.com.",
        step_config={"tool_ids": ["report.generate", "gmail.draft", "mailer.report_send"]},
    )
    email_output = (
        "Subject: Machine Learning Research Brief\n\n"
        "Hi ssebowadisan1@gmail.com,\n\n"
        "Machine learning is increasingly central to modern software and science [1][2].\n\n"
        "Best regards,\n"
        "Maia\n\n"
        "## Evidence Citations\n"
        "- [1] [IBM Machine Learning](https://www.ibm.com/think/topics/machine-learning)\n"
        "- [2] [Stanford AI Index](https://aiindex.stanford.edu/)"
    )

    result = module._run_dialogue_detection(
        step=step,
        output=email_output,
        tenant_id="tenant_1",
        run_id="run_1",
        on_event=None,
        run_agent_for_agent_fn=None,
    )

    assert result == email_output
    assert "Additional context from team dialogue" not in result
