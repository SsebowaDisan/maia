from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.context import get_context
from api.services.google.analytics import GoogleAnalyticsService
from api.services.google.errors import GoogleServiceError
from api.services.google.oauth_scopes import (
    invalid_google_oauth_service_ids,
    normalize_google_oauth_service_ids,
    scopes_from_service_ids,
)
from api.services.google.resource_links import (
    GoogleResourceReference,
    analyze_google_resource_reference,
    normalize_link_aliases,
)
from api.services.google.session import GoogleAuthSession
from api.services.google.service_account import resolve_service_account_profile
from api.services.settings_service import save_user_settings

from .common import publish_event, tenant_settings
from .schemas import (
    GoogleAnalyticsPropertyRequest,
    GoogleOAuthServicesRequest,
    GoogleWorkspaceAuthModeRequest,
    GoogleWorkspaceLinkAliasSaveRequest,
    GoogleWorkspaceLinkAnalyzeRequest,
    GoogleWorkspaceLinkCheckRequest,
)

router = APIRouter(tags=["agent-integrations"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_google_session(*, user_id: str, settings: dict[str, object]) -> GoogleAuthSession:
    return GoogleAuthSession(
        user_id=user_id,
        run_id=None,
        settings=settings,
    )


def _aliases_from_settings(settings: dict[str, object]) -> dict[str, dict[str, str]]:
    return normalize_link_aliases(settings.get("agent.google_workspace_link_aliases"))


def _alias_rows(aliases: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key in sorted(aliases.keys()):
        row = aliases[key]
        rows.append(
            {
                "alias": str(row.get("alias") or key),
                "resource_type": str(row.get("resource_type") or ""),
                "resource_id": str(row.get("resource_id") or ""),
                "canonical_url": str(row.get("canonical_url") or ""),
            }
        )
    return rows


def _resolve_reference_from_payload(
    *,
    link: str,
    aliases: dict[str, dict[str, str]],
) -> GoogleResourceReference:
    parsed = analyze_google_resource_reference(link)
    if parsed is not None:
        return parsed
    alias_key = " ".join(str(link or "").split()).strip().lower()
    alias_row = aliases.get(alias_key)
    if alias_row is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported link or alias. Paste a Google Docs/Sheets/Drive/GA4 link, "
                "a Google file/property ID, or a saved alias."
            ),
        )
    return GoogleResourceReference(
        resource_type=str(alias_row.get("resource_type") or ""),
        resource_id=str(alias_row.get("resource_id") or ""),
        canonical_url=str(alias_row.get("canonical_url") or ""),
        label=str(alias_row.get("resource_type") or "Google resource"),
    )


def _check_drive_access(
    *,
    session: GoogleAuthSession,
    reference: GoogleResourceReference,
    action: str,
) -> dict[str, object]:
    file_id = reference.resource_id
    metadata = session.request_json(
        method="GET",
        url=f"https://www.googleapis.com/drive/v3/files/{file_id}",
        params={
            "fields": "id,name,mimeType,capabilities(canEdit,canComment,canReadRevisions)",
        },
    )
    if not isinstance(metadata, dict):
        metadata = {}
    capabilities = metadata.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}
    can_edit = bool(capabilities.get("canEdit"))
    can_read = True
    required_role = "Editor" if action == "edit" else "Viewer"
    ready = can_read if action == "read" else can_edit
    return {
        "ready": ready,
        "required_role": required_role,
        "can_read": can_read,
        "can_edit": can_edit,
        "resource_name": str(metadata.get("name") or ""),
        "resource_mime_type": str(metadata.get("mimeType") or ""),
        "canonical_url": reference.canonical_url,
        "resource_id": file_id,
        "message": (
            "Access check passed."
            if ready
            else "Resource is reachable, but editor role is required for edit actions."
        ),
    }


