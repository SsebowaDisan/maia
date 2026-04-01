from __future__ import annotations

import pytest

from api.services.auth.tokens import (
    TokenError,
    create_access_token,
    create_invite_token,
    decode_invite_token,
)


def test_invite_token_round_trip() -> None:
    token = create_invite_token(
        user_id="u-invite-1",
        email="invitee@example.com",
        role="org_user",
        tenant_id="tenant-1",
        invited_by="admin-1",
        full_name="Invitee User",
    )

    payload = decode_invite_token(token)

    assert payload["type"] == "invite"
    assert payload["sub"] == "u-invite-1"
    assert payload["email"] == "invitee@example.com"
    assert payload["role"] == "org_user"
    assert payload["tid"] == "tenant-1"
    assert payload["invited_by"] == "admin-1"


def test_invite_decoder_rejects_access_token() -> None:
    access = create_access_token(
        user_id="u-1",
        email="u-1@example.com",
        role="org_admin",
        tenant_id="tenant-1",
    )

    with pytest.raises(TokenError):
        decode_invite_token(access)
