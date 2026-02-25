from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.agent.events import EVENT_SCHEMA_VERSION
from api.services.agent.models import AgentActivityEvent, new_id, utc_now


def _storage_root() -> Path:
    return Path(".maia_agent") / "activity"


def _run_file_path(run_id: str) -> Path:
    return _storage_root() / f"{run_id}.jsonl"


@dataclass
class AgentRunHeader:
    run_id: str
    user_id: str
    conversation_id: str
    mode: str
    goal: str
    started_at: str
    event_schema_version: str = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "mode": self.mode,
            "goal": self.goal,
            "started_at": self.started_at,
            "event_schema_version": self.event_schema_version,
        }


class ActivityStore:
    def __init__(self) -> None:
        self._lock = Lock()
        _storage_root().mkdir(parents=True, exist_ok=True)

    def start_run(
        self,
        *,
        user_id: str,
        conversation_id: str,
        mode: str,
        goal: str,
    ) -> AgentRunHeader:
        run_id = new_id("run")
        header = AgentRunHeader(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            mode=mode,
            goal=goal,
            started_at=utc_now().isoformat(),
        )
        file_path = _run_file_path(run_id)
        with self._lock:
            with file_path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "run_started", "payload": header.to_dict()}))
                handle.write("\n")
        return header

    def append(self, event: AgentActivityEvent) -> None:
        file_path = _run_file_path(event.run_id)
        row = {"type": "event", "payload": event.to_dict()}
        with self._lock:
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row))
                handle.write("\n")

    def end_run(self, run_id: str, payload: dict[str, Any]) -> None:
        file_path = _run_file_path(run_id)
        row = {
            "type": "run_completed",
            "payload": {
                "run_id": run_id,
                "completed_at": utc_now().isoformat(),
                **payload,
            },
        }
        with self._lock:
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row))
                handle.write("\n")

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        file_path = _run_file_path(run_id)
        if not file_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with file_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    rows.append(json.loads(text))
                except json.JSONDecodeError:
                    continue
        return rows

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        files = sorted(_storage_root().glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        output: list[dict[str, Any]] = []
        for file_path in files[: max(1, limit)]:
            rows = self.load_events(file_path.stem)
            if not rows:
                continue
            run_started = next((row for row in rows if row.get("type") == "run_started"), None)
            run_completed = next(
                (row for row in reversed(rows) if row.get("type") == "run_completed"),
                None,
            )
            events = [row for row in rows if row.get("type") == "event"]
            payload = {
                "run_id": file_path.stem,
                "events": len(events),
            }
            if run_started:
                payload.update(run_started.get("payload", {}))
            if run_completed:
                payload["completed_at"] = run_completed.get("payload", {}).get("completed_at")
            output.append(payload)
        return output


_store: ActivityStore | None = None


def get_activity_store() -> ActivityStore:
    global _store
    if _store is None:
        _store = ActivityStore()
    return _store
