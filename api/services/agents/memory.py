"""B2-04 — Agent memory layer.

Responsibility: three-tier memory for agent runs.

  WorkingMemory  — per-conversation key-value store (DB-backed, TTL-pruned).
  EpisodicMemory — per-tenant per-agent timestamped episode log with vector recall.
  SemanticMemory — wraps existing RAG index for company knowledge retrieval.

No Redis dependency — working memory uses the existing SQLite/Postgres DB engine.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


# ── Models ─────────────────────────────────────────────────────────────────────

class WorkingMemoryEntry(SQLModel, table=True):
    __tablename__ = "maia_working_memory"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    conversation_id: str = Field(index=True)
    key: str
    value_json: str
    expires_at: float  # Unix timestamp


class EpisodicMemoryEntry(SQLModel, table=True):
    __tablename__ = "maia_episodic_memory"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    run_id: str
    summary: str
    outcome: str  # "success" | "failure" | "partial"
    embedding_json: Optional[str] = None  # serialised float list
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ── Working Memory ─────────────────────────────────────────────────────────────

class WorkingMemory:
    """Per-conversation key-value store with TTL."""

    def __init__(self, tenant_id: str, conversation_id: str, ttl_seconds: int = 3600) -> None:
        self.tenant_id = tenant_id
        self.conversation_id = conversation_id
        self.ttl_seconds = ttl_seconds
        _ensure_tables()

    def set(self, key: str, value: Any) -> None:
        expires_at = time.time() + self.ttl_seconds
        with Session(engine) as session:
            existing = session.exec(
                select(WorkingMemoryEntry)
                .where(WorkingMemoryEntry.tenant_id == self.tenant_id)
                .where(WorkingMemoryEntry.conversation_id == self.conversation_id)
                .where(WorkingMemoryEntry.key == key)
            ).first()
            if existing:
                existing.value_json = json.dumps(value)
                existing.expires_at = expires_at
                session.add(existing)
            else:
                entry = WorkingMemoryEntry(
                    tenant_id=self.tenant_id,
                    conversation_id=self.conversation_id,
                    key=key,
                    value_json=json.dumps(value),
                    expires_at=expires_at,
                )
                session.add(entry)
            session.commit()

    def get(self, key: str, default: Any = None) -> Any:
        now = time.time()
        with Session(engine) as session:
            entry = session.exec(
                select(WorkingMemoryEntry)
                .where(WorkingMemoryEntry.tenant_id == self.tenant_id)
                .where(WorkingMemoryEntry.conversation_id == self.conversation_id)
                .where(WorkingMemoryEntry.key == key)
                .where(WorkingMemoryEntry.expires_at > now)
            ).first()
        if entry is None:
            return default
        try:
            return json.loads(entry.value_json)
        except Exception:
            return default

    def clear(self) -> None:
        with Session(engine) as session:
            entries = session.exec(
                select(WorkingMemoryEntry)
                .where(WorkingMemoryEntry.tenant_id == self.tenant_id)
                .where(WorkingMemoryEntry.conversation_id == self.conversation_id)
            ).all()
            for e in entries:
                session.delete(e)
            session.commit()


# ── Episodic Memory ────────────────────────────────────────────────────────────

def record_episode(
    tenant_id: str,
    agent_id: str,
    run_id: str,
    summary: str,
    outcome: str = "success",
) -> None:
    """Persist an episode summary for future recall."""
    _ensure_tables()
    embedding = _embed(summary)
    entry = EpisodicMemoryEntry(
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
        summary=summary,
        outcome=outcome,
        embedding_json=json.dumps(embedding) if embedding else None,
    )
    with Session(engine) as session:
        session.add(entry)
        session.commit()
    logger.debug("Recorded episode for agent %s run %s", agent_id, run_id)


def recall_episodes(
    tenant_id: str,
    agent_id: str,
    query: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the most relevant past episodes for a query.

    Uses cosine similarity when embeddings are available; falls back to
    keyword overlap when the embedding service is unavailable.
    """
    with Session(engine) as session:
        rows = session.exec(
            select(EpisodicMemoryEntry)
            .where(EpisodicMemoryEntry.tenant_id == tenant_id)
            .where(EpisodicMemoryEntry.agent_id == agent_id)
            .order_by(EpisodicMemoryEntry.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit * 10)
        ).all()

    if not rows:
        return []

    query_emb = _embed(query)
    scored: list[tuple[float, EpisodicMemoryEntry]] = []

    for row in rows:
        if query_emb and row.embedding_json:
            try:
                row_emb = json.loads(row.embedding_json)
                score = _cosine(query_emb, row_emb)
            except Exception:
                score = _keyword_overlap(query, row.summary)
        else:
            score = _keyword_overlap(query, row.summary)
        scored.append((score, row))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [
        {
            "run_id": row.run_id,
            "summary": row.summary,
            "outcome": row.outcome,
            "created_at": row.created_at,
            "relevance": round(score, 4),
        }
        for score, row in scored[:limit]
    ]


# ── Semantic Memory ────────────────────────────────────────────────────────────

def recall_knowledge(tenant_id: str, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve snippets from the tenant's RAG document index."""
    try:
        from api.context import get_context  # type: ignore[import]

        ctx = get_context()
        pipeline = getattr(ctx, "pipeline", None) or getattr(ctx, "index", None)
        if pipeline is None:
            return []
        results = pipeline.search(query, top_k=limit)
        return [
            {"text": str(r.get("text") or r.get("content") or ""), "score": float(r.get("score") or 0.0)}
            for r in (results or [])
        ]
    except Exception:
        logger.debug("Semantic recall failed", exc_info=True)
        return []


# ── Embedding helpers ──────────────────────────────────────────────────────────

def _embed(text: str) -> list[float] | None:
    """Embed text using the existing embedding model, if available."""
    try:
        from api.context import get_context  # type: ignore[import]

        ctx = get_context()
        embedder = getattr(ctx, "embedder", None)
        if embedder is None:
            return None
        result = embedder.embed(text)
        return list(result) if result is not None else None
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _keyword_overlap(query: str, text: str) -> float:
    q_words = set(query.lower().split())
    t_words = set(text.lower().split())
    if not q_words:
        return 0.0
    return len(q_words & t_words) / len(q_words)
