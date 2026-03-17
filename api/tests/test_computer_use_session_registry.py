from __future__ import annotations

import importlib

import pytest

from api.services.computer_use import session_registry as session_registry_module


def _reload_registry_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    max_sessions: int,
    max_streams: int,
):
    monkeypatch.setenv("MAIA_COMPUTER_USE_MAX_SESSIONS_PER_USER", str(max_sessions))
    monkeypatch.setenv("MAIA_COMPUTER_USE_MAX_CONCURRENT_STREAMS_PER_USER", str(max_streams))
    module = importlib.reload(session_registry_module)
    monkeypatch.setattr(module, "mark_stale_active_sessions", lambda: 0)
    monkeypatch.setattr(module, "create_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "close_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(module.BrowserSession, "start", lambda self: None)
    monkeypatch.setattr(module.BrowserSession, "close", lambda self: None)
    return module


def test_create_is_idempotent_and_owner_scoped(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _reload_registry_module(monkeypatch, max_sessions=3, max_streams=1)
    registry = module.SessionRegistry()

    first = registry.create(user_id="u1", start_url="about:blank", request_id="req-1")
    second = registry.create(user_id="u1", start_url="about:blank", request_id="req-1")

    assert first.session_id == second.session_id
    assert registry.get_for_user(first.session_id, user_id="u1") is not None
    assert registry.get_for_user(first.session_id, user_id="u2") is None


def test_create_enforces_per_user_session_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _reload_registry_module(monkeypatch, max_sessions=1, max_streams=1)
    registry = module.SessionRegistry()

    registry.create(user_id="u1", start_url="about:blank")
    with pytest.raises(module.SessionLimitExceeded):
        registry.create(user_id="u1", start_url="about:blank")

    # Other users are not blocked by u1's cap.
    registry.create(user_id="u2", start_url="about:blank")


def test_stream_lease_enforces_session_and_user_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _reload_registry_module(monkeypatch, max_sessions=3, max_streams=1)
    registry = module.SessionRegistry()

    s1 = registry.create(user_id="u1", start_url="about:blank")
    s2 = registry.create(user_id="u1", start_url="about:blank")

    registry.try_acquire_stream_lease(session_id=s1.session_id, user_id="u1")

    with pytest.raises(RuntimeError):
        registry.try_acquire_stream_lease(session_id=s1.session_id, user_id="u1")

    with pytest.raises(module.StreamLimitExceeded):
        registry.try_acquire_stream_lease(session_id=s2.session_id, user_id="u1")

    with pytest.raises(KeyError):
        registry.try_acquire_stream_lease(session_id=s2.session_id, user_id="u2")

    registry.release_stream_lease(session_id=s1.session_id, user_id="u1")
    registry.try_acquire_stream_lease(session_id=s2.session_id, user_id="u1")

