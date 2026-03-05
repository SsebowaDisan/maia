from __future__ import annotations

import json

import pytest

from api.services.google.errors import GoogleTokenError
from api.services.google.service_account import (
    resolve_google_auth_mode,
    resolve_service_account_profile,
)
from api.services.google.session import GoogleAuthSession


class _OAuthStub:
    def ensure_valid_tokens(self, *, user_id: str):  # pragma: no cover - should not be called in SA mode
        raise AssertionError("ensure_valid_tokens should not be called in service-account mode")


@pytest.mark.usefixtures("monkeypatch")
def test_resolve_google_auth_mode_defaults_to_oauth(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_AUTH_MODE", raising=False)
    assert resolve_google_auth_mode(settings={}) == "oauth"
    assert resolve_google_auth_mode(settings={"agent.google_auth_mode": "service_account"}) == "service_account"


def test_resolve_service_account_profile_email_only(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", raising=False)
    monkeypatch.delenv("MAIA_GMAIL_SA_JSON_PATH", raising=False)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "maia-mailer@example.iam.gserviceaccount.com")

    profile = resolve_service_account_profile(settings={"agent.google_auth_mode": "service_account"})
    assert profile.configured is True
    assert profile.usable is False
    assert profile.email == "maia-mailer@example.iam.gserviceaccount.com"
    assert profile.auth_mode == "service_account"


def test_resolve_service_account_profile_from_json_path(monkeypatch, tmp_path) -> None:
    payload = {
        "type": "service_account",
        "project_id": "demo-project",
        "private_key_id": "abc123",
        "private_key": "-----BEGIN PRIVATE KEY-----\\nFAKE\\n-----END PRIVATE KEY-----\\n",
        "client_email": "maia-mailer@demo-project.iam.gserviceaccount.com",
        "client_id": "106075207775874903847",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    key_path = tmp_path / "sa.json"
    key_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", str(key_path))

    profile = resolve_service_account_profile(settings={})
    assert profile.configured is True
    assert profile.usable is True
    assert profile.email == payload["client_email"]
    assert profile.project_id == payload["project_id"]


def test_google_auth_session_service_account_mode_uses_service_token(monkeypatch) -> None:
    monkeypatch.setattr("api.services.google.auth.get_google_oauth_manager", lambda: _OAuthStub())
    monkeypatch.setattr(
        "api.services.google.session.issue_service_account_access_token",
        lambda **kwargs: "sa-access-token",
    )

    session = GoogleAuthSession(
        user_id="user-1",
        settings={"agent.google_auth_mode": "service_account"},
    )
    assert session.require_access_token() == "sa-access-token"


def test_google_auth_session_oauth_mode_missing_token_has_clear_message(monkeypatch) -> None:
    class _TokenStoreStub:
        @staticmethod
        def get_tokens(*, user_id: str):  # pragma: no cover - deterministic stub
            _ = user_id
            return None

    class _MissingOAuthStub:
        tokens = _TokenStoreStub()

        def ensure_valid_tokens(self, *, user_id: str):
            raise GoogleTokenError(
                code="google_tokens_missing",
                message="No token",
                status_code=401,
            )

    monkeypatch.setattr("api.services.google.auth.get_google_oauth_manager", lambda: _MissingOAuthStub())
    session = GoogleAuthSession(user_id="user-2", settings={"agent.google_auth_mode": "oauth"})
    with pytest.raises(GoogleTokenError) as exc_info:
        session.require_access_token()
    assert "switch auth mode to service_account" in str(exc_info.value).lower()
