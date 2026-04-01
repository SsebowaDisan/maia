from __future__ import annotations

import time
from typing import Any, Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import get_current_registered_user_id
from api.routers import chat as chat_router


def _slow_stream(*_args: Any, **_kwargs: Any) -> Generator[dict[str, Any], None, dict[str, Any]]:
    yield {"type": "activity", "event": {"title": "Starting"}}
    time.sleep(0.18)
    return {
        "conversation_id": "c1",
        "conversation_name": "Conversation",
        "message": "hello",
        "answer": "done",
        "info": "",
        "plot": None,
        "state": {},
        "mode": "deep_search",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": [],
        "next_recommended_steps": [],
        "needs_human_review": False,
        "human_review_notes": None,
        "web_summary": {},
        "activity_run_id": "run-1",
        "info_panel": {},
        "mindmap": {},
    }


def test_chat_stream_emits_heartbeat_ping_during_long_wait(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_current_registered_user_id] = lambda: "u-test"

    monkeypatch.setattr(chat_router, "get_context", lambda: object())
    monkeypatch.setattr(chat_router, "stream_chat_turn", _slow_stream)
    monkeypatch.setattr(chat_router, "_STREAM_HEARTBEAT_SECONDS", 0.03)
    monkeypatch.setattr(chat_router, "end_trace", lambda *_args, **_kwargs: None)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        json={"message": "hello", "agent_mode": "deep_search"},
    )
    body = response.text

    assert response.status_code == 200
    assert "event: ping" in body
    assert "event: done" in body
