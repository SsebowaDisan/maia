"""Agent Collaboration Logs — tracks inter-agent conversations during workflow runs.

Responsibility: when agents hand off tasks, debate, or delegate within a workflow,
this service records the conversation between them so users can see how the team
collaborated to produce the final result.

Each log entry captures: which agent spoke, what they said to whom, and the context.
"""
from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class CollaborationEntry:
    __slots__ = ("run_id", "from_agent", "to_agent", "message", "entry_type", "timestamp", "metadata")

    def __init__(self, *, run_id: str, from_agent: str, to_agent: str, message: str, entry_type: str = "message", metadata: dict[str, Any] | None = None):
        self.run_id = run_id
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.message = message
        self.entry_type = entry_type
        self.timestamp = time.time()
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message": self.message,
            "entry_type": self.entry_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class CollaborationLogService:
    """Stores and retrieves inter-agent collaboration logs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._logs: dict[str, list[CollaborationEntry]] = {}

    def record(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        message: str,
        entry_type: str = "message",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a collaboration entry between two agents."""
        entry = CollaborationEntry(
            run_id=run_id, from_agent=from_agent, to_agent=to_agent,
            message=message, entry_type=entry_type, metadata=metadata,
        )
        with self._lock:
            self._logs.setdefault(run_id, []).append(entry)
        # Emit as live event
        try:
            from api.services.agent.live_events import get_live_event_broker
            get_live_event_broker().publish(
                user_id="", run_id=run_id,
                event={
                    "event_type": "agent_collaboration",
                    "title": f"{from_agent} → {to_agent}",
                    "detail": message[:300],
                    "stage": "execute",
                    "status": "info",
                    "data": entry.to_dict(),
                },
            )
        except Exception:
            pass
        return entry.to_dict()

    def record_handoff(self, *, run_id: str, from_agent: str, to_agent: str, task: str, context: str = "") -> dict[str, Any]:
        return self.record(run_id=run_id, from_agent=from_agent, to_agent=to_agent, message=f"Handing off: {task}", entry_type="handoff", metadata={"task": task, "context": context})

    def record_question(self, *, run_id: str, from_agent: str, to_agent: str, question: str) -> dict[str, Any]:
        return self.record(run_id=run_id, from_agent=from_agent, to_agent=to_agent, message=question, entry_type="question")

    def record_response(self, *, run_id: str, from_agent: str, to_agent: str, response: str) -> dict[str, Any]:
        return self.record(run_id=run_id, from_agent=from_agent, to_agent=to_agent, message=response, entry_type="response")

    def record_disagreement(self, *, run_id: str, from_agent: str, to_agent: str, point: str) -> dict[str, Any]:
        return self.record(run_id=run_id, from_agent=from_agent, to_agent=to_agent, message=point, entry_type="disagreement")

    def get_log(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._logs.get(run_id, [])
        return [e.to_dict() for e in entries]

    def get_summary(self, run_id: str) -> dict[str, Any]:
        log = self.get_log(run_id)
        agents = set()
        for entry in log:
            agents.add(entry["from_agent"])
            agents.add(entry["to_agent"])
        return {
            "run_id": run_id,
            "total_entries": len(log),
            "agents_involved": sorted(agents),
            "handoffs": sum(1 for e in log if e["entry_type"] == "handoff"),
            "questions": sum(1 for e in log if e["entry_type"] == "question"),
            "disagreements": sum(1 for e in log if e["entry_type"] == "disagreement"),
        }


_service: CollaborationLogService | None = None


def get_collaboration_service() -> CollaborationLogService:
    global _service
    if _service is None:
        _service = CollaborationLogService()
    return _service