def _check_ga4_access(
    *,
    session: GoogleAuthSession,
    reference: GoogleResourceReference,
    action: str,
) -> dict[str, object]:
    property_id = reference.resource_id
    analytics = GoogleAnalyticsService(session=session)
    analytics.run_report(
        property_id=property_id,
        date_range={"startDate": "7daysAgo", "endDate": "today"},
        metrics=["sessions"],
        dimensions=["date"],
        limit=1,
    )
    if action == "edit":
        return {
            "ready": False,
            "required_role": "Viewer",
            "can_read": True,
            "can_edit": False,
            "resource_name": f"GA4 property {property_id}",
            "resource_mime_type": "ga4_property",
            "canonical_url": reference.canonical_url,
            "resource_id": property_id,
            "message": "GA4 integration is read-only. Use read action for analytics checks.",
        }
    return {
        "ready": True,
        "required_role": "Viewer",
        "can_read": True,
        "can_edit": False,
        "resource_name": f"GA4 property {property_id}",
        "resource_mime_type": "ga4_property",
        "canonical_url": reference.canonical_url,
        "resource_id": property_id,
    }


@router.get("/integrations/google-workspace/service-account/status")
def google_workspace_service_account_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    profile = resolve_service_account_profile(settings=settings)
    aliases = _aliases_from_settings(settings)
    return {
        "configured": profile.configured,
        "usable": profile.usable,
        "email": profile.email,
        "client_id": profile.client_id or None,
        "project_id": profile.project_id or None,
        "source": profile.source or None,
        "auth_mode": profile.auth_mode,
        "message": profile.message,
        "instructions": profile.instructions,
        "aliases_count": len(aliases),
    }


