"""Bindings service — connector permission checks for agents.

Responsibility: answer whether a given agent is allowed to call a tool,
and manage the allowed_agent_ids / enabled_tool_ids lists on ConnectorBinding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlmodel import Session, select

from api.models.connector_binding import ConnectorBinding
from ktem.db.engine import engine


class ToolPermissionError(PermissionError):
    """Raised when an agent tries to use a tool it is not permitted to access."""


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_binding(tenant_id: str, connector_id: str) -> ConnectorBinding | None:
    with Session(engine) as session:
        return session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
            .where(ConnectorBinding.is_active == True)  # noqa: E712
        ).first()


def list_bindings(tenant_id: str) -> Sequence[ConnectorBinding]:
    with Session(engine) as session:
        return session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.is_active == True)  # noqa: E712
            .order_by(ConnectorBinding.connector_id)
        ).all()


# ---------------------------------------------------------------------------
# Permission check
# ---------------------------------------------------------------------------

def is_tool_allowed(tenant_id: str, agent_id: str, tool_id: str) -> bool:
    """Return True if agent_id is permitted to call tool_id via this tenant's bindings."""
    connector_id = tool_id.split(".")[0] if "." in tool_id else tool_id
    binding = get_binding(tenant_id, connector_id)
    if binding is None:
        return False

    # If allowed_agent_ids is empty, all agents in this tenant may use the connector.
    if binding.allowed_agent_ids:
        if agent_id not in binding.allowed_agent_ids:
            return False

    # If enabled_tool_ids is empty, all tools in the connector are available.
    if binding.enabled_tool_ids:
        if tool_id not in binding.enabled_tool_ids:
            return False

    return True


def assert_tool_allowed(tenant_id: str, agent_id: str, tool_id: str) -> None:
    """Raise ToolPermissionError if the agent is not permitted to use the tool."""
    if not is_tool_allowed(tenant_id, agent_id, tool_id):
        raise ToolPermissionError(
            f"Agent '{agent_id}' is not permitted to call tool '{tool_id}' "
            f"in tenant '{tenant_id}'."
        )


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def set_allowed_agents(
    tenant_id: str,
    connector_id: str,
    agent_ids: list[str],
) -> ConnectorBinding:
    """Replace the allowed_agent_ids list for a binding."""
    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()
        if not binding:
            raise ValueError(f"No binding found for {tenant_id}/{connector_id}.")
        binding.allowed_agent_ids = list(agent_ids)
        binding.date_updated = datetime.utcnow()
        session.add(binding)
        session.commit()
        session.refresh(binding)
        return binding


def set_enabled_tools(
    tenant_id: str,
    connector_id: str,
    tool_ids: list[str],
) -> ConnectorBinding:
    """Replace the enabled_tool_ids list for a binding."""
    with Session(engine) as session:
        binding = session.exec(
            select(ConnectorBinding)
            .where(ConnectorBinding.tenant_id == tenant_id)
            .where(ConnectorBinding.connector_id == connector_id)
        ).first()
        if not binding:
            raise ValueError(f"No binding found for {tenant_id}/{connector_id}.")
        binding.enabled_tool_ids = list(tool_ids)
        binding.date_updated = datetime.utcnow()
        session.add(binding)
        session.commit()
        session.refresh(binding)
        return binding


def mark_last_used(tenant_id: str, connector_id: str) -> None:
    """Update last_used_at timestamp for a binding (best-effort, no error raised)."""
    try:
        with Session(engine) as session:
            binding = session.exec(
                select(ConnectorBinding)
                .where(ConnectorBinding.tenant_id == tenant_id)
                .where(ConnectorBinding.connector_id == connector_id)
            ).first()
            if binding:
                binding.last_used_at = datetime.utcnow()
                session.add(binding)
                session.commit()
    except Exception:
        pass
