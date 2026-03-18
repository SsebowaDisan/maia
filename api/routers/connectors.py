"""Connectors router — catalog, credentials, OAuth, health, and binding endpoints.

Responsibility: HTTP layer only. All logic delegated to services/connectors/.
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.services.connectors import catalog, vault
from api.services.connectors import oauth as oauth_service
from api.services.connectors import bindings as bindings_service
from api.services.connectors import webhooks as webhooks_service
from api.services.connectors.oauth import OAuthError
from api.services.connectors.tool_executor import execute_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/connectors", tags=["connectors"])


# ── Shared helpers ─────────────────────────────────────────────────────────

def _tenant(user_id: str) -> str:
    """Derive tenant_id from user_id (1:1 mapping for single-tenant deployments)."""
    return user_id


def _emit_connector_theatre_event(
    user_id: str,
    connector_id: str,
    event_type: str,
    detail: str,
) -> None:
    """Publish a theatre-friendly event so setup/test progress is visible in theatre."""
    try:
        from api.services.agent.live_events import get_live_event_broker
        from api.services.connectors.product_meta import PRODUCT_META

        meta = PRODUCT_META.get(connector_id, {})
        get_live_event_broker().publish(
            user_id=user_id,
            run_id=None,
            event={
                "event_type": event_type,
                "title": f"Connector: {connector_id}",
                "detail": detail,
                "stage": "execute",
                "status": "completed" if "completed" in event_type else ("failed" if "failed" in event_type else "running"),
                "data": {
                    "event_type": event_type,
                    "connector_id": connector_id,
                    "connector_label": meta.get("brand_slug", connector_id).replace("_", " ").title(),
                    "brand_slug": meta.get("brand_slug", connector_id),
                    "scene_family": meta.get("scene_family", "api"),
                    "operation_label": event_type.replace("connector_", "").replace("_", " ").title(),
                },
            },
        )
    except Exception:
        logger.debug("Failed to emit theatre event for %s", connector_id, exc_info=True)


def _oauth_popup_result_html(*, success: bool, message: str = "") -> HTMLResponse:
    """Return a popup-safe HTML response that notifies opener and closes."""
    payload_success = "true" if success else "false"
    safe_message = (
        message.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", " ")
        .replace("\r", " ")
    )
    html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>OAuth Complete</title>
  </head>
  <body>
    <script>
      (function () {{
        var payload = {{
          type: 'oauth_complete',
          success: {payload_success},
          error: '{safe_message}'
        }};
        try {{
          if (window.opener && !window.opener.closed) {{
            window.opener.postMessage(payload, '*');
          }}
        }} finally {{
          window.close();
        }}
      }})();
    </script>
  </body>
</html>"""
    return HTMLResponse(content=html)


# ── Request / Response bodies ──────────────────────────────────────────────

class ApiKeyCredentialRequest(BaseModel):
    api_key: str


class BasicCredentialRequest(BaseModel):
    username: str
    password: str


class CredentialUpsertRequest(BaseModel):
    values: dict[str, Any]
    auth_strategy: str | None = None


class OAuthStartResponse(BaseModel):
    auth_url: str
    state: str
    connector_id: str
    scopes: list[str]


class BindingPermissionsRequest(BaseModel):
    allowed_agent_ids: list[str] | None = None
    enabled_tool_ids: list[str] | None = None


class ToolExecuteRequest(BaseModel):
    agent_id: str
    tool_id: str
    params: dict[str, Any] = {}


class WebhookRegisterRequest(BaseModel):
    event_types: list[str]
    base_url: str = ""
    extra_params: dict[str, Any] = {}


# ── Catalog ────────────────────────────────────────────────────────────────

@router.get("", summary="List all available connectors")
def list_connectors(
    user_id: Annotated[str, Depends(get_current_user_id)],
    include_internal: bool = False,
) -> list[dict[str, Any]]:
    """Return ConnectorDefinitionSchema for every registered connector.

    Internal/runtime connectors are excluded by default. Pass
    ``include_internal=true`` to include them (admin use only).
    """
    definitions = catalog.list_definitions(
        include_internal=include_internal,
        tenant_id=_tenant(user_id),
    )
    return [d.model_dump(mode="json") for d in definitions]


