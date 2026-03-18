"""Advanced semantic memory with TF-IDF similarity scoring.

Stores structured episodes from agent executions and supports cosine-similarity
retrieval using TF-IDF vectors.  No external ML dependencies required.

Tables
------
  maia_agent_episode  -- one row per tool execution episode
"""
from __future__ import annotations

import logging
import math
import re
import time
import uuid
from collections import Counter
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------

class AgentEpisode(SQLModel, table=True):
    __tablename__ = "maia_agent_episode"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    run_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    tenant_id: str = Field(index=True)
    step_index: int = 0
    tool_id: str = ""
    params_summary: str = ""
    outcome_status: str = ""          # success | empty | failed | blocked | skipped
    evidence_summary: str = ""
    duration_ms: int = 0
    tokens_used: int = 0
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# TF-IDF helpers (zero-dependency)
# ---------------------------------------------------------------------------

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


def _build_tfidf_vector(
    tokens: list[str],
    idf_map: dict[str, float],
) -> dict[str, float]:
    """Term-frequency * inverse-document-frequency for a single document."""
    tf = Counter(tokens)
    doc_len = max(len(tokens), 1)
    vec: dict[str, float] = {}
    for term, count in tf.items():
        tf_val = count / doc_len
        idf_val = idf_map.get(term, 0.0)
        weight = tf_val * idf_val
        if weight > 0:
            vec[term] = weight
    return vec


def _cosine_similarity(
    vec_a: dict[str, float],
    vec_b: dict[str, float],
) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common_keys = set(vec_a.keys()) & set(vec_b.keys())
    if not common_keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common_keys)
    mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
    mag_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# SemanticMemoryStore
# ---------------------------------------------------------------------------

class SemanticMemoryStore:
    """Stores and retrieves agent episodes using TF-IDF cosine similarity."""

    def store_episode(
        self,
        *,
        run_id: str,
        agent_id: str,
        tenant_id: str,
        step_index: int,
        tool_id: str,
        params_summary: str,
        outcome_status: str,
        evidence_summary: str,
        duration_ms: int = 0,
        tokens_used: int = 0,
    ) -> AgentEpisode:
        """Record a structured episode from one tool execution."""
        _ensure_tables()
        episode = AgentEpisode(
            run_id=run_id,
            agent_id=agent_id,
            tenant_id=tenant_id,
            step_index=step_index,
            tool_id=tool_id,
            params_summary=params_summary[:1000],
            outcome_status=outcome_status,
            evidence_summary=evidence_summary[:2000],
            duration_ms=duration_ms,
            tokens_used=tokens_used,
        )
        with Session(engine) as session:
            session.add(episode)
            session.commit()
            session.refresh(episode)
        return episode

    def recall_similar(
        self,
        query: str,
        agent_id: str,
        tenant_id: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve the top-k most semantically similar episodes via TF-IDF cosine."""
        _ensure_tables()
        with Session(engine) as session:
            rows = session.exec(
                select(AgentEpisode)
                .where(AgentEpisode.tenant_id == tenant_id)
                .where(AgentEpisode.agent_id == agent_id)
                .order_by(AgentEpisode.created_at.desc())  # type: ignore[arg-type]
                .limit(500)
            ).all()

        if not rows:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return [_episode_to_dict(r) for r in rows[:top_k]]

        # Build corpus token lists
        corpus_tokens: list[list[str]] = []
        for row in rows:
            doc_text = f"{row.tool_id} {row.params_summary} {row.evidence_summary} {row.outcome_status}"
            corpus_tokens.append(_tokenize(doc_text))

        # Compute IDF across corpus
        n_docs = len(rows)
        doc_freq: Counter[str] = Counter()
        for tokens in corpus_tokens:
            unique = set(tokens)
            for t in unique:
                doc_freq[t] += 1

        idf_map: dict[str, float] = {}
        for term, df in doc_freq.items():
            idf_map[term] = math.log((n_docs + 1) / (df + 1)) + 1.0

        query_vec = _build_tfidf_vector(query_tokens, idf_map)

        scored: list[tuple[float, AgentEpisode]] = []
        for i, row in enumerate(rows):
            doc_vec = _build_tfidf_vector(corpus_tokens[i], idf_map)
            sim = _cosine_similarity(query_vec, doc_vec)
            scored.append((sim, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [_episode_to_dict(r) for score, r in scored[:top_k] if score > 0]

    def get_agent_episodes(
        self,
        agent_id: str,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent episodes for an agent, newest first."""
        _ensure_tables()
        with Session(engine) as session:
            rows = session.exec(
                select(AgentEpisode)
                .where(AgentEpisode.tenant_id == tenant_id)
                .where(AgentEpisode.agent_id == agent_id)
                .order_by(AgentEpisode.created_at.desc())  # type: ignore[arg-type]
                .limit(limit)
            ).all()
        return [_episode_to_dict(r) for r in rows]

    def summarize_agent_experience(
        self,
        agent_id: str,
        tenant_id: str,
    ) -> str:
        """Generate an LLM summary of what this agent has learned.

        Falls back to a statistical summary if the LLM call fails.
        """
        episodes = self.get_agent_episodes(agent_id, tenant_id, limit=100)
        if not episodes:
            return "No episodes recorded for this agent yet."

        # Build statistical summary as fallback / input
        tool_counts: Counter[str] = Counter()
        status_counts: Counter[str] = Counter()
        total_duration = 0
        for ep in episodes:
            tool_counts[ep["tool_id"]] += 1
            status_counts[ep["outcome_status"]] += 1
            total_duration += ep.get("duration_ms", 0)

        stats_lines = [
            f"Total episodes: {len(episodes)}",
            f"Tools used: {dict(tool_counts.most_common(10))}",
            f"Outcomes: {dict(status_counts)}",
            f"Total duration: {total_duration}ms",
        ]
        stats_summary = "\n".join(stats_lines)

        # Attempt LLM summary
        try:
            from api.services.agents.llm_utils import call_llm_json

            recent_details = []
            for ep in episodes[:20]:
                recent_details.append(
                    f"- {ep['tool_id']} ({ep['outcome_status']}): "
                    f"{ep.get('evidence_summary', '')[:150]}"
                )

            prompt = (
                "Summarize what this AI agent has learned from its execution history. "
                "Focus on: which tools work best, common failure patterns, and "
                "successful strategies.\n\n"
                f"Statistics:\n{stats_summary}\n\n"
                f"Recent episodes:\n" + "\n".join(recent_details) + "\n\n"
                "Reply with JSON: {\"summary\": \"...\"}"
            )
            result = call_llm_json(prompt, temperature=0.2, max_tokens=500)
            return str(result.get("summary") or stats_summary)
        except Exception as exc:
            logger.warning("LLM summary failed, returning stats: %s", exc)
            return stats_summary


def _episode_to_dict(r: AgentEpisode) -> dict[str, Any]:
    return {
        "id": r.id,
        "run_id": r.run_id,
        "agent_id": r.agent_id,
        "tenant_id": r.tenant_id,
        "step_index": r.step_index,
        "tool_id": r.tool_id,
        "params_summary": r.params_summary,
        "outcome_status": r.outcome_status,
        "evidence_summary": r.evidence_summary,
        "duration_ms": r.duration_ms,
        "tokens_used": r.tokens_used,
        "created_at": r.created_at,
    }
