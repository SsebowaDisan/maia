"""Agent Memory API — expose memory system for viewing and management.

Endpoints:
    GET  /api/agent/memory                — list all memories for the user
    GET  /api/agent/memory/:agent_id      — memories for a specific agent
    DELETE /api/agent/memory/:memory_id   — delete a specific memory
    POST /api/agent/memory/clear          — clear all memories
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent/memory", tags=["agent-memory"])


def _memory_dir(user_id: str) -> Path:
    root = Path(".maia_agent") / "memory" / user_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_memories(user_id: str) -> list[dict[str, Any]]:
    """Load all memory entries for a user."""
    memories: list[dict[str, Any]] = []
    # Check semantic memory store
    try:
        from api.services.agent.memory.semantic_memory import get_semantic_memory
        sm = get_semantic_memory()
        entries = sm.recall(user_id=user_id, query="", top_k=100)
        for entry in entries:
            memories.append({
                "id": str(entry.get("id", "")),
                "agent_id": str(entry.get("agent_id", "")),
                "content": str(entry.get("content", entry.get("text", ""))),
                "category": str(entry.get("category", "general")),
                "created_at": entry.get("created_at", ""),
                "source": "semantic",
            })
    except Exception:
        pass

    # Check evolution store (cross-run lessons)
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=user_id)
        lessons = store.get_lessons(max_results=50)
        for lesson in lessons:
            memories.append({
                "id": lesson.get("source_run_id", ""),
                "agent_id": "",
                "content": lesson.get("lesson", ""),
                "category": lesson.get("category", "pipeline"),
                "created_at": lesson.get("created_at", ""),
                "source": "evolution",
                "weight": lesson.get("_weight", 0),
            })
    except Exception:
        pass

    # Check file-based memory
    mem_dir = _memory_dir(user_id)
    for fpath in sorted(mem_dir.glob("*.json")):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    memories.append({**item, "source": "file", "id": item.get("id", fpath.stem)})
            elif isinstance(data, dict):
                memories.append({**data, "source": "file", "id": data.get("id", fpath.stem)})
        except Exception:
            pass

    return memories


@router.get("")
def list_memories(user_id: str = Depends(get_current_user_id)) -> list[dict[str, Any]]:
    """List all agent memories for the current user."""
    return _load_memories(user_id)


@router.get("/{agent_id}")
def list_agent_memories(agent_id: str, user_id: str = Depends(get_current_user_id)) -> list[dict[str, Any]]:
    """List memories for a specific agent."""
    all_memories = _load_memories(user_id)
    return [m for m in all_memories if m.get("agent_id") == agent_id or not m.get("agent_id")]


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    """Delete a specific memory entry."""
    try:
        from api.services.agent.memory.semantic_memory import get_semantic_memory
        sm = get_semantic_memory()
        sm.forget(user_id=user_id, memory_id=memory_id)
        return {"status": "deleted", "memory_id": memory_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/clear")
def clear_memories(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    """Clear all memories for the current user."""
    count = 0
    try:
        from api.services.agent.memory.semantic_memory import get_semantic_memory
        sm = get_semantic_memory()
        count = sm.clear(user_id=user_id)
    except Exception:
        pass
    # Clear evolution store
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=user_id)
        count += store.clear_expired()
    except Exception:
        pass
    return {"status": "cleared", "count": count}
