from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
testclient = pytest.importorskip("fastapi.testclient")

FastAPI = fastapi.FastAPI
TestClient = testclient.TestClient

from api.routers import computer_use as computer_use_router
from api.services.computer_use.policy_gate import PolicyDecision


class _FakeSession:
    def current_url(self) -> str:
        return "about:blank"

    def viewport(self) -> dict[str, int]:
        return {"width": 1280, "height": 800}


class _FakeRegistry:
    def get_for_user(self, session_id: str, *, user_id: str):
        if session_id == "s1" and user_id == "u1":
            return _FakeSession()
        return None

    def try_acquire_stream_lease(self, *, session_id: str, user_id: str) -> None:
        return None

    def release_stream_lease(self, *, session_id: str, user_id: str) -> None:
        return None


class _FakeSLOStore:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def record_stream_result(self, **kwargs) -> None:
        self.rows.append(dict(kwargs))

    def summary(self, *, user_id: str | None = None, window_seconds: int = 86400):
        return {
            "window_seconds": window_seconds,
            "run_count": 1,
            "success_rate": 1.0,
            "error_rate": 0.0,
            "p50_latency_ms": 120,
            "p95_latency_ms": 120,
            "p99_latency_ms": 120,
            "avg_latency_ms": 120,
            "avg_event_count": 3.0,
            "avg_action_count": 1.0,
            "status_counts": {"completed": 1},
        }


def test_stream_blocks_when_policy_denies(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(computer_use_router.router)
    fake_store = _FakeSLOStore()

    monkeypatch.setattr(computer_use_router, "get_session_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(computer_use_router, "get_computer_use_slo_store", lambda: fake_store)
    monkeypatch.setattr(
        computer_use_router,
        "evaluate_task_policy",
        lambda _task: PolicyDecision(
            allowed=False,
            mode="enforce",
            reason="Blocked by policy",
            matched_terms=("blocked",),
            max_task_chars=4000,
        ),
    )

    client = TestClient(app)
    response = client.get(
        "/api/computer-use/sessions/s1/stream",
        params={"task": "blocked task"},
        headers={"X-User-Id": "u1"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Blocked by policy"
    assert len(fake_store.rows) == 1
    assert fake_store.rows[0]["status"] == "policy_blocked"


def test_slo_summary_endpoint_returns_store_summary(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(computer_use_router.router)
    fake_store = _FakeSLOStore()

    monkeypatch.setattr(computer_use_router, "get_computer_use_slo_store", lambda: fake_store)

    client = TestClient(app)
    response = client.get(
        "/api/computer-use/slo/summary",
        params={"window_seconds": 3600},
        headers={"X-User-Id": "u1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["window_seconds"] == 3600
    assert body["run_count"] == 1
    assert body["status_counts"] == {"completed": 1}
