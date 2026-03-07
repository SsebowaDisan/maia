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


def _string_list(value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(value, list):
        rows = [" ".join(str(item or "").split()).strip() for item in value]
    elif value in (None, ""):
        rows = []
    else:
        rows = [" ".join(str(value or "").split()).strip()]
    cleaned = [item for item in rows if item]
    return list(dict.fromkeys(cleaned))[: max(1, int(limit or 1))]


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


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
        payload = dict(event.data or {})
        graph_node_ids = _string_list(payload.get("graph_node_ids"))
        if not graph_node_ids:
            graph_node_ids = _string_list(payload.get("graph_node_id"))
        scene_refs = _string_list(payload.get("scene_refs"))
        if not scene_refs:
            scene_refs = _string_list(payload.get("scene_ref"))
        evidence_refs = _string_list(payload.get("evidence_refs"))
        if not evidence_refs:
            evidence_refs = _string_list(payload.get("evidence_ids"))
        artifact_refs = _string_list(payload.get("artifact_refs"))
        if not artifact_refs:
            artifact_refs = _string_list(payload.get("artifact_ids"))
        if not evidence_refs:
            evidence_items = payload.get("evidence_items")
            if isinstance(evidence_items, list):
                extracted: list[str] = []
                for item in evidence_items[:24]:
                    if isinstance(item, dict):
                        candidate = _clean_text(item.get("id") or item.get("evidence_id"))
                        if candidate:
                            extracted.append(candidate)
                evidence_refs = _string_list(extracted)
        if not artifact_refs:
            artifacts = payload.get("artifacts")
            if isinstance(artifacts, list):
                extracted_artifacts: list[str] = []
                for item in artifacts[:24]:
                    if isinstance(item, dict):
                        candidate = _clean_text(item.get("id") or item.get("artifact_id"))
                        if candidate:
                            extracted_artifacts.append(candidate)
                    else:
                        candidate = _clean_text(item)
                        if candidate:
                            extracted_artifacts.append(candidate)
                artifact_refs = _string_list(extracted_artifacts)
        try:
            event_index = int(payload.get("event_index") or event.seq or 0)
        except Exception:
            event_index = 0
        graph_snapshot = None
        if graph_node_ids or scene_refs:
            graph_snapshot = {
                "type": "graph_snapshot",
                "payload": {
                    "run_id": event.run_id,
                    "event_id": event.event_id,
                    "event_index": event_index if event_index > 0 else None,
                    "graph_node_ids": graph_node_ids,
                    "scene_refs": scene_refs,
                    "timestamp": event.timestamp,
                },
            }
        evidence_snapshot = None
        if evidence_refs:
            evidence_snapshot = {
                "type": "evidence_snapshot",
                "payload": {
                    "run_id": event.run_id,
                    "event_id": event.event_id,
                    "event_index": event_index if event_index > 0 else None,
                    "evidence_refs": evidence_refs,
                    "timestamp": event.timestamp,
                },
            }
        artifact_snapshot = None
        if artifact_refs:
            artifact_snapshot = {
                "type": "artifact_snapshot",
                "payload": {
                    "run_id": event.run_id,
                    "event_id": event.event_id,
                    "event_index": event_index if event_index > 0 else None,
                    "artifact_refs": artifact_refs,
                    "timestamp": event.timestamp,
                },
            }
        with self._lock:
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row))
                handle.write("\n")
                if graph_snapshot:
                    handle.write(json.dumps(graph_snapshot))
                    handle.write("\n")
                if evidence_snapshot:
                    handle.write(json.dumps(evidence_snapshot))
                    handle.write("\n")
                if artifact_snapshot:
                    handle.write(json.dumps(artifact_snapshot))
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

    def load_graph_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.load_events(run_id)
        return self._load_snapshots(rows=rows, snapshot_type="graph_snapshot")

    def load_evidence_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.load_events(run_id)
        return self._load_snapshots(rows=rows, snapshot_type="evidence_snapshot")

    def load_artifact_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.load_events(run_id)
        return self._load_snapshots(rows=rows, snapshot_type="artifact_snapshot")

    def append_work_graph_snapshot(
        self,
        *,
        run_id: str,
        event_index: int,
        graph_payload: dict[str, Any],
        schema_version: str = "work_graph.v2",
    ) -> dict[str, Any]:
        file_path = _run_file_path(run_id)
        event_index_value = _positive_int(event_index)
        row_payload = {
            "snapshot_id": new_id("graph_snapshot"),
            "run_id": run_id,
            "event_index": event_index_value,
            "schema_version": _clean_text(schema_version) or "work_graph.v2",
            "storage_backend": "jsonl",
            "created_at": utc_now().isoformat(),
            "graph": dict(graph_payload or {}),
        }
        row = {
            "type": "work_graph_snapshot",
            "payload": row_payload,
        }
        with self._lock:
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row))
                handle.write("\n")
        return dict(row_payload)

    def load_work_graph_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.load_events(run_id)
        snapshots: list[dict[str, Any]] = []
        fallback_index = 0
        for row in rows:
            if row.get("type") != "work_graph_snapshot":
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            snapshot = dict(payload)
            event_index = _positive_int(snapshot.get("event_index"))
            if event_index <= 0:
                fallback_index += 1
                event_index = fallback_index
            else:
                fallback_index = max(fallback_index, event_index)
            snapshot["event_index"] = event_index
            snapshots.append(snapshot)
        snapshots.sort(
            key=lambda item: (
                _positive_int(item.get("event_index")),
                _clean_text(item.get("created_at")),
                _clean_text(item.get("snapshot_id")),
            )
        )
        return snapshots

    def load_replay_state(self, run_id: str) -> dict[str, Any]:
        rows = self.load_events(run_id)
        event_index_by_event_id = self._event_index_lookup(rows)
        graph_snapshots = self._load_snapshots(rows=rows, snapshot_type="graph_snapshot")
        evidence_snapshots = self._load_snapshots(rows=rows, snapshot_type="evidence_snapshot")
        artifact_snapshots = self._load_snapshots(rows=rows, snapshot_type="artifact_snapshot")
        work_graph_snapshots = self.load_work_graph_snapshots(run_id)
        latest_event_index = max(event_index_by_event_id.values()) if event_index_by_event_id else 0
        return {
            "run_id": run_id,
            "latest_event_index": latest_event_index,
            "graph_snapshots": graph_snapshots,
            "evidence_snapshots": evidence_snapshots,
            "artifact_snapshots": artifact_snapshots,
            "work_graph_snapshots": work_graph_snapshots,
        }

    @staticmethod
    def _event_index_lookup(rows: list[dict[str, Any]]) -> dict[str, int]:
        event_index_by_event_id: dict[str, int] = {}
        fallback_event_index = 0
        for row in rows:
            if row.get("type") != "event":
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            event_id = _clean_text(payload.get("event_id"))
            data = payload.get("data")
            data_map = data if isinstance(data, dict) else {}
            event_index = _positive_int(data_map.get("event_index"))
            if event_index <= 0:
                event_index = _positive_int(payload.get("seq"))
            if event_index <= 0:
                fallback_event_index += 1
                event_index = fallback_event_index
            else:
                fallback_event_index = max(fallback_event_index, event_index)
            if event_id:
                event_index_by_event_id[event_id] = event_index
        return event_index_by_event_id

    def _load_snapshots(
        self,
        *,
        rows: list[dict[str, Any]],
        snapshot_type: str,
    ) -> list[dict[str, Any]]:
        event_index_by_event_id = self._event_index_lookup(rows)
        snapshots: list[dict[str, Any]] = []
        fallback_snapshot_index = 0
        for row in rows:
            if row.get("type") != snapshot_type:
                continue
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            snapshot = dict(payload)
            event_id = _clean_text(snapshot.get("event_id"))
            event_index = _positive_int(snapshot.get("event_index"))
            if event_index <= 0 and event_id:
                event_index = _positive_int(event_index_by_event_id.get(event_id))
            if event_index <= 0:
                fallback_snapshot_index += 1
                event_index = fallback_snapshot_index
            else:
                fallback_snapshot_index = max(fallback_snapshot_index, event_index)
            snapshot["event_index"] = event_index
            snapshots.append(snapshot)
        snapshots.sort(
            key=lambda item: (
                _positive_int(item.get("event_index")),
                _clean_text(item.get("timestamp")),
                _clean_text(item.get("event_id")),
            )
        )
        return snapshots


_store: ActivityStore | None = None


def get_activity_store() -> ActivityStore:
    global _store
    if _store is None:
        _store = ActivityStore()
    return _store
