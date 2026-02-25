from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from queue import Empty, Queue
from threading import Lock
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channel_user(user_id: str) -> str:
    return f"user:{user_id}"


def _channel_run(user_id: str, run_id: str) -> str:
    return f"user:{user_id}:run:{run_id}"


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
        envelope = dict(event)
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
        replay_slice = backlog[-max(0, int(replay_limit)) :] if replay_limit else []
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

