"""P7-02 — memory.store agent tool.

Allows an agent to persist a fact to its long-term memory store during a run.

Tool schema (as expected by the step planner):
    tool_id:   "memory.store"
    input:     { "content": "<fact text>", "tags": ["optional", "tags"] }
    output:    { "id": "<uuid>", "stored": true }
"""
from __future__ import annotations

from typing import Any


TOOL_ID = "memory.store"
TOOL_DESCRIPTION = (
    "Store a fact or observation in the agent's long-term memory. "
    "The fact will be available in future runs via memory.recall. "
    "Input: {content: string, tags?: string[]}."
)


def run(
    *,
    tenant_id: str,
    agent_id: str,
    content: str,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Persist content to long-term memory and return the record id."""
    from api.services.agents.long_term_memory import store_memory

    if not content or not str(content).strip():
        return {"stored": False, "error": "content must not be empty"}

    record = store_memory(
        tenant_id=tenant_id,
        agent_id=agent_id,
        content=str(content).strip(),
        tags=list(tags) if tags else [],
    )
    return {"id": record.id, "stored": True}
