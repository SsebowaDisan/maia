"""B3-03 — Installation pipeline.

Responsibility: install a marketplace agent into a tenant's agent store,
map connector bindings, validate prerequisites, and record install history.

B1  — InstallResult carries the full installed agent record.
B2  — Auto-maps connectors server-side when connector_mapping is empty.
B4  — Idempotent upsert: already-installed at same version → success; newer version → update.
B7  — Inherits tenant-level gate defaults when gate_policies is not supplied.
B8  — Appends an audit log entry per install to data/install_history/{tenant_id}.jsonl.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_INSTALL_HISTORY_DIR = Path(os.environ.get("MAIA_DATA_DIR", "data")) / "install_history"
_GATE_DEFAULTS_DIR = Path(os.environ.get("MAIA_DATA_DIR", "data")) / "gate_defaults"


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class InstallResult:
    success: bool
    agent_id: str
    missing_connectors: list[str]
    error: str = ""
    description: str = ""
    trigger_family: str = ""
    already_installed: bool = False          # B4
    auto_mapped_connectors: dict[str, str] = field(default_factory=dict)  # B2
    installed_record: dict[str, Any] | None = None  # B1


@dataclass
class PreflightResult:
    """B3 — result of a dry-run install check."""
    can_install_immediately: bool
    already_installed: bool
    missing_connectors: list[str]
    auto_mapped: dict[str, str]             # {required_id: tenant_connector_id}
    agent_not_found: bool = False


# ── Public API ─────────────────────────────────────────────────────────────────

def preflight_install(
    tenant_id: str,
    marketplace_agent_id: str,
    version: str | None = None,
) -> PreflightResult:
    """B3 — dry-run check: can this agent be installed in one click?

    Does NOT write anything to the database.  Returns enough information for
    the frontend to decide whether to show a one-click Install button or a
    connector-setup sheet.
    """
    from api.services.marketplace.registry import get_marketplace_agent
    from api.services.agents.definition_store import get_agent

    entry = get_marketplace_agent(marketplace_agent_id, version)
    if not entry:
        return PreflightResult(
            can_install_immediately=False,
            already_installed=False,
            missing_connectors=[],
            auto_mapped={},
            agent_not_found=True,
        )

    required: list[str] = json.loads(entry.required_connectors_json)

    # Check if already installed
    definition_dict = json.loads(entry.definition_json)
    agent_id_in_def = str(definition_dict.get("id") or marketplace_agent_id)
    existing = get_agent(tenant_id, agent_id_in_def)
    if existing:
        return PreflightResult(
            can_install_immediately=True,
            already_installed=True,
            missing_connectors=[],
            auto_mapped={},
        )

    # Attempt auto-mapping
    auto_mapped = _auto_map_connectors(tenant_id, required, {})
    missing = _check_missing_connectors(tenant_id, required, auto_mapped)

    return PreflightResult(
        can_install_immediately=len(missing) == 0,
        already_installed=False,
        missing_connectors=missing,
        auto_mapped=auto_mapped,
    )


def install_agent(
    tenant_id: str,
    user_id: str,
    marketplace_agent_id: str,
    version: str | None = None,
    connector_mapping: dict[str, str] | None = None,
    gate_policies: dict[str, bool] | None = None,
) -> InstallResult:
    """Copy a marketplace agent definition into the tenant's store.

    B2: If connector_mapping is empty, auto-maps connectors server-side.
    B4: If the agent is already installed at the same version, returns success
        with already_installed=True instead of an error.  A newer version
        triggers an in-place update.
    B7: If gate_policies is not supplied, inherits tenant-level defaults.
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

    required: list[str] = json.loads(entry.required_connectors_json)

    # B2: auto-map when the caller did not supply an explicit mapping
    effective_mapping = dict(connector_mapping or {})
    auto_mapped: dict[str, str] = {}
    if not effective_mapping:
        auto_mapped = _auto_map_connectors(tenant_id, required, {})
        effective_mapping = auto_mapped

    missing = _check_missing_connectors(tenant_id, required, effective_mapping)
    if missing:
        return InstallResult(
            success=False,
            agent_id=marketplace_agent_id,
            missing_connectors=missing,
        )

    # Computer Use prerequisite
    if entry.has_computer_use and not os.environ.get("ANTHROPIC_API_KEY"):
        return InstallResult(
            success=False,
            agent_id=marketplace_agent_id,
            missing_connectors=[],
            error="ANTHROPIC_API_KEY is not configured. Required for Computer Use agents.",
        )

    definition_dict = json.loads(entry.definition_json)
    try:
        from api.schemas.agent_definition.schema import AgentDefinitionSchema
        from api.services.agents.definition_store import create_agent, get_agent

        schema = AgentDefinitionSchema.model_validate(definition_dict)

        # B4: idempotent upsert
        existing = get_agent(tenant_id, schema.id)
        if existing:
            installed_at_version = existing.version or ""
            if installed_at_version == entry.version:
                # Same version already installed — return success, no-op
                return InstallResult(
                    success=True,
                    agent_id=schema.id,
                    missing_connectors=[],
                    description=schema.description or "",
                    trigger_family=str(getattr(schema.trigger, "family", "") or ""),
                    already_installed=True,
                    auto_mapped_connectors=auto_mapped,
                    installed_record=_record_to_dict(existing),
                )
            # Newer version — fall through to create a fresh record
            # (definition_store.create_agent handles versioning by archiving the old one)

        record = create_agent(tenant_id, user_id, schema)

        # Bind connector permissions
        _bind_connectors(tenant_id, record.agent_id, required, effective_mapping)

        # B7: resolve gate policies (explicit > tenant defaults > empty)
        effective_gate_policies = gate_policies
        if not effective_gate_policies:
            effective_gate_policies = _get_tenant_gate_defaults(tenant_id)
        if effective_gate_policies:
            _store_gate_policies(tenant_id, record.agent_id, effective_gate_policies)

        # Track install count in marketplace
        from api.services.marketplace.registry import increment_install_count
        increment_install_count(marketplace_agent_id)

        # B8: audit log
        _log_install_event(
            tenant_id=tenant_id,
            user_id=user_id,
            marketplace_agent_id=marketplace_agent_id,
            agent_id=record.agent_id,
            version=entry.version,
            connector_mapping=effective_mapping,
        )

        logger.info(
            "Installed marketplace agent %s v%s for tenant %s",
            marketplace_agent_id,
            entry.version,
            tenant_id,
        )
        tf = str(getattr(schema.trigger, "family", "") or "")
        return InstallResult(
            success=True,
            agent_id=record.agent_id,
            missing_connectors=[],
            description=schema.description or "",
            trigger_family=tf,
            already_installed=False,
            auto_mapped_connectors=auto_mapped,
            installed_record=_record_to_dict(record),
        )

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


