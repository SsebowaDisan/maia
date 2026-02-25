from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.google.auth import GoogleOAuthManager
from api.services.google.store import GoogleTokenStore, OAuthStateStore


class _FakeHttpResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_google_refresh_flow_uses_refresh_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client_123")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret_456")

    manager = GoogleOAuthManager()
    manager.tokens = GoogleTokenStore(path=tmp_path / "tokens.json")
    manager.states = OAuthStateStore(path=tmp_path / "state.json", ttl_seconds=600)
    manager.tokens.save_tokens(
        user_id="user_1",
        access_token="expired_access",
        refresh_token="refresh_abc",
        token_type="Bearer",
        scopes=["openid"],
        expires_in=-30,
    )

    observed_bodies: list[str] = []

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        body = request.data.decode("utf-8") if request.data else ""
        observed_bodies.append(body)
        assert request.full_url == "https://oauth2.googleapis.com/token"
        return _FakeHttpResponse(
            {
                "access_token": "new_access_token",
                "token_type": "Bearer",
                "expires_in": 1800,
                "scope": "openid email",
            }
        )

    monkeypatch.setattr("api.services.google.auth.urlopen", fake_urlopen)

    refreshed = manager.refresh_tokens(user_id="user_1")

    assert refreshed.access_token == "new_access_token"
    assert refreshed.refresh_token == "refresh_abc"
    assert refreshed.scopes == ["openid", "email"]
    assert any("refresh_token=refresh_abc" in body for body in observed_bodies)

