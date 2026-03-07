from __future__ import annotations

from dataclasses import dataclass

from api.services.agent.orchestration.models import ExecutionState
from api.services.agent.orchestration.run_checkpoint_persistence import persist_run_checkpoint
from api.services.agent.planner import PlannedStep
from api.services.agent.tools.base import ToolExecutionContext


@dataclass
class _RequestStub:
    message: str = "Run analysis"
    agent_goal: str = "Analyze target"


class _SessionStoreStub:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def save_session_run(self, payload: dict) -> dict:
        self.saved.append(dict(payload))
        return payload


def _state() -> ExecutionState:
    context = ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-1",
        mode="company_agent",
        settings={},
    )
    state = ExecutionState(execution_context=context)
    state.executed_steps.append({"step": 1, "tool_id": "marketing.web_research", "status": "success"})
    state.next_steps.append("Review draft")
    return state


def test_persist_run_checkpoint_stores_resumable_payload() -> None:
    store = _SessionStoreStub()
    state = _state()
    state.execution_context.settings["__execution_checkpoints"] = [{"name": "plan_ready"}]
    persist_run_checkpoint(
        session_store=store,
        run_id="run-1",
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        request=_RequestStub(),
        checkpoint={"name": "execution_cycle_started", "status": "in_progress"},
        settings=state.execution_context.settings,
        state=state,
        pending_steps=[
            PlannedStep(tool_id="report.generate", title="Generate report", params={}),
        ],
        resume_status="paused",
    )
    assert store.saved
    row = store.saved[-1]
    assert row["run_id"] == "run-1"
    assert row["resume_status"] == "paused"
    assert row["execution_checkpoint"]["name"] == "execution_cycle_started"
    assert isinstance(row.get("pending_steps"), list)
    assert row["pending_steps"][0]["tool_id"] == "report.generate"
    assert isinstance(row.get("executed_steps"), list)
    assert isinstance(row.get("next_recommended_steps"), list)
