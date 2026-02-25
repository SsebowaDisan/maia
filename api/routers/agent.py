from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from queue import Empty
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.services.agent.activity import get_activity_store
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.live_events import LiveEventSubscription, get_live_event_broker
from api.services.agent.auth.google_oauth import (
    build_google_authorize_url,
    exchange_google_oauth_code,
)
from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.governance import get_governance_service
from api.services.agent.memory import get_memory_service
from api.services.agent.report_scheduler import get_report_scheduler
from api.services.agent.tools.registry import get_tool_registry
from api.services.google.auth import (
    DEFAULT_FRONTEND_ERROR_URL,
    DEFAULT_FRONTEND_SUCCESS_URL,
    get_google_oauth_manager,
    resolve_google_redirect_uri,
)
from api.services.google.errors import GoogleServiceError
from api.services.settings_service import load_user_settings
from api.context import get_context

router = APIRouter(prefix="/api/agent", tags=["agent"])


class PlaybookCreateRequest(BaseModel):
    name: str
    prompt_template: str
    tool_ids: list[str] = Field(default_factory=list)


class PlaybookPatchRequest(BaseModel):
    name: str | None = None
    prompt_template: str | None = None
    tool_ids: list[str] | None = None


class CredentialUpsertRequest(BaseModel):
    connector_id: str
    values: dict[str, Any] = Field(default_factory=dict)


class ScheduleCreateRequest(BaseModel):
    name: str
    prompt: str
    frequency: str = Field(default="weekly")
    outputs: list[str] = Field(default_factory=lambda: ["markdown"])
    channels: list[str] = Field(default_factory=list)


class ScheduleToggleRequest(BaseModel):
    enabled: bool


class GovernancePatchRequest(BaseModel):
    global_kill_switch: bool | None = None
    tool_id: str | None = None
    tool_enabled: bool | None = None


class GoogleOAuthExchangeRequest(BaseModel):
    code: str
    redirect_uri: str | None = None
    state: str | None = None
    connector_ids: list[str] = Field(
        default_factory=lambda: [
            "google_workspace",
            "gmail",
            "google_calendar",
            "google_analytics",
            "google_ads",
        ]
    )


GOOGLE_OAUTH_CONNECTOR_IDS = [
    "google_workspace",
    "gmail",
    "google_calendar",
    "google_analytics",
    "google_ads",
]


def _mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 6:
        return "*" * len(text)
    return f"{text[:3]}{'*' * (len(text) - 6)}{text[-3:]}"


def _masked_credential_payload(values: dict[str, Any]) -> dict[str, Any]:
    masked: dict[str, Any] = {}
    for key, raw_value in values.items():
        if raw_value is None:
            masked[key] = ""
            continue
        text = str(raw_value)
        if "token" in key.lower() or "secret" in key.lower() or "password" in key.lower():
            masked[key] = _mask_secret(text)
        else:
            masked[key] = text
    return masked


def _http_error_from_google(exc: GoogleServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.to_detail())


def _oauth_error(status_code: int, code: str, message: str, **details: Any) -> HTTPException:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details:
        payload["details"] = details
    return HTTPException(status_code=status_code, detail=payload)


def _to_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


def _build_frontend_redirect(
    *,
    oauth_status: str,
    code: str | None = None,
    message: str | None = None,
) -> str:
    if oauth_status == "success":
        base_url = os.getenv("GOOGLE_OAUTH_FRONTEND_SUCCESS_URL", DEFAULT_FRONTEND_SUCCESS_URL)
    else:
        base_url = os.getenv("GOOGLE_OAUTH_FRONTEND_ERROR_URL", DEFAULT_FRONTEND_ERROR_URL)
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["oauth"] = oauth_status
    if code:
        query["code"] = code
    if message:
        query["message"] = message[:220]
    return urlunparse(parsed._replace(query=urlencode(query)))


def _store_google_connector_tokens(
    *,
    user_id: str,
    access_token: str,
    refresh_token: str,
    connector_ids: list[str],
) -> list[str]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    stored_connectors: list[str] = []
    for connector_id in connector_ids:
        if connector_id not in get_connector_registry().names():
            continue
        credential_values: dict[str, Any] = {}
        if connector_id == "google_workspace":
            credential_values["GOOGLE_WORKSPACE_ACCESS_TOKEN"] = access_token
            if refresh_token:
                credential_values["GOOGLE_WORKSPACE_REFRESH_TOKEN"] = refresh_token
        elif connector_id == "gmail":
            credential_values["GMAIL_ACCESS_TOKEN"] = access_token
            if refresh_token:
                credential_values["GMAIL_REFRESH_TOKEN"] = refresh_token
        elif connector_id == "google_calendar":
            credential_values["GOOGLE_CALENDAR_ACCESS_TOKEN"] = access_token
            if refresh_token:
                credential_values["GOOGLE_CALENDAR_REFRESH_TOKEN"] = refresh_token
        elif connector_id == "google_analytics":
            credential_values["GOOGLE_ANALYTICS_ACCESS_TOKEN"] = access_token
            if refresh_token:
                credential_values["GOOGLE_ANALYTICS_REFRESH_TOKEN"] = refresh_token
        elif connector_id == "google_ads":
            credential_values["GOOGLE_ADS_ACCESS_TOKEN"] = access_token
            if refresh_token:
                credential_values["GOOGLE_ADS_REFRESH_TOKEN"] = refresh_token
        if not credential_values:
            continue
        get_credential_store().set(
            tenant_id=tenant_id,
            connector_id=connector_id,
            values=credential_values,
        )
        stored_connectors.append(connector_id)
    return stored_connectors


