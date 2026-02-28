from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from api.auth import get_current_user_id
from api.services.agent.auth.google_oauth import (
    build_google_authorize_url,
    exchange_google_oauth_code,
)
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.live_events import get_live_event_broker
from api.services.google.auth import (
    get_google_oauth_manager,
    resolve_google_redirect_uri,
)
from api.services.google.errors import GoogleServiceError

from .common import (
    build_frontend_redirect,
    http_error_from_google,
    oauth_error,
    store_google_connector_tokens,
    tenant_id_for_user,
)
from .schemas import GOOGLE_OAUTH_CONNECTOR_IDS, GoogleOAuthExchangeRequest

router = APIRouter(tags=["agent"])


@router.get("/oauth/google/start")
def start_google_oauth(
    redirect_uri: str | None = None,
    scopes: str | None = None,
    state: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    scope_list = [item.strip() for item in str(scopes or "").split(",") if item.strip()]
    try:
        payload = build_google_authorize_url(
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scope_list or None,
            state=state,
        )
    except GoogleServiceError as exc:
        raise http_error_from_google(exc) from exc
    get_live_event_broker().publish(
        user_id=user_id,
        run_id=None,
        event={
            "type": "oauth.start",
            "message": "Google OAuth flow started",
            "data": {"redirect_uri": payload.get("redirect_uri"), "scopes": payload.get("scopes", [])},
        },
    )
    return payload


@router.get("/oauth/google/callback")
def google_oauth_callback(
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    oauth = get_google_oauth_manager()
    if not state:
        return RedirectResponse(
            build_frontend_redirect(
                oauth_status="error",
                code="oauth_state_missing",
                message="Missing OAuth state.",
            ),
            status_code=302,
        )

    try:
        state_record = oauth.consume_state(state=state)
    except GoogleServiceError:
        return RedirectResponse(
            build_frontend_redirect(
                oauth_status="error",
                code="oauth_state_invalid",
                message="OAuth state is invalid or expired.",
            ),
            status_code=302,
        )

    if error:
        message = error_description or error
        get_live_event_broker().publish(
            user_id=state_record.user_id,
            run_id=None,
            event={
                "type": "oauth.error",
                "message": "Google OAuth callback returned an error",
                "data": {"error": error, "error_description": error_description or ""},
            },
        )
        return RedirectResponse(
            build_frontend_redirect(
                oauth_status="error",
                code="oauth_provider_error",
                message=message,
            ),
            status_code=302,
        )
    if not code:
        return RedirectResponse(
            build_frontend_redirect(
                oauth_status="error",
                code="oauth_code_missing",
                message="Google did not return an authorization code.",
            ),
            status_code=302,
        )

    try:
        token_record = oauth.exchange_code(
            code=code,
            user_id=state_record.user_id,
            redirect_uri=state_record.redirect_uri,
            scopes_hint=state_record.scopes,
        )
    except GoogleServiceError as exc:
        return RedirectResponse(
            build_frontend_redirect(
                oauth_status="error",
                code=exc.code,
                message=exc.message,
            ),
            status_code=302,
        )

    store_google_connector_tokens(
        user_id=state_record.user_id,
        access_token=token_record.access_token,
        refresh_token=token_record.refresh_token,
        connector_ids=list(GOOGLE_OAUTH_CONNECTOR_IDS),
    )
    get_live_event_broker().publish(
        user_id=state_record.user_id,
        run_id=None,
        event={
            "type": "oauth.connected",
            "message": "Google OAuth connected successfully",
            "data": {"scopes": token_record.scopes, "expires_at": token_record.expires_at},
        },
    )
    return RedirectResponse(build_frontend_redirect(oauth_status="success"), status_code=302)


@router.post("/oauth/google/exchange")
def exchange_google_oauth(
    payload: GoogleOAuthExchangeRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    oauth = get_google_oauth_manager()
    effective_user_id = user_id
    resolved_redirect_uri = resolve_google_redirect_uri(payload.redirect_uri)
    scopes_hint: list[str] | None = None
    if payload.state:
        try:
            state_record = oauth.consume_state(state=payload.state)
        except GoogleServiceError as exc:
            raise http_error_from_google(exc) from exc
        effective_user_id = state_record.user_id
        if not payload.redirect_uri:
            resolved_redirect_uri = state_record.redirect_uri
        scopes_hint = state_record.scopes

    try:
        token_payload = exchange_google_oauth_code(
            user_id=effective_user_id,
            code=payload.code,
            redirect_uri=resolved_redirect_uri,
            scopes_hint=scopes_hint,
        )
    except GoogleServiceError as exc:
        raise http_error_from_google(exc) from exc
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    expires_at = token_payload.get("expires_at")
    token_type = str(token_payload.get("token_type") or "Bearer")
    if not access_token:
        raise oauth_error(
            400,
            "oauth_exchange_no_access_token",
            "OAuth exchange did not return access_token.",
        )

    connector_ids = payload.connector_ids or list(GOOGLE_OAUTH_CONNECTOR_IDS)
    stored_connectors = store_google_connector_tokens(
        user_id=effective_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        connector_ids=connector_ids,
    )
    get_live_event_broker().publish(
        user_id=effective_user_id,
        run_id=None,
        event={
            "type": "oauth.exchange",
            "message": "Google OAuth exchange completed",
            "data": {"connector_count": len(stored_connectors)},
        },
    )

    return {
        "status": "ok",
        "stored_connectors": stored_connectors,
        "token_type": token_type,
        "expires_at": expires_at,
        "refresh_token_stored": bool(refresh_token),
        "deprecated": True,
        "warning": "Use /api/agent/oauth/google/callback for the preferred OAuth flow.",
    }


@router.get("/oauth/google/status")
def google_oauth_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    oauth = get_google_oauth_manager()
    try:
        return oauth.connection_status(user_id=user_id)
    except GoogleServiceError as exc:
        raise http_error_from_google(exc) from exc


@router.post("/oauth/google/disconnect")
def disconnect_google_oauth(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    oauth = get_google_oauth_manager()
    try:
        result = oauth.disconnect(user_id=user_id)
    except GoogleServiceError as exc:
        raise http_error_from_google(exc) from exc

    tenant_id = tenant_id_for_user(user_id)
    cleared_connectors: list[str] = []
    for connector_id in GOOGLE_OAUTH_CONNECTOR_IDS:
        if connector_id not in get_connector_registry().names():
            continue
        if get_credential_store().delete(tenant_id=tenant_id, connector_id=connector_id):
            cleared_connectors.append(connector_id)

    get_live_event_broker().publish(
        user_id=user_id,
        run_id=None,
        event={
            "type": "oauth.disconnected",
            "message": "Google OAuth disconnected",
            "data": {"cleared_connectors": cleared_connectors},
        },
    )
    return {
        **result,
        "cleared_connectors": cleared_connectors,
    }
