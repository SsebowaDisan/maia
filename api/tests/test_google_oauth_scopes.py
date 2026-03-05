from __future__ import annotations

import pytest

from api.services.google.errors import GoogleTokenError
from api.services.google.oauth_scopes import (
    default_oauth_scopes,
    enabled_tool_ids_from_scopes,
    expand_scopes_for_tool_ids,
    missing_scopes,
)
from api.services.google.session import GoogleAuthSession


def test_default_oauth_scopes_include_calendar_and_workspace() -> None:
    scopes = default_oauth_scopes()
    assert "https://www.googleapis.com/auth/calendar.events" in scopes
    assert "https://www.googleapis.com/auth/drive" in scopes
    assert "https://www.googleapis.com/auth/documents" in scopes
    assert "https://www.googleapis.com/auth/spreadsheets" in scopes


def test_expand_scopes_for_selected_tools() -> None:
    scopes = expand_scopes_for_tool_ids(["gmail", "google_analytics"])
    assert "openid" in scopes
    assert "email" in scopes
    assert "https://www.googleapis.com/auth/gmail.send" in scopes
    assert "https://www.googleapis.com/auth/analytics.readonly" in scopes
    assert "https://www.googleapis.com/auth/drive" not in scopes


def test_missing_scopes_accepts_gmail_super_scope() -> None:
    missing = missing_scopes(
        required_scopes=["https://www.googleapis.com/auth/gmail.send"],
        granted_scopes=["https://mail.google.com/"],
    )
    assert missing == []


def test_enabled_tools_resolved_from_granted_scopes() -> None:
    scopes = expand_scopes_for_tool_ids(["google_workspace", "google_analytics"])
    enabled = enabled_tool_ids_from_scopes(scopes)
    assert "google_workspace" in enabled
    assert "google_analytics" in enabled
    assert "gmail" not in enabled


def test_google_auth_session_enforces_required_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "api.services.google.session.resolve_google_auth_mode",
        lambda settings=None: "oauth",
    )
    session = GoogleAuthSession(
        user_id="user_1",
        fallback_tokens={
            "access_token": "token_123",
            "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
        },
    )
    with pytest.raises(GoogleTokenError) as exc:
        session.require_scopes(
            ["https://www.googleapis.com/auth/gmail.send"],
            reason="Gmail send",
        )
    assert exc.value.code == "google_scopes_missing"
