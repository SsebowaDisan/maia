"""B2-01 — Agent definition store (versioned).

Responsibility: CRUD for AgentDefinitionSchema per tenant with full version
history.  Each update archives the previous version rather than overwriting it.

This is the Phase-2 runtime store.  Phase-0's agent_definitions store handles
the platform-level record; this wraps it with versioning semantics needed
by the agent runtime.
"""
from __future__ import annotations

import logging
from typing import Sequence

from api.models.agent_definition import AgentDefinitionRecord
from api.schemas.agent_definition.schema import AgentDefinitionSchema
from api.services.agent_definitions import store as _base_store

logger = logging.getLogger(__name__)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_agent(tenant_id: str, user_id: str, schema: AgentDefinitionSchema) -> AgentDefinitionRecord:
    """Create and persist a new agent definition for a tenant."""
    return _base_store.create_definition(tenant_id, user_id, schema)


def get_agent(
    tenant_id: str,
    agent_id: str,
    version: str | None = None,
) -> AgentDefinitionRecord | None:
    """Return the agent definition record.

    If *version* is None, returns the current active version.
    If *version* is specified, searches all (including archived) records for
    a matching version string.
    """
    if version is None:
        return _base_store.get_definition_by_agent_id(tenant_id, agent_id)

    # Historical lookup: scan all records including inactive ones
    from sqlmodel import Session, select
    from api.models.agent_definition import AgentDefinitionRecord as _R
    from ktem.db.engine import engine

    with Session(engine) as session:
        return session.exec(
            select(_R)
            .where(_R.tenant_id == tenant_id)
            .where(_R.agent_id == agent_id)
            .where(_R.version == version)
        ).first()


def list_agents(tenant_id: str) -> Sequence[AgentDefinitionRecord]:
    """List all active agent definitions for a tenant."""
    return _base_store.list_definitions(tenant_id, active_only=True)


def update_agent(
    tenant_id: str,
    agent_id: str,
    user_id: str,
    schema: AgentDefinitionSchema,
) -> AgentDefinitionRecord:
    """Update an agent: archives current version, creates new one.

    The schema *version* field must differ from the current active version.
    """
    current = _base_store.get_definition_by_agent_id(tenant_id, agent_id)
    if not current:
        raise ValueError(f"No active agent '{agent_id}' in tenant '{tenant_id}'.")

    if current.version == schema.version:
        raise ValueError(
            f"New version '{schema.version}' is the same as current version. "
            "Increment the version before updating."
        )

    # Archive current by deactivating it
    _base_store.deactivate_definition(current.id)

    # Create fresh active record with new version
    new_record = _base_store.create_definition(tenant_id, user_id, schema)
    logger.info(
        "Agent '%s' updated from v%s to v%s for tenant '%s'",
        agent_id,
        current.version,
        schema.version,
        tenant_id,
    )
    return new_record


def delete_agent(tenant_id: str, agent_id: str) -> AgentDefinitionRecord:
    """Soft-delete (deactivate) an agent definition."""
    current = _base_store.get_definition_by_agent_id(tenant_id, agent_id)
    if not current:
        raise ValueError(f"No active agent '{agent_id}' in tenant '{tenant_id}'.")
    return _base_store.deactivate_definition(current.id)


def load_schema(record: AgentDefinitionRecord) -> AgentDefinitionSchema:
    """Deserialise a DB record back to the validated schema object."""
    return _base_store.load_schema(record)
