"""B2-02 — Agent resolver (message routing).

Responsibility: given a user message and tenant context, determine which
installed agent should handle it.

Strategy (in order):
  1. Explicit ``@agent-name`` prefix in the message.
  2. LLM-based intent classification against installed agents' descriptions.
  3. Fallback: return None (caller falls through to Maia's default ask mode).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

_AT_PREFIX = re.compile(r"^@([\w-]+)\s*", re.UNICODE)


@dataclass
class AgentResolution:
    agent_id: str
    confidence: float
    reasoning: str
    matched_by: str  # "explicit_prefix" | "llm_intent" | "default"


def resolve_agent(
    tenant_id: str,
    message: str,
    *,
    user_id: str = "",
) -> Optional[AgentResolution]:
    """Return the best agent for this message, or None for Maia default handling."""
    message = (message or "").strip()
    if not message:
        return None

    # Strategy 1: explicit @agent-name prefix
    match = _AT_PREFIX.match(message)
    if match:
        slug = match.group(1).lower()
        resolution = _resolve_by_slug(tenant_id, slug)
        if resolution:
            return resolution
        logger.debug("@%s mentioned but no matching agent found in tenant %s", slug, tenant_id)

    # Strategy 2: LLM-based intent classification
    try:
        return _resolve_by_llm(tenant_id, message)
    except Exception:
        logger.debug("LLM intent classification failed", exc_info=True)

    return None


# ── Private helpers ────────────────────────────────────────────────────────────

def _resolve_by_slug(tenant_id: str, slug: str) -> Optional[AgentResolution]:
    """Find an agent whose id or name slug matches."""
    from api.services.agents.definition_store import list_agents, load_schema

    for record in list_agents(tenant_id):
        schema = load_schema(record)
        if record.agent_id == slug or _slugify(schema.name) == slug:
            return AgentResolution(
                agent_id=record.agent_id,
                confidence=1.0,
                reasoning=f"Explicit @{slug} prefix matched agent '{schema.name}'.",
                matched_by="explicit_prefix",
            )
    return None


def _resolve_by_llm(tenant_id: str, message: str) -> Optional[AgentResolution]:
    """Use the LLM to pick the best installed agent for the message."""
    from api.services.agents.definition_store import list_agents, load_schema

    agents = list_agents(tenant_id)
    if not agents:
        return None

    descriptions = []
    for record in agents:
        try:
            schema = load_schema(record)
            descriptions.append(
                f"- id={record.agent_id}  name={schema.name}  desc={schema.description or '(none)'}"
            )
        except Exception:
            pass

    if not descriptions:
        return None

    prompt = (
        "You are a routing assistant. Given the user's message and the list of available agents, "
        "choose the single best agent to handle the message. Reply with JSON: "
        "{\"agent_id\": \"<id>\", \"confidence\": <0.0-1.0>, \"reasoning\": \"<short reason>\"}. "
        "If no agent is a good fit, reply {\"agent_id\": null}.\n\n"
        f"User message: {message[:500]}\n\n"
        f"Available agents:\n" + "\n".join(descriptions)
    )

    try:
        import json
        from api.services.agents.llm_utils import call_llm_json

        result = call_llm_json(prompt, temperature=0.0, max_tokens=200)
        agent_id = result.get("agent_id")
        if not agent_id:
            return None
        return AgentResolution(
            agent_id=str(agent_id),
            confidence=float(result.get("confidence", 0.5)),
            reasoning=str(result.get("reasoning", "")),
            matched_by="llm_intent",
        )
    except Exception:
        logger.debug("LLM routing call failed", exc_info=True)
        return None


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", (text or "").lower()).strip("-")