@router.post("/integrations/google-workspace/service-account/auth-mode")
def update_google_workspace_auth_mode(
    payload: GoogleWorkspaceAuthModeRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    next_settings = deepcopy(settings)
    next_settings["agent.google_auth_mode"] = payload.mode
    save_user_settings(
        context=get_context(),
        user_id=user_id,
        values=next_settings,
    )
    publish_event(
        user_id=user_id,
        run_id=None,
        event_type="google.workspace.auth_mode_updated",
        message="Google Workspace auth mode updated",
        data={"mode": payload.mode},
    )
    return {"status": "saved", "mode": payload.mode}


@router.get("/integrations/google/oauth/services")
def list_google_oauth_services(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    services = normalize_google_oauth_service_ids(settings.get("agent.google_oauth_services"))
    return {
        "services": services,
        "scopes": scopes_from_service_ids(services, include_base=True),
    }


@router.post("/integrations/google/oauth/services")
def save_google_oauth_services(
    payload: GoogleOAuthServicesRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    invalid = invalid_google_oauth_service_ids(payload.services)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Google OAuth service IDs: {', '.join(invalid)}",
        )
    _, settings = tenant_settings(user_id)
    services = normalize_google_oauth_service_ids(payload.services)
    next_settings = deepcopy(settings)
    next_settings["agent.google_oauth_services"] = services
    save_user_settings(
        context=get_context(),
        user_id=user_id,
        values=next_settings,
    )
    publish_event(
        user_id=user_id,
        run_id=None,
        event_type="google.oauth.services_saved",
        message="Google OAuth service selections updated",
        data={"services": services},
    )
    return {
        "status": "saved",
        "services": services,
        "scopes": scopes_from_service_ids(services, include_base=True),
    }


@router.get("/integrations/google/analytics/property")
def get_google_analytics_property(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    property_id = str(settings.get("agent.google_analytics_property_id") or "").strip()
    return {"property_id": property_id, "configured": bool(property_id)}


@router.post("/integrations/google/analytics/property")
def save_google_analytics_property(
    payload: GoogleAnalyticsPropertyRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    raw = " ".join(str(payload.property_id or "").split()).strip()
    if not raw.isdigit():
        raise HTTPException(status_code=400, detail="GA4 property ID must be numeric (e.g. 479179141).")
    _, settings = tenant_settings(user_id)
    next_settings = deepcopy(settings)
    next_settings["agent.google_analytics_property_id"] = raw
    save_user_settings(context=get_context(), user_id=user_id, values=next_settings)
    return {"status": "saved", "property_id": raw}


@router.get("/integrations/google-workspace/link-assistant/aliases")
def list_google_workspace_link_aliases(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    aliases = _aliases_from_settings(settings)
    return {"aliases": _alias_rows(aliases)}


@router.post("/integrations/google-workspace/link-assistant/analyze")
def analyze_google_workspace_link(
    payload: GoogleWorkspaceLinkAnalyzeRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    aliases = _aliases_from_settings(settings)
    text = str(payload.link or "").strip()
    parsed = analyze_google_resource_reference(text)
    if parsed is not None:
        return {"detected": True, **parsed.to_dict(), "source": "link"}
    alias_key = " ".join(text.split()).strip().lower()
    alias_row = aliases.get(alias_key)
    if alias_row is None:
        return {
            "detected": False,
            "message": "Unsupported link or alias.",
            "source": "unknown",
        }
    return {
        "detected": True,
        "resource_type": str(alias_row.get("resource_type") or ""),
        "resource_id": str(alias_row.get("resource_id") or ""),
        "canonical_url": str(alias_row.get("canonical_url") or ""),
        "label": str(alias_row.get("alias") or alias_key),
        "source": "alias",
    }


@router.post("/integrations/google-workspace/link-assistant/check-access")
def check_google_workspace_link_access(
    payload: GoogleWorkspaceLinkCheckRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    aliases = _aliases_from_settings(settings)
    action = str(payload.action or "read").strip().lower()
    if action not in {"read", "edit"}:
        action = "read"
    reference = _resolve_reference_from_payload(link=payload.link, aliases=aliases)
    session = _build_google_session(user_id=user_id, settings=settings)

    try:
        if reference.resource_type in {"google_doc", "google_sheet", "google_drive_file"}:
            outcome = _check_drive_access(
                session=session,
                reference=reference,
                action=action,
            )
        elif reference.resource_type == "ga4_property":
            outcome = _check_ga4_access(
                session=session,
                reference=reference,
                action=action,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported resource type: {reference.resource_type}",
            )
    except GoogleServiceError as exc:
        outcome = {
            "ready": False,
            "required_role": "Editor" if action == "edit" else "Viewer",
            "can_read": False,
            "can_edit": False,
            "resource_name": "",
            "resource_mime_type": "",
            "canonical_url": reference.canonical_url,
            "resource_id": reference.resource_id,
            "message": f"{exc.code}: {exc.message}",
            "error_code": exc.code,
        }

    publish_event(
        user_id=user_id,
        run_id=None,
        event_type="google.workspace.link_access_checked",
        message="Google Workspace link access checked",
        data={
            "resource_type": reference.resource_type,
            "resource_id": reference.resource_id,
            "action": action,
            "ready": bool(outcome.get("ready")),
        },
    )
    result = {
        "action": action,
        "resource_type": reference.resource_type,
        "checked_at": _utc_now_iso(),
        **outcome,
    }
    if "message" not in result:
        result["message"] = (
            "Access check passed."
            if bool(result.get("ready"))
            else "Access check failed."
        )
    return result


@router.post("/integrations/google-workspace/link-assistant/aliases/save")
def save_google_workspace_link_alias(
    payload: GoogleWorkspaceLinkAliasSaveRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, object]:
    _, settings = tenant_settings(user_id)
    aliases = _aliases_from_settings(settings)
    alias_text = " ".join(str(payload.alias or "").split()).strip()
    if not alias_text:
        raise HTTPException(status_code=400, detail="Alias is required.")
    reference = _resolve_reference_from_payload(link=payload.link, aliases=aliases)

    alias_key = alias_text.lower()
    aliases[alias_key] = {
        "alias": alias_text,
        "resource_type": reference.resource_type,
        "resource_id": reference.resource_id,
        "canonical_url": reference.canonical_url,
    }
    next_settings = deepcopy(settings)
    next_settings["agent.google_workspace_link_aliases"] = aliases
    save_user_settings(
        context=get_context(),
        user_id=user_id,
        values=next_settings,
    )
    publish_event(
        user_id=user_id,
        run_id=None,
        event_type="google.workspace.link_alias_saved",
        message="Google Workspace alias saved",
        data={
            "alias": alias_text,
            "resource_type": reference.resource_type,
            "resource_id": reference.resource_id,
        },
    )
    return {
        "status": "saved",
        "alias": aliases[alias_key],
        "aliases": _alias_rows(aliases),
    }
