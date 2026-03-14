"""B3-03 — Installation pipeline.

Responsibility: install a marketplace agent into a tenant's agent store,
map connector bindings, and validate prerequisites.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class InstallResult:
    success: bool
    agent_id: str
    missing_connectors: list[str]
    error: str = ""


def install_agent(
    tenant_id: str,
    user_id: str,
    marketplace_agent_id: str,
    version: str | None = None,
    connector_mapping: dict[str, str] | None = None,
) -> InstallResult:
    """Copy a marketplace agent definition into the tenant's store.

    Args:
        tenant_id: Target tenant.
        user_id: User performing the install.
        marketplace_agent_id: Agent ID in the marketplace.
        version: Specific version to install (defaults to latest published).
        connector_mapping: {required_connector_id: tenant_connector_id} overrides.

    Returns:
        InstallResult with success flag and any missing connectors.
    """
    from api.services.marketplace.registry import get_marketplace_agent

    entry = get_marketplace_agent(marketplace_agent_id, version)
    if not entry:
        return InstallResult(
            success=False,
            agent_id=marketplace_agent_id,
            missing_connectors=[],
            error=f"Marketplace agent '{marketplace_agent_id}' not found.",
        )

    # Check required connectors
    required: list[str] = json.loads(entry.required_connectors_json)
    missing = _check_missing_connectors(tenant_id, required, connector_mapping or {})
    if missing:
        return InstallResult(success=False, agent_id=marketplace_agent_id, missing_connectors=missing)

    # Check Computer Use prerequisite
    if entry.has_computer_use and not os.environ.get("ANTHROPIC_API_KEY"):
        return InstallResult(
            success=False,
            agent_id=marketplace_agent_id,
            missing_connectors=[],
            error="ANTHROPIC_API_KEY is not configured. Required for Computer Use agents.",
        )

    # Parse and persist definition
    definition_dict = json.loads(entry.definition_json)
    try:
        from api.schemas.agent_definition.schema import AgentDefinitionSchema
        from api.services.agents.definition_store import create_agent, get_agent

        schema = AgentDefinitionSchema.model_validate(definition_dict)

        # Avoid duplicate installs
        existing = get_agent(tenant_id, schema.id)
        if existing:
            return InstallResult(
                success=False,
                agent_id=schema.id,
                missing_connectors=[],
                error=f"Agent '{schema.id}' is already installed.",
            )

        record = create_agent(tenant_id, user_id, schema)

        # Bind connector permissions
        _bind_connectors(tenant_id, record.agent_id, required, connector_mapping or {})

        # Track install count
        from api.services.marketplace.registry import increment_install_count

        increment_install_count(marketplace_agent_id)

        logger.info(
            "Installed marketplace agent %s v%s for tenant %s",
            marketplace_agent_id,
            entry.version,
            tenant_id,
        )
        return InstallResult(success=True, agent_id=record.agent_id, missing_connectors=[])

    except Exception as exc:
        logger.error("Install failed for %s: %s", marketplace_agent_id, exc, exc_info=True)
        return InstallResult(
            success=False,
            agent_id=marketplace_agent_id,
            missing_connectors=[],
            error=str(exc)[:300],
        )


def uninstall_agent(tenant_id: str, agent_id: str) -> bool:
    """Soft-delete the agent definition from the tenant's store."""
    try:
        from api.services.agents.definition_store import delete_agent

        delete_agent(tenant_id, agent_id)
        return True
    except ValueError:
        return False


# ── Private helpers ────────────────────────────────────────────────────────────

def _check_missing_connectors(
    tenant_id: str,
    required: list[str],
    mapping: dict[str, str],
) -> list[str]:
    """Return list of connector IDs that are required but not installed/connected."""
    if not required:
        return []

    missing: list[str] = []
    for req in required:
        mapped = mapping.get(req, req)
        if mapped == "computer_use":
            continue  # Handled separately via ANTHROPIC_API_KEY
        connected = _is_connector_connected(tenant_id, mapped)
        if not connected:
            missing.append(req)
    return missing


def _is_connector_connected(tenant_id: str, connector_id: str) -> bool:
    try:
        from api.services.connectors.vault import get_credential

        cred = get_credential(tenant_id, connector_id)
        return cred is not None
    except Exception:
        return False


def _bind_connectors(
    tenant_id: str,
    agent_id: str,
    required: list[str],
    mapping: dict[str, str],
) -> None:
    try:
        from api.services.connectors.bindings import set_allowed_agents, get_binding

        for req in required:
            mapped = mapping.get(req, req)
            if mapped == "computer_use":
                continue
            binding = get_binding(tenant_id, mapped)
            if binding:
                current = list(binding.allowed_agent_ids or [])
                if agent_id not in current:
                    set_allowed_agents(tenant_id, mapped, current + [agent_id])
    except Exception:
        logger.debug("Connector binding failed during install", exc_info=True)
