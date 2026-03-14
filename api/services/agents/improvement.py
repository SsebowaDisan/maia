"""B6-03 — Agent self-improvement feedback loop.

Responsibility: record corrected outputs and generate system-prompt
improvement suggestions after enough feedback is collected.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)

_MIN_FEEDBACK_FOR_SUGGESTION = 10


class FeedbackRecord(SQLModel, table=True):
    __tablename__ = "maia_feedback"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    run_id: str
    original_output: str
    corrected_output: str
    feedback_type: str = "correction"  # "correction" | "approval" | "rejection"
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def record_feedback(
    tenant_id: str,
    agent_id: str,
    run_id: str,
    original_output: str,
    corrected_output: str,
    feedback_type: str = "correction",
) -> FeedbackRecord:
    """Persist one feedback record for an agent run."""
    _ensure_tables()
    record = FeedbackRecord(
        tenant_id=tenant_id,
        agent_id=agent_id,
        run_id=run_id,
        original_output=original_output[:3000],
        corrected_output=corrected_output[:3000],
        feedback_type=feedback_type,
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def list_feedback(tenant_id: str, agent_id: str, *, limit: int = 50) -> Sequence[FeedbackRecord]:
    with Session(engine) as session:
        return session.exec(
            select(FeedbackRecord)
            .where(FeedbackRecord.tenant_id == tenant_id)
            .where(FeedbackRecord.agent_id == agent_id)
            .order_by(FeedbackRecord.created_at.desc())  # type: ignore[attr-defined]
            .limit(limit)
        ).all()


def generate_improvement_suggestion(
    tenant_id: str,
    agent_id: str,
) -> Optional[dict[str, Any]]:
    """Generate a system-prompt improvement suggestion using the LLM.

    Returns None if not enough feedback has been collected.
    Returns dict with keys: suggested_prompt, reasoning, feedback_count.
    """
    records = list_feedback(tenant_id, agent_id, limit=100)
    if len(records) < _MIN_FEEDBACK_FOR_SUGGESTION:
        return None

    from api.services.agents.definition_store import get_agent, load_schema

    agent_record = get_agent(tenant_id, agent_id)
    if not agent_record:
        return None

    schema = load_schema(agent_record)
    current_prompt = schema.system_prompt or ""

    # Build examples from feedback
    examples = []
    for r in records[:20]:  # use last 20 feedback items
        examples.append(
            f"Original: {r.original_output[:400]}\n"
            f"Correction: {r.corrected_output[:400]}\n"
        )

    prompt = (
        "You are an AI system prompt engineer. Given the current system prompt and examples of "
        "incorrect outputs with corrections, suggest an improved system prompt that reduces "
        "similar mistakes.\n\n"
        f"Current system prompt:\n{current_prompt[:1000]}\n\n"
        f"Feedback examples:\n" + "\n---\n".join(examples[:10]) + "\n\n"
        "Reply with JSON: {\"suggested_prompt\": \"...\", \"reasoning\": \"...\"}"
    )

    try:
        from api.services.agents.llm_utils import call_llm_json

        result = call_llm_json(prompt, temperature=0.2, max_tokens=1000)
        return {
            "suggested_prompt": str(result.get("suggested_prompt") or ""),
            "reasoning": str(result.get("reasoning") or ""),
            "feedback_count": len(records),
            "agent_id": agent_id,
        }
    except Exception as exc:
        logger.error("Improvement suggestion LLM call failed: %s", exc)
        return None
