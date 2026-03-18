"""ConnectorCatalog — builds ConnectorDefinitionSchema from profiles + product metadata.

Responsibility: merge tool profiles with product metadata, apply suite sub-services,
filter internal connectors from user-facing responses, and compute setup status.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from api.schemas.connector_definition import (
    ConnectorCategory,
    ConnectorDefinitionSchema,
    ConnectorSubService,
    NoAuthConfig,
)
from api.services.connectors.connector_profiles import PROFILES
from api.services.connectors.connector_profiles_ext import PROFILES_EXT
from api.services.connectors.product_meta import (
    PRODUCT_META,
    SUITE_SUB_SERVICES,
)

logger = logging.getLogger(__name__)

# Merge both profile dicts (core + extended)
_ALL_PROFILES: dict[str, dict] = {**PROFILES, **PROFILES_EXT}


def _default_profile(connector_id: str) -> dict:
    """Fallback profile for connectors not explicitly defined."""
    return {
        "name": connector_id.replace("_", " ").title(),
        "description": f"{connector_id} connector.",
        "category": ConnectorCategory.other,
        "auth": NoAuthConfig(),
        "tags": [],
        "tools": [],
    }


def _infer_auth_kind(auth: object) -> str:
    """Derive auth_kind from the auth config object."""
    from api.schemas.connector_definition import (
        ApiKeyAuthConfig,
        BasicAuthConfig,
        BearerAuthConfig,
        OAuth2AuthConfig,
    )
    if isinstance(auth, OAuth2AuthConfig):
        return "oauth2"
    if isinstance(auth, ApiKeyAuthConfig):
        return "api_key"
    if isinstance(auth, BearerAuthConfig):
        return "bearer"
    if isinstance(auth, BasicAuthConfig):
        return "basic"
    return "none"


def _infer_setup_mode(auth_kind: str) -> str:
    """Derive setup_mode from auth_kind."""
    if auth_kind == "oauth2":
        return "oauth_popup"
    if auth_kind in ("api_key", "bearer", "basic"):
        return "manual_credentials"
    return "none"


def build_definition(
    connector_id: str,
    *,
    enabled: bool = True,
    tenant_id: str | None = None,
) -> ConnectorDefinitionSchema:
    """Build a ConnectorDefinitionSchema enriched with product metadata."""
    profile = _ALL_PROFILES.get(connector_id) or _default_profile(connector_id)
    meta = PRODUCT_META.get(connector_id, {})

    auth = profile.get("auth", NoAuthConfig())
    auth_kind = meta.get("auth_kind") or _infer_auth_kind(auth)
    setup_mode = meta.get("setup_mode") or _infer_setup_mode(auth_kind)
    visibility = meta.get("visibility", "user_facing")
    brand_slug = meta.get("brand_slug", connector_id)
    scene_family = meta.get("scene_family", "api")
    suite_id = meta.get("suite_id") or profile.get("suite_id")
    suite_label = meta.get("suite_label") or profile.get("suite_label")
    service_order = meta.get("service_order") or profile.get("service_order", 99)

    # Attach suite sub-services
    sub_services: list[ConnectorSubService] = []
    if suite_id and suite_id in SUITE_SUB_SERVICES:
        sub_services = list(SUITE_SUB_SERVICES[suite_id])

    # Compute setup_status if tenant_id provided
    required_scopes = _collect_required_scopes(auth)
    setup_status = "needs_setup"
    setup_message = ""
    if tenant_id:
        setup_status, setup_message = _compute_setup_status(
            tenant_id, connector_id, auth_kind, required_scopes,
        )
        if sub_services:
            sub_services = _hydrate_sub_service_status(
                tenant_id=tenant_id,
                connector_id=connector_id,
                setup_status=setup_status,
                sub_services=sub_services,
            )

    return ConnectorDefinitionSchema(
        id=connector_id,
        name=profile["name"],
        description=profile.get("description", ""),
        auth=auth,
        category=profile.get("category", ConnectorCategory.other),
        tags=list(profile.get("tags") or []),
        tools=list(profile.get("tools") or []),
        logo_url=profile.get("logo_url"),
        suite_id=suite_id,
        suite_label=suite_label,
        service_order=service_order,
        emitted_event_types=list(profile.get("emitted_event_types") or []),
        is_public=enabled,
        # Product metadata
        brand_slug=brand_slug,
        visibility=visibility,
        auth_kind=auth_kind,
        setup_mode=setup_mode,
        scene_family=scene_family,
        setup_status=setup_status,
        setup_message=setup_message,
        required_scopes=required_scopes,
        sub_services=sub_services,
    )


def _collect_required_scopes(auth: object) -> list[str]:
    """Extract required scopes from an OAuth2 auth config."""
    from api.schemas.connector_definition import OAuth2AuthConfig
    if isinstance(auth, OAuth2AuthConfig) and auth.scopes:
        return list(auth.scopes)
    return []


def _compute_setup_status(
    tenant_id: str,
    connector_id: str,
    auth_kind: str,
    required_scopes: list[str] | None = None,
) -> tuple[str, str]:
    """Compute setup_status and setup_message from stored credentials.

    Returns one of:
    - ("connected", "")
    - ("needs_setup", reason)
    - ("expired", reason)
    - ("needs_permission", reason)  — connected but missing scopes
    """
    if auth_kind == "none":
        return "connected", ""

    try:
        from api.services.connectors.vault import get_binding, get_granted_scopes
        binding = get_binding(tenant_id, connector_id)
    except Exception:
        return "needs_setup", ""

    if not binding or not binding.is_active:
        return "needs_setup", "No credentials configured."

    # Check token expiry for OAuth2
    if auth_kind == "oauth2":
        if not binding.encrypted_access_token:
            return "needs_setup", "No access token stored."
        if binding.token_expires_at:
            now = datetime.now(tz=timezone.utc)
            expires = binding.token_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now >= expires:
                return "expired", f"Token expired {(now - expires).days}d ago."

        # Check scope gaps
        if required_scopes:
            try:
                granted = get_granted_scopes(tenant_id, connector_id)
                if granted:
                    missing = [s for s in required_scopes if s not in granted]
                    if missing:
                        return "needs_permission", f"Missing scopes: {', '.join(missing[:3])}"
            except Exception:
                pass

    # For API key / basic — just check creds exist
    if auth_kind in ("api_key", "bearer", "basic"):
        if not binding.encrypted_credentials:
            return "needs_setup", "No credentials stored."

    return "connected", ""


def _hydrate_sub_service_status(
    *,
    tenant_id: str,
    connector_id: str,
    setup_status: str,
    sub_services: list[ConnectorSubService],
) -> list[ConnectorSubService]:
    """Populate suite sub-service status from connector binding + granted scopes."""
    if setup_status == "connected":
        try:
            from api.services.connectors.vault import get_granted_scopes

            granted = set(get_granted_scopes(tenant_id, connector_id))
        except Exception:
            granted = set()
        hydrated: list[ConnectorSubService] = []
        for service in sub_services:
            required = list(service.required_scopes or [])
            if required and granted:
                missing = [scope for scope in required if scope not in granted]
                status = "needs_permission" if missing else "connected"
            elif required and not granted:
                status = "needs_permission"
            else:
                status = "connected"
            hydrated.append(service.model_copy(update={"status": status}))
        return hydrated

    if setup_status in {"expired", "needs_permission"}:
        return [
            service.model_copy(update={"status": "needs_permission"})
            for service in sub_services
        ]

    if setup_status == "needs_setup":
        return [
            service.model_copy(update={"status": "needs_setup"})
            for service in sub_services
        ]

    return sub_services


def list_definitions(
    *,
    enabled_ids: list[str] | None = None,
    include_internal: bool = False,
    tenant_id: str | None = None,
) -> list[ConnectorDefinitionSchema]:
    """Return definitions for all known connectors, or a filtered subset."""
    from api.services.agent.connectors.registry import get_connector_registry

    all_ids = get_connector_registry().names()
    ids = enabled_ids if enabled_ids is not None else all_ids

    results: list[ConnectorDefinitionSchema] = []
    for cid in ids:
        if cid not in all_ids and cid not in _ALL_PROFILES:
            continue
        defn = build_definition(cid, tenant_id=tenant_id)
        if not include_internal and defn.visibility == "internal":
            continue
        results.append(defn)

    # Also include metadata-only connectors from profiles not in registry
    for cid in _ALL_PROFILES:
        if cid in {d.id for d in results}:
            continue
        if enabled_ids is not None and cid not in enabled_ids:
            continue
        defn = build_definition(cid, tenant_id=tenant_id)
        if not include_internal and defn.visibility == "internal":
            continue
        results.append(defn)

    return results


def get_definition(
    connector_id: str,
    *,
    tenant_id: str | None = None,
) -> ConnectorDefinitionSchema | None:
    """Return the definition for a single connector, or None if unknown."""
    from api.services.agent.connectors.registry import get_connector_registry

    if (
        connector_id not in get_connector_registry().names()
        and connector_id not in _ALL_PROFILES
    ):
        return None
    return build_definition(connector_id, tenant_id=tenant_id)
