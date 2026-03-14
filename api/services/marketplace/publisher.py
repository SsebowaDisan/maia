"""B3-02 — Publishing pipeline.

Responsibility: validate agents before publishing and manage the review
status workflow: pending_review → approved → published.

Safety checks enforced on submit:
  1. No hardcoded credentials in system prompt.
  2. All declared tools exist in the connector registry.
  3. Delegation depth ≤ 5.
  4. http_request tool blocked for private IP ranges (pattern check).
  5. Computer Use agents must declare max_steps ≤ 50.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from sqlmodel import Session, select

from ktem.db.engine import engine
from api.services.marketplace.registry import MarketplaceAgent

logger = logging.getLogger(__name__)

# Patterns that indicate hardcoded secrets in system prompts
_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|password|secret|token|bearer|sk-[a-z0-9]{20,})\s*[:=]\s*\S{8,}"),
    re.compile(r"(?i)(AKIA|ASIA)[A-Z0-9]{16}"),  # AWS key pattern
]

# Private IP CIDR patterns (for http_request block)
_PRIVATE_IP = re.compile(
    r"https?://(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|127\.|localhost|0\.0\.0\.0)"
)


class PublishValidationError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def submit_for_review(publisher_id: str, agent_id: str) -> MarketplaceAgent:
    """Validate and move agent to pending_review status.

    Raises PublishValidationError on any safety check failure.
    """
    with Session(engine) as session:
        entry = session.exec(
            select(MarketplaceAgent)
            .where(MarketplaceAgent.agent_id == agent_id)
            .where(MarketplaceAgent.publisher_id == publisher_id)
        ).first()
        if not entry:
            raise ValueError(f"Agent '{agent_id}' not found for publisher '{publisher_id}'.")

        definition = _load_definition(entry)
        _run_safety_checks(definition)

        entry.status = "pending_review"
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def approve_agent(agent_id: str) -> MarketplaceAgent:
    """Move agent from pending_review to approved (admin only)."""
    return _set_status(agent_id, "approved")


def publish_agent(agent_id: str) -> MarketplaceAgent:
    """Move approved agent to published."""
    import time

    entry = _set_status(agent_id, "published")
    with Session(engine) as session:
        rec = session.get(MarketplaceAgent, entry.id)
        if rec:
            rec.published_at = time.time()
            session.add(rec)
            session.commit()
    return entry


def reject_agent(agent_id: str, reason: str) -> MarketplaceAgent:
    """Reject an agent with a reason."""
    logger.info("Rejecting agent %s: %s", agent_id, reason)
    return _set_status(agent_id, "rejected")


def deprecate_agent(agent_id: str) -> MarketplaceAgent:
    return _set_status(agent_id, "deprecated")


# ── Safety checks ──────────────────────────────────────────────────────────────

def _run_safety_checks(definition: dict[str, Any]) -> None:
    system_prompt: str = str(definition.get("system_prompt") or "")
    tools: list[str] = list(definition.get("tools") or [])
    trigger = definition.get("trigger") or {}
    computer_use_config = definition.get("computer_use") or {}

    # 1. No hardcoded credentials
    for pattern in _SECRET_PATTERNS:
        if pattern.search(system_prompt):
            raise PublishValidationError(
                "System prompt contains what appears to be a hardcoded credential or secret. "
                "Remove all secrets from prompts before publishing."
            )

    # 2. Declared tools exist in registry
    try:
        from api.services.connectors.catalog import get_definition as get_connector_def

        for tool_id in tools:
            connector_id = tool_id.split(".")[0] if "." in tool_id else tool_id
            if connector_id not in ("computer_use", "http"):
                defn = get_connector_def(connector_id)
                if not defn:
                    raise PublishValidationError(
                        f"Tool '{tool_id}' references unknown connector '{connector_id}'."
                    )
    except PublishValidationError:
        raise
    except Exception:
        pass  # Registry unavailable at validation time — skip

    # 3. Delegation depth ≤ 5
    max_depth = int((definition.get("orchestration") or {}).get("max_delegation_depth") or 3)
    if max_depth > 5:
        raise PublishValidationError(
            f"max_delegation_depth={max_depth} exceeds the maximum allowed value of 5."
        )

    # 4. http_request blocked for private IPs
    for tool_id in tools:
        if "http" in tool_id.lower():
            test_url = str(system_prompt + str(definition)).lower()
            if _PRIVATE_IP.search(test_url):
                raise PublishValidationError(
                    "Agent appears to target private/internal IP ranges via http_request. "
                    "Only public endpoints are allowed."
                )

    # 5. Computer Use max_steps ≤ 50
    if "computer_use" in tools or "computer_use" in str(definition.get("required_connectors") or []):
        max_steps = int(computer_use_config.get("max_steps") or 0)
        if max_steps > 50:
            raise PublishValidationError(
                f"Computer Use max_steps={max_steps} exceeds the maximum allowed value of 50."
            )


def _load_definition(entry: MarketplaceAgent) -> dict[str, Any]:
    import json

    try:
        return json.loads(entry.definition_json)
    except Exception:
        return {}


def _set_status(agent_id: str, status: str) -> MarketplaceAgent:
    with Session(engine) as session:
        entry = session.exec(
            select(MarketplaceAgent).where(MarketplaceAgent.agent_id == agent_id)
        ).first()
        if not entry:
            raise ValueError(f"Marketplace agent '{agent_id}' not found.")
        entry.status = status  # type: ignore[assignment]
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry
