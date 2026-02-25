from __future__ import annotations

from pathlib import Path

import pytest

from api.services.google.auth import GoogleOAuthManager
from api.services.google.errors import GoogleOAuthError
from api.services.google.store import GoogleTokenStore, OAuthStateStore


def test_google_token_store_save_get_clear(tmp_path: Path) -> None:
    store = GoogleTokenStore(path=tmp_path / "tokens.json")

    saved = store.save_tokens(
        user_id="user_1",
        access_token="access_123",
        refresh_token="refresh_abc",
        scopes=["openid", "email"],
        token_type="Bearer",
        expires_in=3600,
    )
    loaded = store.get_tokens(user_id="user_1")

    assert loaded is not None
    assert loaded.access_token == "access_123"
    assert loaded.refresh_token == "refresh_abc"
    assert loaded.scopes == ["openid", "email"]
    assert loaded.expires_at is not None
    assert saved.user_id == loaded.user_id

    assert store.clear_tokens(user_id="user_1") is True
    assert store.get_tokens(user_id="user_1") is None


def test_oauth_state_store_consume_once(tmp_path: Path) -> None:
    store = OAuthStateStore(path=tmp_path / "state.json", ttl_seconds=600)
    created = store.create_state(
        state="state_1",
        user_id="user_1",
        redirect_uri="http://localhost:8000/api/agent/oauth/google/callback",
        scopes=["openid", "email"],
    )

    consumed = store.consume_state(state="state_1")
    consumed_again = store.consume_state(state="state_1")

    assert consumed is not None
    assert consumed.user_id == "user_1"
    assert consumed.redirect_uri == created.redirect_uri
    assert consumed_again is None


def test_oauth_manager_rejects_invalid_state(tmp_path: Path) -> None:
    manager = GoogleOAuthManager()
    manager.tokens = GoogleTokenStore(path=tmp_path / "tokens.json")
    manager.states = OAuthStateStore(path=tmp_path / "state.json", ttl_seconds=600)

    with pytest.raises(GoogleOAuthError) as exc_info:
        manager.consume_state(state="missing_state")

    assert exc_info.value.code == "oauth_state_invalid"
    assert exc_info.value.status_code == 401

