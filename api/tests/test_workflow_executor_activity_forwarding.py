from __future__ import annotations

from types import SimpleNamespace

from api.services.agents import workflow_executor as module


def test_run_agent_step_unwraps_activity_stream_events(monkeypatch) -> None:
    fake_record = SimpleNamespace(agent_id="researcher")
    fake_schema = SimpleNamespace(
        system_prompt="",
        tools=[],
        max_tool_calls_per_run=None,
    )

    def _fake_get_agent(tenant_id: str, agent_id: str):
        return fake_record

    def _fake_load_schema(record):
        return fake_schema

    def _fake_run_agent_task(*args, **kwargs):
        yield {
            "type": "activity",
            "event": {
                "event_type": "browser_navigate",
                "event_id": "evt_nav",
                "run_id": "run_1",
                "title": "Navigate",
                "detail": "Opening source page",
                "timestamp": "2026-01-01T00:00:00Z",
                "data": {"url": "https://example.com"},
                "metadata": {},
            },
        }
        yield {"type": "chat_delta", "delta": "hello", "text": "hello"}
        yield {"event_type": "budget_exceeded", "detail": "limit reached"}

    monkeypatch.setattr("api.services.agents.definition_store.get_agent", _fake_get_agent)
    monkeypatch.setattr("api.services.agents.definition_store.load_schema", _fake_load_schema)
    monkeypatch.setattr("api.services.agents.runner.run_agent_task", _fake_run_agent_task)
    monkeypatch.setattr(module, "_verify_and_clean_citations", lambda text, tenant_id: text)

    captured: list[dict] = []
    result = module._run_agent_step(
        "researcher",
        {"task": "research topic"},
        "tenant_1",
        on_event=lambda event: captured.append(dict(event)),
    )

    assert result == "hello"
    event_types = [str(event.get("event_type") or "").strip().lower() for event in captured]
    assert "browser_navigate" in event_types
    assert "budget_exceeded" in event_types
    assert "chat_delta" not in event_types
