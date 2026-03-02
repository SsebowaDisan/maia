from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.auth import get_current_user_id


def test_get_current_user_id_prefers_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIA_REQUIRE_EXPLICIT_USER_ID", raising=False)
    monkeypatch.delenv("MAIA_DEV_DEFAULT_USER_ID", raising=False)

    assert get_current_user_id(x_user_id="header-user", user_id="query-user") == "header-user"


def test_get_current_user_id_accepts_query_for_sse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAIA_REQUIRE_EXPLICIT_USER_ID", raising=False)
    monkeypatch.delenv("MAIA_DEV_DEFAULT_USER_ID", raising=False)

    assert get_current_user_id(x_user_id=None, user_id="stream-user") == "stream-user"


def test_get_current_user_id_uses_dev_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIA_DEV_DEFAULT_USER_ID", "dev-user")
    monkeypatch.setenv("MAIA_REQUIRE_EXPLICIT_USER_ID", "false")

    assert get_current_user_id(x_user_id=None, user_id=None) == "dev-user"


def test_get_current_user_id_requires_explicit_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAIA_REQUIRE_EXPLICIT_USER_ID", "true")
    monkeypatch.setenv("MAIA_DEV_DEFAULT_USER_ID", "")

    with pytest.raises(HTTPException) as exc_info:
        get_current_user_id(x_user_id=None, user_id=None)

    assert exc_info.value.status_code == 401