def get_install_history(tenant_id: str, agent_id: str | None = None) -> list[dict[str, Any]]:
    """B8 — Return install audit log for a tenant, optionally filtered by agent_id."""
    path = _INSTALL_HISTORY_DIR / f"{tenant_id}.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            if agent_id is None or evt.get("agent_id") == agent_id:
                events.append(evt)
    except Exception:
        logger.debug("Failed to read install history for tenant %s", tenant_id, exc_info=True)
    return list(reversed(events))  # newest first


def get_tenant_connector_status(
    tenant_id: str,
    required_connectors: list[str],
) -> dict[str, str]:
    """B6 — Return connection state per required connector for this tenant.

    Returns a dict of {connector_id: "connected" | "missing" | "not_required"}.
    """
    if not required_connectors:
        return {}
    status: dict[str, str] = {}
    for req in required_connectors:
        if req == "computer_use":
            status[req] = "connected" if os.environ.get("ANTHROPIC_API_KEY") else "missing"
        elif _is_connector_connected(tenant_id, req):
            status[req] = "connected"
        else:
            status[req] = "missing"
    return status


# ── Private helpers ─────────────────────────────────────────────────────────────

def _auto_map_connectors(
    tenant_id: str,
    required: list[str],
    existing_mapping: dict[str, str],
) -> dict[str, str]:
    """B2 — Build an automatic connector mapping for unmapped required connectors.

    For each required connector not already in existing_mapping, check if the
    tenant has exactly one configured connector whose id matches (or starts with)
    the required connector id.  If so, map it automatically.
    """
    if not required:
        return {}

    try:
        from api.services.connectors.bindings import list_bindings
        bindings = {b.connector_id: b for b in list_bindings(tenant_id)}
    except Exception:
        return {}

    mapped: dict[str, str] = {}
    for req in required:
        if req in existing_mapping:
            continue  # caller already supplied a mapping
        if req == "computer_use":
            continue
        # Exact match first
        if req in bindings:
            mapped[req] = req
            continue
        # Prefix match: e.g., required="google_ads" matches "google_ads_v2"
        candidates = [bid for bid in bindings if bid.startswith(req)]
        if len(candidates) == 1:
            mapped[req] = candidates[0]

    return mapped


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
            continue
        if not _is_connector_connected(tenant_id, mapped):
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


def _store_gate_policies(
    tenant_id: str,
    agent_id: str,
    gate_policies: dict[str, bool],
) -> None:
    """Persist gate approval preferences for each connector binding."""
    try:
        from api.services.connectors.bindings import get_binding, set_gate_policy
        for connector_id, require_approval in gate_policies.items():
            binding = get_binding(tenant_id, connector_id)
            if binding:
                set_gate_policy(tenant_id, connector_id, agent_id, require_approval)
    except Exception:
        logger.debug("Gate policy storage failed during install", exc_info=True)


def _get_tenant_gate_defaults(tenant_id: str) -> dict[str, bool]:
    """B7 — Load tenant-level gate policy defaults from disk."""
    path = _GATE_DEFAULTS_DIR / f"{tenant_id}.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def set_tenant_gate_defaults(tenant_id: str, defaults: dict[str, bool]) -> None:
    """B7 — Persist tenant-level gate policy defaults."""
    _GATE_DEFAULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _GATE_DEFAULTS_DIR / f"{tenant_id}.json"
    path.write_text(json.dumps(defaults, indent=2), encoding="utf-8")


def _log_install_event(
    *,
    tenant_id: str,
    user_id: str,
    marketplace_agent_id: str,
    agent_id: str,
    version: str,
    connector_mapping: dict[str, str],
) -> None:
    """B8 — Append one line to the tenant's install history log."""
    try:
        _INSTALL_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path = _INSTALL_HISTORY_DIR / f"{tenant_id}.jsonl"
        event = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "user_id": user_id,
            "marketplace_agent_id": marketplace_agent_id,
            "agent_id": agent_id,
            "version": version,
            "connector_mapping": connector_mapping,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except Exception:
        logger.debug("Failed to write install history", exc_info=True)


def _record_to_dict(record: Any) -> dict[str, Any]:
    """B1 — Serialise an AgentDefinitionRecord to a plain dict for API responses."""
    try:
        return {
            "id": record.id,
            "agent_id": record.agent_id,
            "name": record.name,
            "version": record.version,
            "is_active": record.is_active,
            "date_created": record.date_created.isoformat() if record.date_created else None,
            "date_updated": record.date_updated.isoformat() if record.date_updated else None,
            "definition": record.definition,
        }
    except Exception:
        return {}
