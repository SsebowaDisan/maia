from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.models.user import User
from api.routers.uploads import _assert_upload_write_allowed


def _user(role: str) -> User:
    return User(
        id=f"{role}-user",
        email=f"{role}@example.com",
        hashed_password="x",
        role=role,
        tenant_id="tenant-1",
        is_active=True,
    )


def test_org_user_cannot_write_persistent_library() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _assert_upload_write_allowed(_user("org_user"), "persistent")
    assert exc_info.value.status_code == 403


def test_org_user_can_upload_chat_temp_attachments() -> None:
    _assert_upload_write_allowed(_user("org_user"), "chat_temp")


def test_admin_can_write_persistent_library() -> None:
    _assert_upload_write_allowed(_user("org_admin"), "persistent")
    _assert_upload_write_allowed(_user("super_admin"), "persistent")

