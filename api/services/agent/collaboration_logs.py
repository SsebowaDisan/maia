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
        self._append_to_activity_store(entry)
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

    def record_question(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        question: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(metadata or {})
        payload.setdefault("event_type", "agent_dialogue_turn")
        return self.record(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message=question,
            entry_type="question",
            metadata=payload,
        )

    def record_response(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(metadata or {})
        payload.setdefault("event_type", "agent_dialogue_turn")
        return self.record(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message=response,
            entry_type="response",
            metadata=payload,
        )

    def record_disagreement(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        point: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(metadata or {})
        payload.setdefault("event_type", "agent_dialogue_turn")
        return self.record(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message=point,
            entry_type="disagreement",
            metadata=payload,
        )

    def get_log(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            entries = self._logs.get(run_id, [])
        if entries:
            return [e.to_dict() for e in entries]

        # Fallback to persisted activity events so conversation history
        # survives process restarts and multi-worker setups.
        try:
            from api.services.agent.activity import get_activity_store

            rows = get_activity_store().load_events(run_id)
            restored: list[dict[str, Any]] = []
            for row in rows:
                if not isinstance(row, dict) or row.get("type") != "event":
                    continue
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                event_type = str(payload.get("event_type") or "").strip().lower()
                if event_type not in {
                    "team_chat_message",
                    "agent_dialogue_turn",
                }:
                    continue
                data = payload.get("data")
                data_map = data if isinstance(data, dict) else {}
                restored.append(
                    {
                        "run_id": run_id,
                        "from_agent": str(
                            data_map.get("from_agent")
                            or data_map.get("speaker_id")
                            or data_map.get("speaker_name")
                            or data_map.get("source_agent")
                            or payload.get("agent_id")
                            or "agent"
                        ).strip(),
                        "to_agent": str(
                            data_map.get("to_agent")
                            or data_map.get("audience")
                            or data_map.get("recipient")
                            or data_map.get("target_agent")
                            or data_map.get("next_agent")
                            or "team"
                        ).strip(),
                        "message": str(
                            data_map.get("message")
                            or data_map.get("content")
                            or data_map.get("question")
                            or data_map.get("answer")
                            or data_map.get("reasoning")
                            or data_map.get("feedback")
                            or data_map.get("summary")
                            or payload.get("detail")
                            or payload.get("title")
                            or ""
                        ).strip(),
                        "entry_type": str(
                            data_map.get("entry_type")
                            if event_type == "team_chat_message"
                            else data_map.get("turn_role")
                            or data_map.get("turn_type")
                            or data_map.get("entry_type")
                            or data_map.get("message_type")
                            or "message"
                        ).strip().lower(),
                        "timestamp": data_map.get("timestamp") or payload.get("timestamp") or payload.get("ts"),
                        "metadata": data_map,
                    }
                )
            return restored
        except Exception:
            return []

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

    def _append_to_activity_store(self, entry: CollaborationEntry) -> None:
        try:
            from api.services.agent.activity import get_activity_store
            from api.services.agent.models import AgentActivityEvent, new_id

            payload = entry.to_dict()
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            event_type = str(metadata.get("event_type") or "").strip().lower()
            if not event_type:
                if entry.entry_type == "chat":
                    event_type = "team_chat_message"
                elif entry.entry_type in {"question", "response", "disagreement"}:
                    event_type = "agent_dialogue_turn"
                else:
                    event_type = "agent_collaboration"
            event = AgentActivityEvent(
                event_id=new_id("evt"),
                run_id=entry.run_id,
                event_type=event_type,
                title=f"{entry.from_agent} -> {entry.to_agent}",
                detail=str(entry.message or "")[:300],
                stage="execute",
                status="info",
                metadata=payload,
                data=payload,
            )
            get_activity_store().append(event)
        except Exception:
            logger.debug("Failed to persist collaboration entry for run %s", entry.run_id, exc_info=True)


_service: CollaborationLogService | None = None


def get_collaboration_service() -> CollaborationLogService:
    global _service
    if _service is None:
        _service = CollaborationLogService()
    return _service
