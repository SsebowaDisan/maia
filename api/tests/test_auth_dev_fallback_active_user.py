from __future__ import annotations

import pytest

from api import auth
from api.models.user import User


def _user(user_id: str, email: str, *, role: str, is_active: bool) -> User:
    return User(
        id=user_id,
        email=email,
        hashed_password="x",
        role=role,
        tenant_id=None,
        is_active=is_active,
    )


def test_dev_fallback_prefers_active_super_admin_when_resolved_user_inactive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inactive_default = _user("default", "admin@micrurus.com", role="org_admin", is_active=False)
    francis = _user("francis-id", "francis.declercq@axongroup.com", role="super_admin", is_active=True)

    monkeypatch.setattr(auth, "_AUTH_DISABLED", True)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda user_id: inactive_default if user_id == "default" else (francis if user_id == "francis-id" else None),
    )
    monkeypatch.setattr(auth, "list_all_active_users", lambda: [francis])

    resolved = auth.get_current_user(credentials=None, x_user_id="default", user_id_query=None)

    assert resolved.id == "francis-id"
    assert resolved.email == "francis.declercq@axongroup.com"


def test_dev_fallback_uses_active_super_admin_for_inactive_dev_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inactive_default = _user("default", "admin@micrurus.com", role="org_admin", is_active=False)
    francis = _user("francis-id", "francis.declercq@axongroup.com", role="super_admin", is_active=True)

    monkeypatch.setattr(auth, "_AUTH_DISABLED", True)
    monkeypatch.setenv("MAIA_DEV_DEFAULT_USER_ID", "default")
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda user_id: inactive_default if user_id == "default" else (francis if user_id == "francis-id" else None),
    )
    monkeypatch.setattr(auth, "list_all_active_users", lambda: [francis])

    resolved = auth.get_current_user(credentials=None, x_user_id=None, user_id_query=None)

    assert resolved.id == "francis-id"
    assert resolved.email == "francis.declercq@axongroup.com"


def test_dev_fallback_keeps_explicit_active_user(monkeypatch: pytest.MonkeyPatch) -> None:
    francis = _user("francis-id", "francis.declercq@axongroup.com", role="super_admin", is_active=True)
    other = _user("other-id", "other@example.com", role="org_admin", is_active=True)

    monkeypatch.setattr(auth, "_AUTH_DISABLED", True)
    monkeypatch.setattr(
        auth,
        "get_user",
        lambda user_id: francis if user_id == "francis-id" else (other if user_id == "other-id" else None),
    )
    monkeypatch.setattr(auth, "list_all_active_users", lambda: [other, francis])

    resolved = auth.get_current_user(credentials=None, x_user_id="francis-id", user_id_query=None)

    assert resolved.id == "francis-id"
    assert resolved.email == "francis.declercq@axongroup.com"
