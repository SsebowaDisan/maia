from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock
from typing import Any

from api.services.agent.activity import get_activity_store
from api.services.agent.event_envelope import build_event_envelope, merge_event_envelope_data
from api.services.agent.events import EVENT_SCHEMA_VERSION, infer_stage, infer_status
from api.services.agent.zoom_history import enrich_event_data_with_zoom


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_user(user_id: str) -> str:
    return f"user:{user_id}"


def _channel_run(user_id: str, run_id: str) -> str:
    return f"user:{user_id}:run:{run_id}"


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _string_list(value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(value, list):
        rows = [_clean_text(item) for item in value]
    elif value in (None, ""):
        rows = []
    else:
        rows = [_clean_text(value)]
    cleaned = [item for item in rows if item]
    return list(dict.fromkeys(cleaned))[: max(1, int(limit or 1))]


def _positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def _snapshot_by_event_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshot_map: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = _clean_text(row.get("event_id"))
        if not event_id:
            continue
        snapshot_map[event_id] = dict(row)
    return snapshot_map


def _hydrate_payload_from_snapshots(
    *,
    payload: dict[str, Any],
    graph_snapshot_map: dict[str, dict[str, Any]],
    evidence_snapshot_map: dict[str, dict[str, Any]],
    artifact_snapshot_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hydrated = dict(payload or {})
    data = hydrated.get("data")
    data_map = dict(data) if isinstance(data, dict) else {}
    event_id = _clean_text(hydrated.get("event_id"))

    graph_snapshot = graph_snapshot_map.get(event_id) if event_id else None
    if isinstance(graph_snapshot, dict):
        graph_node_ids = _string_list(data_map.get("graph_node_ids")) or _string_list(
            graph_snapshot.get("graph_node_ids")
        )
        scene_refs = _string_list(data_map.get("scene_refs")) or _string_list(graph_snapshot.get("scene_refs"))
        if graph_node_ids:
            data_map["graph_node_ids"] = graph_node_ids
            data_map.setdefault("graph_node_id", graph_node_ids[0])
        if scene_refs:
            data_map["scene_refs"] = scene_refs
            data_map.setdefault("scene_ref", scene_refs[0])
        graph_event_index = graph_snapshot.get("event_index")
        try:
            graph_event_index_value = int(graph_event_index)
        except Exception:
            graph_event_index_value = 0
        if graph_event_index_value > 0 and _positive_int(data_map.get("event_index")) <= 0:
            data_map["event_index"] = graph_event_index_value
            if _positive_int(hydrated.get("event_index")) <= 0:
                hydrated["event_index"] = graph_event_index_value

    evidence_snapshot = evidence_snapshot_map.get(event_id) if event_id else None
    if isinstance(evidence_snapshot, dict):
        evidence_refs = _string_list(data_map.get("evidence_refs")) or _string_list(
            evidence_snapshot.get("evidence_refs")
        )
        if evidence_refs:
            data_map["evidence_refs"] = evidence_refs
            data_map.setdefault("evidence_ids", evidence_refs)

    artifact_snapshot = artifact_snapshot_map.get(event_id) if event_id else None
    if isinstance(artifact_snapshot, dict):
        artifact_refs = _string_list(data_map.get("artifact_refs")) or _string_list(
            artifact_snapshot.get("artifact_refs")
        )
        if artifact_refs:
            data_map["artifact_refs"] = artifact_refs
            data_map.setdefault("artifact_ids", artifact_refs)

    hydrated["data"] = data_map
    return hydrated


def _normalize_live_event(event: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(event or {})
    event_type = _clean_text(normalized.get("event_type") or normalized.get("type")) or "system_update"
    raw_data = normalized.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    stage = _clean_text(normalized.get("stage") or data.get("stage")) or infer_stage(event_type)
    status = _clean_text(normalized.get("status") or data.get("status")) or infer_status(event_type)
    schema_version = (
        _clean_text(normalized.get("event_schema_version") or data.get("event_schema_version"))
        or EVENT_SCHEMA_VERSION
    )
    envelope = build_event_envelope(
        event_type=event_type,
        stage=stage,
        status=status,
        data=data,
    )
    data = merge_event_envelope_data(
        data=data,
        envelope=envelope,
        event_schema_version=schema_version,
    )
    event_index_raw = normalized.get("event_index")
    try:
        event_index = int(event_index_raw)
    except Exception:
        event_index = 0
    if event_index <= 0:
        try:
            event_index = int(normalized.get("seq") or data.get("event_index") or 0)
        except Exception:
            event_index = 0
    if event_index > 0:
        data["event_index"] = event_index
    replay_importance = _clean_text(
        normalized.get("replay_importance")
        or data.get("replay_importance")
        or data.get("event_replay_importance")
    )
    if not replay_importance:
        replay_importance = _clean_text(data.get("event_replay_importance")) or "normal"
    data["replay_importance"] = replay_importance
    timeline = data.get("timeline")
    if not isinstance(timeline, dict):
        timeline = {}
    timeline.setdefault("event_index", data.get("event_index") or None)
    timeline.setdefault("replay_importance", replay_importance)
    timeline.setdefault("graph_node_id", data.get("graph_node_id"))
    timeline.setdefault("scene_ref", data.get("scene_ref"))
    data["timeline"] = timeline
    data = enrich_event_data_with_zoom(
        data=data,
        event_type=event_type,
        event_id=_clean_text(normalized.get("event_id")),
        event_index=event_index,
        timestamp=_clean_text(normalized.get("timestamp")),
        graph_node_id=_clean_text(data.get("graph_node_id")),
        scene_ref=_clean_text(data.get("scene_ref")),
    )
    normalized["event_type"] = event_type
    normalized["type"] = _clean_text(normalized.get("type")) or event_type
    normalized["data"] = data
    normalized["stage"] = stage
    normalized["status"] = status
    normalized["event_schema_version"] = schema_version
    normalized["event_family"] = data.get("event_family")
    normalized["event_priority"] = data.get("event_priority")
    normalized["event_render_mode"] = data.get("event_render_mode")
    normalized["event_replay_importance"] = data.get("event_replay_importance")
    normalized["replay_importance"] = data.get("replay_importance")
    normalized["event_index"] = data.get("event_index")
    normalized["graph_node_id"] = data.get("graph_node_id")
    normalized["scene_ref"] = data.get("scene_ref")
    return normalized


@dataclass
class LiveEventSubscription:
    channel: str
    queue: Queue[dict[str, Any]]


class LiveEventBroker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._subscribers: dict[str, list[Queue[dict[str, Any]]]] = defaultdict(list)
        self._backlog: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=200))

    def publish(self, *, user_id: str, event: dict[str, Any], run_id: str | None = None) -> None:
        envelope = _normalize_live_event(event)
        envelope.setdefault("timestamp", _utc_now_iso())
        envelope.setdefault("user_id", user_id)
        if run_id:
            envelope.setdefault("run_id", run_id)

        channels = [_channel_user(user_id)]
        if run_id:
            channels.append(_channel_run(user_id, run_id))

        with self._lock:
            for channel in channels:
                self._backlog[channel].append(envelope)
                subscribers = self._subscribers.get(channel, [])
                for queue in list(subscribers):
                    try:
                        queue.put_nowait(envelope)
                    except Exception:
                        continue

    def subscribe(
        self,
        *,
        user_id: str,
        run_id: str | None = None,
        replay_limit: int = 30,
    ) -> LiveEventSubscription:
        channel = _channel_run(user_id, run_id) if run_id else _channel_user(user_id)
        queue: Queue[dict[str, Any]] = Queue(maxsize=300)
        with self._lock:
            self._subscribers[channel].append(queue)
            backlog = list(self._backlog.get(channel, deque()))
        persisted: list[dict[str, Any]] = []
        if run_id and replay_limit:
            try:
                store = get_activity_store()
                rows = store.load_events(run_id)
                graph_snapshots = store.load_graph_snapshots(run_id)
                evidence_snapshots = store.load_evidence_snapshots(run_id)
                artifact_snapshots = store.load_artifact_snapshots(run_id)
            except Exception:
                rows = []
                graph_snapshots = []
                evidence_snapshots = []
                artifact_snapshots = []
            graph_snapshot_map = _snapshot_by_event_id(graph_snapshots)
            evidence_snapshot_map = _snapshot_by_event_id(evidence_snapshots)
            artifact_snapshot_map = _snapshot_by_event_id(artifact_snapshots)
            for row in rows:
                if row.get("type") != "event":
                    continue
                payload = row.get("payload")
                if not isinstance(payload, dict):
                    continue
                replay_payload = _hydrate_payload_from_snapshots(
                    payload=payload,
                    graph_snapshot_map=graph_snapshot_map,
                    evidence_snapshot_map=evidence_snapshot_map,
                    artifact_snapshot_map=artifact_snapshot_map,
                )
                persisted.append(_normalize_live_event(replay_payload))
        replay_rows = [*persisted, *backlog]
        replay_limit_value = max(0, int(replay_limit))
        if replay_limit_value <= 0:
            replay_slice = []
        else:
            deduped: list[dict[str, Any]] = []
            seen: set[str] = set()
            for row in replay_rows:
                event_id = _clean_text(row.get("event_id"))
                if event_id and event_id in seen:
                    continue
                if event_id:
                    seen.add(event_id)
                deduped.append(row)
            replay_slice = deduped[-replay_limit_value:]
        for item in replay_slice:
            try:
                queue.put_nowait(item)
            except Exception:
                break
        return LiveEventSubscription(channel=channel, queue=queue)

    def unsubscribe(self, subscription: LiveEventSubscription) -> None:
        with self._lock:
            subscribers = self._subscribers.get(subscription.channel, [])
            self._subscribers[subscription.channel] = [
                queue for queue in subscribers if queue is not subscription.queue
            ]

    @staticmethod
    def receive(
        subscription: LiveEventSubscription,
        *,
        timeout_seconds: float = 15.0,
    ) -> dict[str, Any] | None:
        try:
            return subscription.queue.get(timeout=max(0.1, float(timeout_seconds)))
        except Empty:
            return None


_broker: LiveEventBroker | None = None


def get_live_event_broker() -> LiveEventBroker:
    global _broker
    if _broker is None:
        _broker = LiveEventBroker()
    return _broker
