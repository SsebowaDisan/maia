from __future__ import annotations

import sys
from types import SimpleNamespace

from api.services.agents import runner as module


def test_run_agent_task_skips_long_term_memory_for_explicit_workflow_stage(monkeypatch) -> None:
    observed_request = {}

    class _FakeOrchestrator:
        def run_stream(self, *, user_id, conversation_id, request, settings):
            observed_request["message"] = request.message
            observed_request["settings"] = settings
            yield {"type": "chat_delta", "text": "done"}

    monkeypatch.setitem(
        sys.modules,
        "api.services.agent.orchestration.app",
        SimpleNamespace(get_orchestrator=lambda: _FakeOrchestrator()),
    )
    monkeypatch.setattr(
        module,
        "_prepare_memory_context",
        lambda tenant_id, agent_id, task, k=5: "[Relevant memories from previous runs:]\n- stale benchmark memory",
    )

    list(
        module.run_agent_task(
            "Research machine learning citations",
            tenant_id="tenant_1",
            run_id="run_1",
            agent_id="researcher",
            allowed_tool_ids=["marketing.web_research"],
        )
    )

    assert "[Relevant memories from previous runs:]" not in str(observed_request.get("message") or "")
