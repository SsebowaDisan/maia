"""ACP message builders — convenience functions for creating well-formed payloads."""

from __future__ import annotations

import time
import uuid
from typing import Any

from maia_acp.types import (
    ACPActivity,
    ACPArtifact,
    ACPCapabilities,
    ACPEvent,
    ACPHandoff,
    ACPMessage,
    ACPReview,
    AgentPersonality,
    AgentSkill,
    HandoffTask,
    ReviewIssue,
)

_sequence_counter = 0


def _next_seq() -> int:
    global _sequence_counter
    _sequence_counter += 1
    return _sequence_counter


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _uid() -> str:
    return uuid.uuid4().hex[:12]


# ── Envelope ──────────────────────────────────────────────────────────────────

def envelope(
    agent_id: str,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    parent_event_id: str | None = None,
) -> ACPEvent:
    return ACPEvent(
        acp_version="1.0",
        run_id=run_id,
        agent_id=agent_id,
        event_type=event_type,  # type: ignore[arg-type]
        timestamp=_now(),
        sequence=_next_seq(),
        parent_event_id=parent_event_id,
        payload=payload,
    )


# ── Message ───────────────────────────────────────────────────────────────────

def message(
    *,
    from_agent: str,
    to: str,
    intent: str,
    content: str,
    thinking: str | None = None,
    mood: str | None = None,
    message_id: str | None = None,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
    task_id: str | None = None,
    task_title: str | None = None,
    handoff_id: str | None = None,
    review_id: str | None = None,
    channel: str | None = None,
    mentions: list[str] | None = None,
    requires_ack: bool | None = None,
    delivery_status: str | None = None,
    acked_by: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "from": from_agent,
        "to": to,
        "intent": intent,
        "content": content,
        "thinking": thinking,
        "mood": mood,
        "artifacts": [],
        "context": {
            "message_id": message_id or f"msg_{_uid()}",
            "thread_id": thread_id or f"thread_{_uid()}",
            "in_reply_to": in_reply_to,
            "task_id": task_id,
            "task_title": task_title,
            "handoff_id": handoff_id,
            "review_id": review_id,
            "channel": channel or ("broadcast" if to == "agent://broadcast" else "direct"),
            "mentions": mentions or [],
            "requires_ack": requires_ack,
            "delivery_status": delivery_status,
            "acked_by": acked_by or [],
        },
    }


# ── Handoff ───────────────────────────────────────────────────────────────────

def handoff(
    *,
    from_agent: str,
    to: str,
    description: str,
    task_id: str | None = None,
    thread_id: str | None = None,
    constraints: list[str] | None = None,
    definition_of_done: str | None = None,
    deadline_seconds: int | None = None,
    priority: str = "normal",
    owner_agent_id: str | None = None,
    status: str | None = None,
    blockers: list[str] | None = None,
    handoff_id: str | None = None,
    requires_ack: bool | None = None,
    accepted_by: str | None = None,
    declined_reason: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "from": from_agent,
        "to": to,
        "task": {
            "task_id": task_id or f"task_{_uid()}",
            "thread_id": thread_id,
            "description": description,
            "constraints": constraints or [],
            "definition_of_done": definition_of_done,
            "deadline_seconds": deadline_seconds,
            "priority": priority,
            "owner_agent_id": owner_agent_id,
            "status": status or "proposed",
            "blockers": blockers or [],
        },
        "handoff_id": handoff_id or f"handoff_{_uid()}",
        "status": status or "proposed",
        "requires_ack": requires_ack,
        "accepted_by": accepted_by,
        "declined_reason": declined_reason,
        "context": context or {},
        "artifacts": [],
        "prior_steps": [],
    }


# ── Review ────────────────────────────────────────────────────────────────────

def review(
    *,
    reviewer: str,
    author: str,
    verdict: str,
    feedback: str | None = None,
    score: float | None = None,
    revision_instructions: str | None = None,
    strengths: list[str] | None = None,
    issues: list[dict[str, Any]] | None = None,
    round: int = 1,
) -> dict[str, Any]:
    return {
        "reviewer": reviewer,
        "author": author,
        "verdict": verdict,
        "feedback": feedback,
        "score": score,
        "revision_instructions": revision_instructions,
        "strengths": strengths or [],
        "issues": issues or [],
        "round": round,
        "max_rounds": 3,
    }


# ── Artifact ──────────────────────────────────────────────────────────────────

def artifact(
    *,
    kind: str,
    title: str,
    content: str,
    mime_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": f"artifact_{_uid()}",
        "kind": kind,
        "title": title,
        "content": content,
        "mime_type": mime_type,
        "metadata": metadata or {},
        "version": 1,
    }


# ── Activity ──────────────────────────────────────────────────────────────────

def activity(
    *,
    agent_id: str,
    activity_type: str,
    detail: str | None = None,
    tool: dict[str, Any] | None = None,
    browser: dict[str, Any] | None = None,
    cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "activity": activity_type,
        "detail": detail,
        "tool": tool,
        "browser": browser,
        "cost": cost,
    }


# ── Capabilities ──────────────────────────────────────────────────────────────

def capabilities(
    *,
    agent_id: str,
    name: str,
    description: str | None = None,
    role: str | None = None,
    personality: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
    connectors: list[str] | None = None,
    accepts_intents: list[str] | None = None,
    max_concurrent_tasks: int = 1,
    presence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "name": name,
        "description": description,
        "role": role,
        "personality": personality,
        "skills": skills or [],
        "connectors": connectors or [],
        "accepts_intents": accepts_intents or [],
        "max_concurrent_tasks": max_concurrent_tasks,
        "presence": presence,
    }
