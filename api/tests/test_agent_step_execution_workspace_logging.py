from __future__ import annotations

from api.services.agent.models import AgentActivityEvent
from api.services.agent.orchestration.models import ExecutionState
from api.services.agent.orchestration.step_execution_sections.failure import handle_step_failure
from api.services.agent.orchestration.step_execution_sections.guards import (
    prepare_step_params,
    should_skip_step_for_workspace_logging,
)
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import AgentTool, ToolExecutionContext, ToolMetadata


class _DummyTool(AgentTool):
    def __init__(self, tool_id: str, action_class: str) -> None:
        self.metadata = ToolMetadata(
            tool_id=tool_id,
            action_class=action_class,  # type: ignore[arg-type]
            risk_level="low",
            required_permissions=[],
            execution_policy="auto_execute",
            description="dummy",
        )

    def execute(self, *, context, prompt, params):  # pragma: no cover - not used in tests
        raise NotImplementedError


class _Registry:
    def get(self, tool_id: str) -> AgentTool:
        action_class = "execute" if tool_id.startswith("workspace.sheets") else "draft"
        return _DummyTool(tool_id=tool_id, action_class=action_class)


def _state(*, deep_workspace_logging_enabled: bool = True) -> ExecutionState:
    return ExecutionState(
        execution_context=ToolExecutionContext(
            user_id="user-1",
            tenant_id="tenant-1",
            conversation_id="conv-1",
            run_id="run-1",
            mode="company_agent",
            settings={"agent.tenant_id": "tenant-1"},
        ),
        deep_workspace_logging_enabled=deep_workspace_logging_enabled,
    )


def _activity_factory(**kwargs) -> AgentActivityEvent:
    return AgentActivityEvent(
        event_id=f"evt_{kwargs.get('event_type', 'event')}",
        run_id="run-1",
        event_type=str(kwargs.get("event_type") or ""),
        title=str(kwargs.get("title") or ""),
        detail=str(kwargs.get("detail") or ""),
        metadata=dict(kwargs.get("metadata") or {}),
        stage=str(kwargs.get("stage") or "tool"),
        status=str(kwargs.get("status") or "info"),
        snapshot_ref=kwargs.get("snapshot_ref"),
    )


def test_should_skip_workspace_steps_only_when_marked_as_logging_step() -> None:
    state = _state(deep_workspace_logging_enabled=False)
    roadmap_step = PlannedStep(
        tool_id="workspace.sheets.track_step",
        title="Roadmap",
        params={"__workspace_logging_step": True},
    )
    explicit_docs_step = PlannedStep(
        tool_id="workspace.docs.research_notes",
        title="Write findings to Google Docs",
        params={"note": "hello"},
    )
    assert should_skip_step_for_workspace_logging(state=state, step=roadmap_step) is True
    assert should_skip_step_for_workspace_logging(state=state, step=explicit_docs_step) is False


