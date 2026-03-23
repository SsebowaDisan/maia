from __future__ import annotations

from api.services.agent import collaboration_logs as module


class _FakeStore:
    def __init__(self) -> None:
        self.appended = []
        self.rows = []

    def append(self, event):
        self.appended.append(event)

    def load_events(self, run_id: str):
        return list(self.rows)


def test_record_persists_collaboration_event(monkeypatch) -> None:
    store = _FakeStore()
    monkeypatch.setattr("api.services.agent.activity.get_activity_store", lambda: store)
    monkeypatch.setattr(
        "api.services.agent.live_events.get_live_event_broker",
        lambda: type("_Broker", (), {"publish": lambda *args, **kwargs: None})(),
    )

    service = module.CollaborationLogService()
    row = service.record(
        run_id="run_1",
        from_agent="researcher",
        to_agent="analyst",
        message="Please validate these findings.",
        entry_type="question",
    )

    assert row["entry_type"] == "question"
    assert len(store.appended) == 1
    assert str(store.appended[0].event_type) == "agent_collaboration"


def test_get_log_restores_from_activity_store_when_memory_is_empty(monkeypatch) -> None:
    store = _FakeStore()
    store.rows = [
        {
            "type": "event",
            "payload": {
                "event_type": "agent_collaboration",
                "detail": "Validate this with source B.",
                "timestamp": "2026-03-20T12:00:00Z",
                "data": {
                    "from_agent": "analyst",
                    "to_agent": "researcher",
                    "message": "Validate this with source B.",
                    "entry_type": "question",
                    "timestamp": 1_763_472_000,
                },
            },
        }
    ]
    monkeypatch.setattr("api.services.agent.activity.get_activity_store", lambda: store)

    service = module.CollaborationLogService()
    rows = service.get_log("run_1")

    assert len(rows) == 1
    assert rows[0]["from_agent"] == "analyst"
    assert "source B" in rows[0]["message"]
