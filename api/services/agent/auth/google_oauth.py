from __future__ import annotations

from typing import Any

from api.services.google.auth import (
    build_google_authorize_url as build_google_authorize_url_v2,
    exchange_google_oauth_code as exchange_google_oauth_code_v2,
    resolve_google_redirect_uri,
)


def build_google_authorize_url(
    *,
    user_id: str = "default",
    redirect_uri: str | None = None,
    scopes: list[str] | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    return build_google_authorize_url_v2(
        user_id=user_id,
        redirect_uri=redirect_uri or resolve_google_redirect_uri(user_id=user_id),
        scopes=scopes,
        state=state,
    )


def exchange_google_oauth_code(
    *,
    user_id: str = "default",
    code: str,
    redirect_uri: str | None = None,
    scopes_hint: list[str] | None = None,
) -> dict[str, Any]:
    record = exchange_google_oauth_code_v2(
        user_id=user_id,
        code=code,
        redirect_uri=(redirect_uri or resolve_google_redirect_uri(user_id=user_id)),
        scopes_hint=scopes_hint,
    )
    return {
        "access_token": record.access_token,
        "refresh_token": record.refresh_token,
        "token_type": record.token_type,
        "scope": " ".join(record.scopes),
        "expires_at": record.expires_at,
        "id_token": record.id_token,
    }
