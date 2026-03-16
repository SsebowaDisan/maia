"""B3-04 — Versioning and update system.

Responsibility: detect when a marketplace agent has a newer version, notify
tenants, and migrate their installed agent to the new version.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Sequence

from sqlmodel import Session, select

from ktem.db.engine import engine
from api.services.marketplace.registry import MarketplaceAgent

logger = logging.getLogger(__name__)


def check_for_updates(tenant_id: str) -> list[dict[str, Any]]:
    """Return list of installed agents that have a newer published version."""
    from api.services.agents.definition_store import list_agents, load_schema

    updates: list[dict[str, Any]] = []
    for record in list_agents(tenant_id):
        try:
            schema = load_schema(record)
            latest = _get_latest_published(schema.id)
            if latest and _is_newer(latest.version, schema.version):
                updates.append({
                    "agent_id": record.agent_id,
                    "current_version": schema.version,
                    "latest_version": latest.version,
                    "marketplace_id": latest.id,
                    "changelog": _get_changelog(schema.id, schema.version, latest.version),
                })
        except Exception:
            pass
    return updates


def update_agent(
    tenant_id: str,
    user_id: str,
    agent_id: str,
    target_version: str | None = None,
) -> dict[str, Any]:
    """Update a tenant's installed agent to a newer marketplace version.

    Migrates connector bindings to preserve access permissions.
    """
    from api.services.marketplace.registry import get_marketplace_agent
    from api.services.agents.definition_store import get_agent, load_schema, update_agent as _update
    from api.schemas.agent_definition.schema import AgentDefinitionSchema

    marketplace_entry = get_marketplace_agent(agent_id, target_version)
    if not marketplace_entry:
        return {"success": False, "error": f"No published version found for agent '{agent_id}'."}

    current = get_agent(tenant_id, agent_id)
    if not current:
        return {"success": False, "error": f"Agent '{agent_id}' is not installed for this tenant."}

    try:
        # Load new schema from marketplace definition
        definition_dict = json.loads(marketplace_entry.definition_json)
        new_schema = AgentDefinitionSchema.model_validate(definition_dict)

        # Preserve current version's connector bindings
        _migrate_connector_bindings(tenant_id, agent_id)

        updated = _update(tenant_id, agent_id, user_id, new_schema)
        logger.info(
            "Updated agent %s to v%s for tenant %s",
            agent_id,
            marketplace_entry.version,
            tenant_id,
        )
        return {
            "success": True,
            "agent_id": agent_id,
            "new_version": updated.version,
        }
    except Exception as exc:
        logger.error("Update failed for agent %s: %s", agent_id, exc, exc_info=True)
        return {"success": False, "error": str(exc)[:300]}


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_latest_published(agent_id: str) -> MarketplaceAgent | None:
    with Session(engine) as session:
        return session.exec(
            select(MarketplaceAgent)
            .where(MarketplaceAgent.agent_id == agent_id)
            .where(MarketplaceAgent.status == "published")
            .order_by(MarketplaceAgent.published_at.desc())  # type: ignore[attr-defined]
        ).first()


def _is_newer(candidate: str, current: str) -> bool:
    """Simple semver comparison.  Returns True if candidate > current."""
    try:
        def _parts(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.lstrip("v").split(".")[:3])

        return _parts(candidate) > _parts(current)
    except Exception:
        return False


def _get_changelog(agent_id: str, from_version: str, to_version: str) -> str:
    """Return the changelog for the target version, falling back to a generic message."""
    with Session(engine) as session:
        entry = session.exec(
            select(MarketplaceAgent)
            .where(MarketplaceAgent.agent_id == agent_id)
            .where(MarketplaceAgent.version == to_version)
            .where(MarketplaceAgent.status == "published")
        ).first()
    if entry and entry.changelog:
        return entry.changelog
    return f"Update from v{from_version} to v{to_version}."


def _migrate_connector_bindings(tenant_id: str, agent_id: str) -> None:
    """Ensure connector bindings survive the update (they already target agent_id, so no-op)."""
    pass  # Bindings are stored by agent_id string — they persist across version updates