def test_workspace_logging_failure_disables_only_optional_logging_steps() -> None:
    state = _state(deep_workspace_logging_enabled=True)
    step = PlannedStep(
        tool_id="workspace.sheets.track_step",
        title="Roadmap step",
        params={"__workspace_logging_step": True},
    )
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        handle_step_failure(
            execution_prompt="research",
            state=state,
            registry=_Registry(),
            step=step,
            index=1,
            step_started="2026-01-01T00:00:00Z",
            duration_seconds=0.1,
            exc=RuntimeError("google_tokens_missing: No Google token record found for this user."),
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    assert state.deep_workspace_logging_enabled is False
    assert any("Workspace logging disabled" in event.title for event in captured)
    assert any(str(event.event_type) == "tool_skipped" for event in captured)
    assert state.all_actions
    assert state.all_actions[-1].status == "skipped"
    assert state.executed_steps[-1].get("status") == "skipped"


def test_workspace_logging_failure_disables_for_service_account_unauthorized_client() -> None:
    state = _state(deep_workspace_logging_enabled=True)
    step = PlannedStep(
        tool_id="workspace.sheets.track_step",
        title="Roadmap step",
        params={"__workspace_logging_step": True},
    )
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        handle_step_failure(
            execution_prompt="research",
            state=state,
            registry=_Registry(),
            step=step,
            index=1,
            step_started="2026-01-01T00:00:00Z",
            duration_seconds=0.1,
            exc=RuntimeError(
                "google_service_account_token_failed: unauthorized_client"
            ),
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    assert state.deep_workspace_logging_enabled is False
    assert any(str(event.event_type) == "tool_skipped" for event in captured)


def test_explicit_workspace_step_failure_keeps_logging_flag_enabled() -> None:
    state = _state(deep_workspace_logging_enabled=True)
    step = PlannedStep(
        tool_id="workspace.docs.research_notes",
        title="Write findings to Google Docs",
        params={"note": "hello"},
    )
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        handle_step_failure(
            execution_prompt="research",
            state=state,
            registry=_Registry(),
            step=step,
            index=2,
            step_started="2026-01-01T00:00:00Z",
            duration_seconds=0.1,
            exc=RuntimeError("google_tokens_missing: No Google token record found for this user."),
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    assert state.deep_workspace_logging_enabled is True
    assert all("Workspace logging disabled" not in event.title for event in captured)


def test_execute_failure_emits_clarification_request_from_recovery_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.failure.suggest_failure_recovery",
        lambda **_: "Provide sender full name for outreach form submission.",
    )
    state = _state(deep_workspace_logging_enabled=True)
    state.execution_context.settings["__task_clarification_missing"] = [
        "Provide sender full name for outreach form submission."
    ]
    state.execution_context.settings["__task_clarification_questions"] = [
        "Please provide sender full name for outreach form submission."
    ]
    step = PlannedStep(
        tool_id="workspace.sheets.track_step",
        title="Execute outreach action",
        params={},
    )
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        handle_step_failure(
            execution_prompt="send outreach",
            state=state,
            registry=_Registry(),
            step=step,
            index=4,
            step_started="2026-01-01T00:00:00Z",
            duration_seconds=0.2,
            exc=RuntimeError("execution failed"),
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    assert any(event.event_type == "llm.clarification_requested" for event in captured)
    clarification_event = next(event for event in captured if event.event_type == "llm.clarification_requested")
    assert clarification_event.data.get("deferred_until_after_attempts") is True


def test_prepare_step_params_hydrates_web_extract_from_latest_web_sources() -> None:
    state = _state()
    state.execution_context.settings["__latest_web_sources"] = [
        {"url": "https://example.com/placeholder"},
        {"url": "https://hai.stanford.edu/ai-index"},
        {"url": "https://www.ibm.com/think/topics/machine-learning"},
    ]
    step = PlannedStep(
        tool_id="web.extract.structured",
        title="Extract findings",
        params={"field_schema": {"topic": "string"}},
    )

    params = prepare_step_params(
        step=step,
        access_context=type("AccessContext", (), {"access_mode": "restricted", "full_access_enabled": False})(),
        settings=state.execution_context.settings,
    )

    assert params.get("url") == "https://hai.stanford.edu/ai-index"
    assert params.get("candidate_urls") == [
        "https://hai.stanford.edu/ai-index",
        "https://www.ibm.com/think/topics/machine-learning",
    ]


def test_prepare_step_params_hydrates_browser_inspect_from_latest_web_sources() -> None:
    state = _state()
    state.execution_context.settings["__latest_web_sources"] = [
        {"url": "https://example.com/placeholder"},
        {"url": "https://hai.stanford.edu/ai-index"},
        {"url": "https://www.ibm.com/think/topics/machine-learning"},
    ]
    step = PlannedStep(
        tool_id="browser.playwright.inspect",
        title="Inspect source",
        params={"urls": []},
    )

    params = prepare_step_params(
        step=step,
        access_context=type("AccessContext", (), {"access_mode": "restricted", "full_access_enabled": False})(),
        settings=state.execution_context.settings,
    )

    assert params.get("url") == "https://hai.stanford.edu/ai-index"
    assert params.get("urls") == [
        "https://hai.stanford.edu/ai-index",
        "https://www.ibm.com/think/topics/machine-learning",
    ]


def test_execute_failure_does_not_emit_clarification_for_internal_recovery_hint(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.services.agent.orchestration.step_execution_sections.failure.suggest_failure_recovery",
        lambda **_: "Check the API request parameters for correctness and retry the Google Slides tool execution.",
    )
    state = _state(deep_workspace_logging_enabled=True)
    step = PlannedStep(
        tool_id="workspace.sheets.track_step",
        title="Execute outreach action",
        params={},
    )
    captured: list[AgentActivityEvent] = []

    def _emit(event: AgentActivityEvent):
        captured.append(event)
        return {"type": "activity", "event": event.to_dict()}

    _ = list(
        handle_step_failure(
            execution_prompt="send outreach",
            state=state,
            registry=_Registry(),
            step=step,
            index=5,
            step_started="2026-01-01T00:00:00Z",
            duration_seconds=0.2,
            exc=RuntimeError("execution failed"),
            emit_event=_emit,
            activity_event_factory=_activity_factory,
        )
    )

    assert not any(event.event_type == "llm.clarification_requested" for event in captured)
    assert state.execution_context.settings.get("__clarification_requested_after_attempt") is None
