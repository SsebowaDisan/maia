from __future__ import annotations

from pathlib import Path

from api.services.google.auth import (
    OAUTH_OWNER_SET_AT_KEY,
    OAUTH_OWNER_USER_ID_KEY,
    OAUTH_SETUP_REQUESTS_KEY,
    GoogleOAuthManager,
    oauth_configuration_status,
    queue_google_oauth_setup_request,
    save_google_oauth_configuration,
)
from api.services.google.store import GoogleTokenStore, OAuthStateStore


def test_start_authorization_uses_stored_oauth_credentials(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)

    monkeypatch.setattr(
        "api.services.google.auth._oauth_store_values",
        lambda user_id=None, include_metadata=False: {
            "GOOGLE_OAUTH_CLIENT_ID": "stored_client_id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "stored_secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/agent/oauth/google/callback",
        },
    )

    manager = GoogleOAuthManager()
    manager.tokens = GoogleTokenStore(path=tmp_path / "tokens.json")
    manager.states = OAuthStateStore(path=tmp_path / "state.json", ttl_seconds=600)

    result = manager.start_authorization(user_id="user_1")

    assert "client_id=stored_client_id" in result.authorize_url
    assert result.redirect_uri == "http://localhost:8000/api/agent/oauth/google/callback"


def test_oauth_configuration_status_reports_stored_credentials(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)

    monkeypatch.setattr(
        "api.services.google.auth._oauth_store_values",
        lambda user_id=None, include_metadata=False: {
            "GOOGLE_OAUTH_CLIENT_ID": "stored_client_id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "stored_secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/api/agent/oauth/google/callback",
        },
    )

    status = oauth_configuration_status(user_id="user_1")

    assert status["oauth_ready"] is True
    assert status["oauth_missing_env"] == []
    assert status["oauth_client_id_configured"] is True
    assert status["oauth_client_secret_configured"] is True
    assert status["oauth_uses_stored_credentials"] is True


def test_oauth_configuration_status_owner_access_flags(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(
        "api.services.google.auth._oauth_store_values",
        lambda user_id=None, include_metadata=False: {
            "GOOGLE_OAUTH_CLIENT_ID": "stored_client_id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "stored_secret",
            OAUTH_OWNER_USER_ID_KEY: "owner_user",
            OAUTH_SETUP_REQUESTS_KEY: [
                {
                    "id": "req_1",
                    "requester_user_id": "member_user",
                    "status": "pending",
                    "requested_at": "2026-03-01T12:00:00+00:00",
                }
            ],
        },
    )

    owner_status = oauth_configuration_status(user_id="owner_user")
    member_status = oauth_configuration_status(user_id="member_user")

    assert owner_status["oauth_current_user_is_owner"] is True
    assert owner_status["oauth_can_manage_config"] is True
    assert member_status["oauth_current_user_is_owner"] is False
    assert member_status["oauth_can_manage_config"] is False
    assert member_status["oauth_setup_request_pending"] is True


def test_save_google_oauth_configuration_assigns_owner_and_clears_requests(monkeypatch) -> None:
    store: dict[str, object] = {}

    def fake_read(user_id=None, include_metadata=False):  # type: ignore[no-untyped-def]
        data = dict(store)
        if not include_metadata:
            return {
                "GOOGLE_OAUTH_CLIENT_ID": str(data.get("GOOGLE_OAUTH_CLIENT_ID") or ""),
                "GOOGLE_OAUTH_CLIENT_SECRET": str(data.get("GOOGLE_OAUTH_CLIENT_SECRET") or ""),
                "GOOGLE_OAUTH_REDIRECT_URI": str(data.get("GOOGLE_OAUTH_REDIRECT_URI") or ""),
            }
        return data

    def fake_save(user_id: str, values: dict[str, object]) -> None:
        store.clear()
        store.update(values)

    monkeypatch.setattr("api.services.google.auth._oauth_store_values", fake_read)
    monkeypatch.setattr("api.services.google.auth._save_oauth_store_values", fake_save)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    status = save_google_oauth_configuration(
        user_id="owner_user",
        client_id="client_123",
        client_secret="secret_456",
        redirect_uri="http://localhost:8000/api/agent/oauth/google/callback",
    )

    assert status["oauth_ready"] is True
    assert status["oauth_current_user_is_owner"] is True
    assert store.get(OAUTH_OWNER_USER_ID_KEY) == "owner_user"
    assert str(store.get(OAUTH_OWNER_SET_AT_KEY) or "").strip() != ""
    assert store.get(OAUTH_SETUP_REQUESTS_KEY) == []


def test_queue_google_oauth_setup_request_is_idempotent(monkeypatch) -> None:
    store: dict[str, object] = {
        "GOOGLE_OAUTH_CLIENT_ID": "client_123",
        "GOOGLE_OAUTH_CLIENT_SECRET": "secret_456",
        OAUTH_OWNER_USER_ID_KEY: "owner_user",
        OAUTH_SETUP_REQUESTS_KEY: [],
    }

    def fake_read(user_id=None, include_metadata=False):  # type: ignore[no-untyped-def]
        data = dict(store)
        if not include_metadata:
            return {
                "GOOGLE_OAUTH_CLIENT_ID": str(data.get("GOOGLE_OAUTH_CLIENT_ID") or ""),
                "GOOGLE_OAUTH_CLIENT_SECRET": str(data.get("GOOGLE_OAUTH_CLIENT_SECRET") or ""),
                "GOOGLE_OAUTH_REDIRECT_URI": str(data.get("GOOGLE_OAUTH_REDIRECT_URI") or ""),
            }
        return data

    def fake_save(user_id: str, values: dict[str, object]) -> None:
        store.clear()
        store.update(values)

    monkeypatch.setattr("api.services.google.auth._oauth_store_values", fake_read)
    monkeypatch.setattr("api.services.google.auth._save_oauth_store_values", fake_save)

    first = queue_google_oauth_setup_request(user_id="member_user", note="Please enable Google login")
    second = queue_google_oauth_setup_request(user_id="member_user", note="Please enable Google login")

    pending = [row for row in list(store.get(OAUTH_SETUP_REQUESTS_KEY) or []) if row.get("status") == "pending"]
    assert first["status"] == "queued"
    assert second["status"] == "queued"
    assert len(pending) == 1