@router.get("/tools")
def list_tools() -> list[dict[str, Any]]:
    return get_tool_registry().list_tools()


@router.get("/connectors/health")
def connector_health(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    return get_connector_registry().health_report(settings=settings)


@router.get("/oauth/google/start")
def start_google_oauth(
    redirect_uri: str | None = None,
    scopes: str | None = None,
    state: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    scope_list = [item.strip() for item in str(scopes or "").split(",") if item.strip()]
    try:
        payload = build_google_authorize_url(
            user_id=user_id,
            redirect_uri=redirect_uri,
            scopes=scope_list or None,
            state=state,
        )
    except GoogleServiceError as exc:
        raise _http_error_from_google(exc) from exc
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
            _build_frontend_redirect(
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
            _build_frontend_redirect(
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
            _build_frontend_redirect(
                oauth_status="error",
                code="oauth_provider_error",
                message=message,
            ),
            status_code=302,
        )
    if not code:
        return RedirectResponse(
            _build_frontend_redirect(
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
            _build_frontend_redirect(
                oauth_status="error",
                code=exc.code,
                message=exc.message,
            ),
            status_code=302,
        )

    _store_google_connector_tokens(
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
    return RedirectResponse(_build_frontend_redirect(oauth_status="success"), status_code=302)


@router.post("/oauth/google/exchange")
def exchange_google_oauth(
    payload: GoogleOAuthExchangeRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    oauth = get_google_oauth_manager()
    effective_user_id = user_id
    resolved_redirect_uri = resolve_google_redirect_uri(payload.redirect_uri)
    scopes_hint: list[str] | None = None
    if payload.state:
        try:
            state_record = oauth.consume_state(state=payload.state)
        except GoogleServiceError as exc:
            raise _http_error_from_google(exc) from exc
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
        raise _http_error_from_google(exc) from exc
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    expires_at = token_payload.get("expires_at")
    token_type = str(token_payload.get("token_type") or "Bearer")
    if not access_token:
        raise _oauth_error(
            400,
            "oauth_exchange_no_access_token",
            "OAuth exchange did not return access_token.",
        )

    connector_ids = payload.connector_ids or list(GOOGLE_OAUTH_CONNECTOR_IDS)
    stored_connectors = _store_google_connector_tokens(
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
) -> dict[str, Any]:
    oauth = get_google_oauth_manager()
    try:
        return oauth.connection_status(user_id=user_id)
    except GoogleServiceError as exc:
        raise _http_error_from_google(exc) from exc


@router.post("/oauth/google/disconnect")
def disconnect_google_oauth(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    oauth = get_google_oauth_manager()
    try:
        result = oauth.disconnect(user_id=user_id)
    except GoogleServiceError as exc:
        raise _http_error_from_google(exc) from exc

    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    cleared_connectors: list[str] = []
    for connector_id in GOOGLE_OAUTH_CONNECTOR_IDS:
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


@router.get("/events")
def stream_agent_events(
    run_id: str | None = None,
    replay: int = Query(default=40, ge=0, le=200),
    user_id: str = Depends(get_current_user_id),
):
    broker = get_live_event_broker()
    subscription = broker.subscribe(user_id=user_id, run_id=run_id, replay_limit=replay)

    def event_stream(active_subscription: LiveEventSubscription):
        try:
            yield _to_sse("ready", {"status": "subscribed", "run_id": run_id})
            while True:
                event = broker.receive(active_subscription, timeout_seconds=15)
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                yield _to_sse("event", event)
        except Empty:
            yield ": keep-alive\n\n"
        finally:
            broker.unsubscribe(active_subscription)

    return StreamingResponse(event_stream(subscription), media_type="text/event-stream")


@router.post("/connectors/credentials")
def upsert_connector_credentials(
    payload: CredentialUpsertRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    if payload.connector_id not in get_connector_registry().names():
        raise HTTPException(status_code=404, detail="Unknown connector.")
    record = get_credential_store().set(
        tenant_id=tenant_id,
        connector_id=payload.connector_id,
        values=payload.values,
    )
    return {
        "tenant_id": record.tenant_id,
        "connector_id": record.connector_id,
        "values": _masked_credential_payload(record.values),
        "date_updated": record.date_updated,
    }


@router.get("/connectors/credentials")
def list_connector_credentials(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    rows = get_credential_store().list_for_tenant(tenant_id=tenant_id)
    return [
        {
            "tenant_id": row.tenant_id,
            "connector_id": row.connector_id,
            "values": _masked_credential_payload(row.values),
            "date_updated": row.date_updated,
        }
        for row in rows
    ]


@router.delete("/connectors/credentials/{connector_id}")
def delete_connector_credentials(
    connector_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    if connector_id not in get_connector_registry().names():
        raise HTTPException(status_code=404, detail="Unknown connector.")
    deleted = get_credential_store().delete(tenant_id=tenant_id, connector_id=connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credentials not found.")
    return {"status": "deleted", "connector_id": connector_id}


@router.get("/runs")
def list_agent_runs(limit: int = 50) -> list[dict[str, Any]]:
    return get_memory_service().list_runs(limit=limit)


@router.get("/runs/{run_id}")
def get_agent_run(run_id: str) -> dict[str, Any]:
    row = get_memory_service().runs.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return row


@router.get("/runs/{run_id}/events")
def get_agent_run_events(run_id: str) -> list[dict[str, Any]]:
    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")
    return rows


@router.get("/runs/{run_id}/events/{event_id}/snapshot")
def get_agent_event_snapshot(
    run_id: str,
    event_id: str,
    user_id: str = Depends(get_current_user_id),
):
    del user_id  # Current run store is user-scoped at write time; keep endpoint signature auth-guarded.

    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")

    snapshot_ref = ""
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if str(payload.get("event_id") or "") != event_id:
            continue
        snapshot_ref = str(payload.get("snapshot_ref") or "").strip()
        break

    if not snapshot_ref:
        raise HTTPException(status_code=404, detail="Snapshot not found for this event.")

    candidate = Path(snapshot_ref).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    allowed_roots = [
        (Path.cwd() / ".maia_agent").resolve(),
        (Path.cwd() / "flow_tmp").resolve(),
    ]
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Snapshot path is outside allowed directories.")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Snapshot file is missing.")

    media_type, _ = mimetypes.guess_type(str(candidate))
    return FileResponse(
        path=str(candidate),
        media_type=media_type or "application/octet-stream",
        filename=candidate.name,
    )


@router.get("/runs/{run_id}/events/export")
def export_agent_run_events(run_id: str) -> dict[str, Any]:
    rows = get_activity_store().load_events(run_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Run events not found.")
    run_started = next((row.get("payload", {}) for row in rows if row.get("type") == "run_started"), {})
    run_completed = next(
        (row.get("payload", {}) for row in reversed(rows) if row.get("type") == "run_completed"),
        {},
    )
    events = [row.get("payload", {}) for row in rows if row.get("type") == "event"]
    return {
        "run_id": run_id,
        "run_started": run_started,
        "run_completed": run_completed,
        "total_rows": len(rows),
        "total_events": len(events),
        "events": events,
    }


@router.get("/playbooks")
def list_playbooks(limit: int = 50) -> list[dict[str, Any]]:
    return get_memory_service().list_playbooks(limit=limit)


@router.post("/playbooks")
def create_playbook(
    payload: PlaybookCreateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    return get_memory_service().save_playbook(
        name=payload.name,
        prompt_template=payload.prompt_template,
        tool_ids=payload.tool_ids,
        owner_id=user_id,
    )


@router.patch("/playbooks/{playbook_id}")
def patch_playbook(
    playbook_id: str,
    payload: PlaybookPatchRequest,
) -> dict[str, Any]:
    patch = payload.model_dump(exclude_none=True)
    return get_memory_service().update_playbook(playbook_id, patch)


@router.get("/schedules")
def list_schedules(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    return get_report_scheduler().list(user_id=user_id)


@router.post("/schedules")
def create_schedule(
    payload: ScheduleCreateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    if payload.frequency not in {"daily", "weekly", "monthly"}:
        raise HTTPException(status_code=400, detail="frequency must be one of: daily, weekly, monthly")
    return get_report_scheduler().create(
        user_id=user_id,
        name=payload.name,
        prompt=payload.prompt,
        frequency=payload.frequency,  # type: ignore[arg-type]
        outputs=payload.outputs,
        channels=payload.channels,
    )


@router.post("/schedules/{schedule_id}/trigger")
def trigger_schedule_now(
    schedule_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        return get_report_scheduler().trigger_now(user_id=user_id, schedule_id=schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/schedules/{schedule_id}")
def toggle_schedule(
    schedule_id: str,
    payload: ScheduleToggleRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        return get_report_scheduler().toggle(
            user_id=user_id,
            schedule_id=schedule_id,
            enabled=payload.enabled,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    try:
        get_report_scheduler().delete(user_id=user_id, schedule_id=schedule_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "schedule_id": schedule_id}


@router.get("/governance")
def get_governance() -> dict[str, Any]:
    return get_governance_service().get()


@router.patch("/governance")
def patch_governance(payload: GovernancePatchRequest) -> dict[str, Any]:
    service = get_governance_service()
    result = service.get()
    if payload.global_kill_switch is not None:
        result = service.set_global_kill_switch(payload.global_kill_switch)
    if payload.tool_id and payload.tool_enabled is not None:
        result = service.set_tool_enabled(payload.tool_id, payload.tool_enabled)
    return result
