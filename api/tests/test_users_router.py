from __future__ import annotations

from api.models.user import User
from api.routers import users as users_router


def _user(user_id: str, *, role: str, tenant_id: str | None) -> User:
    return User(
        id=user_id,
        email=f"{user_id}@example.com",
        hashed_password="x",
        full_name=user_id,
        role=role,
        tenant_id=tenant_id,
        is_active=True,
    )


def test_list_users_super_admin_gets_all_active_users(monkeypatch) -> None:
    rows = [
        _user("u-1", role="org_admin", tenant_id="t-1"),
        _user("u-2", role="org_user", tenant_id="t-2"),
    ]
    monkeypatch.setattr(users_router, "list_all_active_users", lambda: rows)

    result = users_router.list_users(actor=_user("root", role="super_admin", tenant_id=None))

    assert [row.id for row in result] == ["u-1", "u-2"]


def test_list_users_org_admin_is_tenant_scoped(monkeypatch) -> None:
    actor = _user("admin-1", role="org_admin", tenant_id="t-1")
    rows = [
        _user("u-1", role="org_admin", tenant_id="t-1"),
        _user("u-2", role="org_user", tenant_id="t-1"),
    ]
    monkeypatch.setattr(users_router, "list_users_for_tenant", lambda tenant_id: rows if tenant_id == "t-1" else [])

    result = users_router.list_users(actor=actor)

    assert [row.id for row in result] == ["u-1", "u-2"]

