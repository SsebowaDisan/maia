from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import auth
from api.models.user import User


def _user(user_id: str, *, role: str = "org_user") -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="x",
        role=role,
        tenant_id="tenant-1",
        is_active=True,
    )


def test_registered_user_gate_rejects_non_db_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_user", lambda _user_id: None)

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_registered_user(_user("ghost"))

    assert exc_info.value.status_code == 401
    assert "invited account" in str(exc_info.value.detail).lower()


def test_registered_user_gate_accepts_db_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = _user("member-1")
    monkeypatch.setattr(auth, "get_user", lambda _user_id: stored)

    resolved = auth.get_current_registered_user(_user("member-1"))

    assert resolved.id == "member-1"

