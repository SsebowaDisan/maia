"""P7-03 — memory.recall agent tool.

Allows an agent to query its long-term memory store and retrieve relevant facts.

Tool schema (as expected by the step planner):
    tool_id:   "memory.recall"
    input:     { "query": "<search text>", "k": 5 }
    output:    { "memories": [{ "content": "...", "recorded_at": ... }, ...] }
"""
from __future__ import annotations

from typing import Any


TOOL_ID = "memory.recall"
TOOL_DESCRIPTION = (
    "Retrieve relevant facts from the agent's long-term memory. "
    "Input: {query: string, k?: int (default 5)}. "
    "Returns a list of the most relevant stored memories."
)


def run(
    *,
    tenant_id: str,
    agent_id: str,
    query: str,
    k: int = 5,
) -> dict[str, Any]:
    """Return top-k relevant memories for the given query."""
    from api.services.agents.long_term_memory import recall_memories

    if not query or not str(query).strip():
        return {"memories": [], "error": "query must not be empty"}

    memories = recall_memories(
        tenant_id=tenant_id,
        agent_id=agent_id,
        query=str(query).strip(),
        k=max(1, min(int(k), 20)),
    )
    return {"memories": memories, "count": len(memories)}
