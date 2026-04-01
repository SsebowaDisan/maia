from __future__ import annotations

from api.models.user import User
from api.routers import users as users_router


def _user(user_id: str, *, email: str, role: str, tenant_id: str | None, is_active: bool = True) -> User:
    return User(
        id=user_id,
        email=email,
        hashed_password="x",
        full_name=user_id,
        role=role,
        tenant_id=tenant_id,
        is_active=is_active,
    )


def test_invite_user_returns_copyable_link_and_email_metadata(monkeypatch) -> None:
    actor = _user("admin-1", email="francis.declercq@axongroup.com", role="super_admin", tenant_id=None)
    created = _user(
        "new-user-1",
        email="new.user@example.com",
        role="org_user",
        tenant_id=None,
    )

    monkeypatch.setattr("api.services.auth.store.get_user_by_email", lambda _email: None)
    monkeypatch.setattr(users_router, "create_user", lambda **_kwargs: created)
    monkeypatch.setattr(users_router, "add_member", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(users_router, "create_invite_token", lambda **_kwargs: "invite-token-123")
    monkeypatch.setattr(users_router, "decode_invite_token", lambda _token: {"exp": 1893456000})
    monkeypatch.setattr(users_router, "_build_invite_link", lambda _token: "http://127.0.0.1:5173/accept-invite?token=invite-token-123")
    monkeypatch.setattr(users_router, "send_invite_email", lambda **_kwargs: (True, None))

    result = users_router.invite_user(
        body=users_router.InviteRequest(
            email="new.user@example.com",
            full_name="New User",
            role="org_user",
            send_invite_email=True,
        ),
        actor=actor,
    )

    assert result.user.email == "new.user@example.com"
    assert result.invite_link.startswith("http://127.0.0.1:5173/accept-invite?token=")
    assert result.email_sent is True
    assert result.email_error is None