@router.get("/webhooks", summary="List active webhooks for this tenant")
def list_webhooks(
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> list[dict[str, Any]]:
    registrations = webhooks_service.list_webhooks(_tenant(user_id))
    return [
        {
            "id": r.id,
            "connector_id": r.connector_id,
            "event_types": r.event_types_json,
            "receiver_url": r.receiver_url,
            "external_hook_id": r.external_hook_id,
            "active": r.active,
            "created_at": r.created_at,
        }
        for r in registrations
    ]


@router.delete(
    "/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Deregister a webhook",
)
def deregister_webhook(
    webhook_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    removed = webhooks_service.deregister_webhook(_tenant(user_id), webhook_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Webhook not found.")


@router.get("/{connector_id}", summary="Get a single connector definition")
def get_connector(
    connector_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    definition = catalog.get_definition(connector_id, tenant_id=_tenant(user_id))
    if not definition:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found.")
    return definition.model_dump(mode="json")


# ── Credentials (API key / basic auth) ─────────────────────────────────────

def _mirror_to_legacy_store(tenant_id: str, connector_id: str, values: dict[str, Any]) -> None:
    """Mirror credentials to the legacy file-based ConnectorCredentialStore."""
    try:
        from api.services.agent.auth.credentials import get_credential_store
        get_credential_store().set(tenant_id=tenant_id, connector_id=connector_id, values=values)
    except Exception:
        logger.debug("Legacy credential mirror failed for %s", connector_id, exc_info=True)


@router.post("/{connector_id}/credentials/api-key", status_code=status.HTTP_201_CREATED)
def store_api_key(
    connector_id: str,
    body: ApiKeyCredentialRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Store an API key credential for this tenant+connector."""
    definition = catalog.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found.")

    values = {"api_key": body.api_key}
    vault.store_credential(_tenant(user_id), connector_id, values, auth_strategy="api_key")
    _mirror_to_legacy_store(_tenant(user_id), connector_id, values)
    _emit_connector_theatre_event(user_id, connector_id, "connector_setup_completed", "API key stored successfully.")
    return {"status": "stored", "connector_id": connector_id}


@router.post("/{connector_id}/credentials/basic", status_code=status.HTTP_201_CREATED)
def store_basic_credential(
    connector_id: str,
    body: BasicCredentialRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Store basic auth credentials (username + password) for this tenant+connector."""
    definition = catalog.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found.")

    values = {"username": body.username, "password": body.password}
    vault.store_credential(_tenant(user_id), connector_id, values, auth_strategy="basic")
    _mirror_to_legacy_store(_tenant(user_id), connector_id, values)
    return {"status": "stored", "connector_id": connector_id}


@router.post("/{connector_id}/credentials", status_code=status.HTTP_201_CREATED)
def upsert_credential(
    connector_id: str,
    body: CredentialUpsertRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Store arbitrary connector credentials for this tenant+connector."""
    definition = catalog.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found.")

    values = {str(k): str(v) for k, v in (body.values or {}).items() if str(k).strip()}
    if not values:
        raise HTTPException(status_code=400, detail="Credential values cannot be empty.")

    auth_strategy = (
        str(body.auth_strategy or "").strip().lower() or str(definition.auth_kind or "api_key")
    )
    if auth_strategy == "service_identity":
        auth_strategy = "api_key"

    vault.store_credential(_tenant(user_id), connector_id, values, auth_strategy=auth_strategy)
    _mirror_to_legacy_store(_tenant(user_id), connector_id, values)
    return {"status": "stored", "connector_id": connector_id}


@router.delete("/{connector_id}/credentials", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def revoke_credential(
    connector_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> None:
    """Revoke and clear all stored credentials for this tenant+connector."""
    revoked = vault.revoke_credential(_tenant(user_id), connector_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="No credentials found for this connector.")


# ── OAuth2 PKCE flow ───────────────────────────────────────────────────────

@router.get("/{connector_id}/oauth/start", response_model=OAuthStartResponse)
def oauth_start(
    connector_id: str,
    redirect_uri: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> OAuthStartResponse:
    """Begin the OAuth2 PKCE flow. Returns the authorization URL to redirect the user to."""
    try:
        result = oauth_service.build_auth_url(
            connector_id=connector_id,
            tenant_id=_tenant(user_id),
            redirect_uri=redirect_uri,
        )
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    return OAuthStartResponse(
        auth_url=result["auth_url"],
        state=result["state"],
        connector_id=connector_id,
        scopes=result["scopes"],
    )


@router.get("/oauth/callback", include_in_schema=False)
def oauth_callback(
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    """OAuth2 callback. Exchange code for tokens and store via vault."""
    if error:
        return _oauth_popup_result_html(
            success=False,
            message=f"OAuth provider error: {error}",
        )
    if not state or not code:
        return _oauth_popup_result_html(
            success=False,
            message="Missing state or code in OAuth callback.",
        )

    try:
        oauth_service.exchange_code(state=state, code=code)
    except OAuthError as exc:
        return _oauth_popup_result_html(success=False, message=exc.message)

    return _oauth_popup_result_html(success=True)


@router.post("/{connector_id}/oauth/refresh")
def oauth_refresh(
    connector_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Refresh the OAuth2 access token using the stored refresh token."""
    try:
        return oauth_service.refresh_token(_tenant(user_id), connector_id)
    except OAuthError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


# ── Health / test ──────────────────────────────────────────────────────────

@router.post("/{connector_id}/test", summary="Test a stored connector credential")
def test_connector(
    connector_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Run a lightweight read-only call to verify the stored credential works."""
    definition = catalog.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found.")

    credentials = vault.get_credential(_tenant(user_id), connector_id)
    if not credentials:
        return {"status": "error", "detail": "No credentials stored for this connector."}

    # Emit theatre-friendly test event
    _emit_connector_theatre_event(user_id, connector_id, "connector_test_started", "Testing connection…")

    # Delegate to the existing agent-layer connector for the actual health check.
    try:
        from api.services.agent.connectors.registry import get_connector_registry
        import time

        settings = dict(credentials)
        settings["__agent_user_id"] = user_id
        connector = get_connector_registry().build(connector_id, settings=settings)
        start = time.perf_counter()
        health = connector.health_check()
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        result_status = "ok" if health.ok else "error"
        _emit_connector_theatre_event(
            user_id, connector_id,
            "connector_test_completed" if health.ok else "connector_test_failed",
            f"Test {'passed' if health.ok else 'failed'}: {health.message}" if health.message else ("Connection verified" if health.ok else "Test failed"),
        )
        return {
            "status": result_status,
            "latency_ms": latency_ms,
            "detail": health.message,
        }
    except KeyError:
        _emit_connector_theatre_event(user_id, connector_id, "connector_test_completed", "Credentials stored (no health check available).")
        return {"status": "ok", "latency_ms": 0, "detail": "Credentials stored (no health check available)."}
    except Exception as exc:
        _emit_connector_theatre_event(user_id, connector_id, "connector_test_failed", str(exc)[:200])
        return {"status": "error", "latency_ms": 0, "detail": str(exc)[:300]}


# ── Binding permissions ────────────────────────────────────────────────────

@router.get("/{connector_id}/bindings")
def get_binding(
    connector_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Return the current binding permissions for this connector."""
    binding = bindings_service.get_binding(_tenant(user_id), connector_id)
    if not binding:
        raise HTTPException(status_code=404, detail="No binding found.")
    return {
        "connector_id": binding.connector_id,
        "allowed_agent_ids": binding.allowed_agent_ids,
        "enabled_tool_ids": binding.enabled_tool_ids,
        "is_active": binding.is_active,
        "last_used_at": binding.last_used_at.isoformat() if binding.last_used_at else None,
    }


@router.patch("/{connector_id}/bindings")
def update_binding_permissions(
    connector_id: str,
    body: BindingPermissionsRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Update which agents and tools are permitted for this connector."""
    try:
        if body.allowed_agent_ids is not None:
            bindings_service.set_allowed_agents(_tenant(user_id), connector_id, body.allowed_agent_ids)
        if body.enabled_tool_ids is not None:
            bindings_service.set_enabled_tools(_tenant(user_id), connector_id, body.enabled_tool_ids)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"status": "updated", "connector_id": connector_id}


# ── Webhooks ──────────────────────────────────────────────────────────────

@router.post("/{connector_id}/webhooks", status_code=status.HTTP_201_CREATED, summary="Register a webhook")
def register_webhook(
    connector_id: str,
    body: WebhookRegisterRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Register a webhook with the external connector service."""
    definition = catalog.get_definition(connector_id)
    if not definition:
        raise HTTPException(status_code=404, detail="Connector not found.")
    try:
        record = webhooks_service.register_webhook(
            tenant_id=_tenant(user_id),
            connector_id=connector_id,
            event_types=body.event_types,
            base_url=body.base_url,
            extra_params=body.extra_params,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "id": record.id,
        "connector_id": record.connector_id,
        "receiver_url": record.receiver_url,
        "external_hook_id": record.external_hook_id,
    }


# ── Tool execution ─────────────────────────────────────────────────────────

@router.post("/tools/execute")
def run_tool(
    body: ToolExecuteRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
) -> dict[str, Any]:
    """Execute a connector tool on behalf of an agent."""
    result = execute_tool(
        tool_id=body.tool_id,
        tenant_id=_tenant(user_id),
        agent_id=body.agent_id,
        params=body.params,
    )
    return result.to_dict()
