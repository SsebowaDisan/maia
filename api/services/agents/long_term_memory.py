"""P7-01 — Long-term agent memory store.

Responsibility: persist facts/observations per (tenant_id, agent_id) and recall
relevant memories using keyword-overlap scoring (BM25-style, no extra deps).

Schema
------
  maia_agent_memory  — one row per stored fact
    id               — uuid primary key
    tenant_id        — scoped per tenant (never crosses tenants)
    agent_id         — scoped per agent
    content          — the fact string
    tags_json        — JSON list of string tags
    recorded_at      — unix timestamp
"""
from __future__ import annotations

import json
import math
import re
import time
import uuid
from collections import Counter
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine


# ── ORM ───────────────────────────────────────────────────────────────────────

class AgentMemoryRecord(SQLModel, table=True):
    __tablename__ = "maia_agent_memory"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    content: str
    tags_json: str = "[]"
    recorded_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Text utilities ─────────────────────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would could should may might must shall can to of in on at "
    "for by with from as into through out over under between and or but "
    "not no it its this that these those i me my we our you your he she "
    "they them his her their what when where who how".split()
)


def _tokenize(text: str) -> list[str]:
    return [
        w.lower()
        for w in re.findall(r"[a-zA-Z0-9]+", text)
        if w.lower() not in _STOP_WORDS and len(w) > 1
    ]


def _bm25_score(query_tokens: list[str], doc_tokens: list[str], corpus_size: int, avg_dl: float) -> float:
    """Simplified BM25 score (k1=1.5, b=0.75)."""
    k1, b = 1.5, 0.75
    doc_len = len(doc_tokens)
    tf_map = Counter(doc_tokens)
    score = 0.0
    for token in query_tokens:
        tf = tf_map.get(token, 0)
        if tf == 0:
            continue
        idf = math.log((corpus_size - 1 + 0.5) / (1 + 0.5) + 1)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avg_dl, 1)))
        score += idf * tf_norm
    return score


# ── Public API ─────────────────────────────────────────────────────────────────

def store_memory(
    tenant_id: str,
    agent_id: str,
    content: str,
    tags: list[str] | None = None,
) -> AgentMemoryRecord:
    """Persist a new memory fact."""
    _ensure_tables()
    record = AgentMemoryRecord(
        tenant_id=tenant_id,
        agent_id=agent_id,
        content=content.strip(),
        tags_json=json.dumps(tags or []),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def recall_memories(
    tenant_id: str,
    agent_id: str,
    query: str,
    k: int = 5,
) -> list[dict[str, Any]]:
    """Return the top-k most relevant memories for a query."""
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(AgentMemoryRecord)
            .where(AgentMemoryRecord.tenant_id == tenant_id)
            .where(AgentMemoryRecord.agent_id == agent_id)
        ).all()

    if not rows:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        # No meaningful query tokens; return most recent k
        rows_sorted = sorted(rows, key=lambda r: r.recorded_at, reverse=True)
        return [_record_to_dict(r) for r in rows_sorted[:k]]

    all_tokens = [_tokenize(r.content) for r in rows]
    avg_dl = sum(len(t) for t in all_tokens) / max(len(all_tokens), 1)
    corpus_size = len(rows)

    scored = [
        (_bm25_score(query_tokens, all_tokens[i], corpus_size, avg_dl), rows[i])
        for i in range(len(rows))
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_record_to_dict(r) for _, r in scored[:k] if _ > 0]


def list_memories(tenant_id: str, agent_id: str) -> list[dict[str, Any]]:
    """Return all stored memories for an agent, newest first."""
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(AgentMemoryRecord)
            .where(AgentMemoryRecord.tenant_id == tenant_id)
            .where(AgentMemoryRecord.agent_id == agent_id)
            .order_by(AgentMemoryRecord.recorded_at.desc())  # type: ignore[arg-type]
        ).all()
    return [_record_to_dict(r) for r in rows]


def delete_memory(tenant_id: str, agent_id: str, memory_id: str) -> bool:
    _ensure_tables()
    with Session(engine) as session:
        record = session.get(AgentMemoryRecord, memory_id)
        if not record or record.tenant_id != tenant_id or record.agent_id != agent_id:
            return False
        session.delete(record)
        session.commit()
    return True


def clear_memories(tenant_id: str, agent_id: str) -> int:
    _ensure_tables()
    with Session(engine) as session:
        rows = session.exec(
            select(AgentMemoryRecord)
            .where(AgentMemoryRecord.tenant_id == tenant_id)
            .where(AgentMemoryRecord.agent_id == agent_id)
        ).all()
        for r in rows:
            session.delete(r)
        session.commit()
        return len(rows)


def _record_to_dict(r: AgentMemoryRecord) -> dict[str, Any]:
    return {
        "id": r.id,
        "tenant_id": r.tenant_id,
        "agent_id": r.agent_id,
        "content": r.content,
        "tags": json.loads(r.tags_json or "[]"),
        "recorded_at": r.recorded_at,
    }
