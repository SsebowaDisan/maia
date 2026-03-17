"""Task queue abstraction — pluggable backends for distributed execution.

Config via env:
    MAIA_TASK_BACKEND — "memory" (default) or "redis"
    MAIA_REDIS_URL — Redis connection URL (default "redis://localhost:6379/0")
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TaskQueue(ABC):
    """Interface every task-queue backend must implement."""

    @abstractmethod
    def enqueue(
        self,
        task_type: str,
        payload: dict,
        *,
        priority: int = 0,
        delay_s: float = 0,
    ) -> str:
        """Submit a task and return its task_id."""

    @abstractmethod
    def dequeue(
        self,
        task_types: list[str],
        timeout_s: float = 5,
    ) -> tuple[str, str, dict] | None:
        """Block up to *timeout_s* and return (task_id, task_type, payload) or None."""

    @abstractmethod
    def ack(self, task_id: str) -> None:
        """Mark a task as successfully completed."""

    @abstractmethod
    def nack(self, task_id: str, error: str = "") -> None:
        """Mark a task as failed (eligible for retry)."""

    @abstractmethod
    def get_status(self, task_id: str) -> dict:
        """Return status dict for a task."""


# ---------------------------------------------------------------------------
# In-process implementation (dev / single-node)
# ---------------------------------------------------------------------------

class MemoryTaskQueue(TaskQueue):
    """Thread-safe in-process queue backed by :class:`queue.PriorityQueue`."""

    def __init__(self) -> None:
        self._pq: queue.PriorityQueue = queue.PriorityQueue()
        self._statuses: dict[str, dict] = {}
        self._delayed: list[tuple[float, str, str, dict, int]] = []
        self._lock = threading.Lock()

    # -- internal helpers ---------------------------------------------------

    def _flush_delayed(self) -> None:
        """Move delayed tasks whose time has come into the main queue."""
        now = time.time()
        still_waiting: list[tuple[float, str, str, dict, int]] = []
        for execute_at, tid, ttype, payload, prio in self._delayed:
            if now >= execute_at:
                self._pq.put((prio, execute_at, tid, ttype, payload))
            else:
                still_waiting.append((execute_at, tid, ttype, payload, prio))
        self._delayed = still_waiting

    # -- public API ---------------------------------------------------------

    def enqueue(self, task_type: str, payload: dict, *, priority: int = 0, delay_s: float = 0) -> str:
        task_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._statuses[task_id] = {
                "task_id": task_id,
                "task_type": task_type,
                "status": "queued",
                "created_at": now,
                "error": "",
            }
            if delay_s > 0:
                self._delayed.append((now + delay_s, task_id, task_type, payload, priority))
            else:
                self._pq.put((priority, now, task_id, task_type, payload))
        return task_id

    def dequeue(self, task_types: list[str], timeout_s: float = 5) -> tuple[str, str, dict] | None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self._lock:
                self._flush_delayed()
            try:
                prio, ts, tid, ttype, payload = self._pq.get(timeout=min(0.25, max(0, deadline - time.time())))
            except queue.Empty:
                continue
            if ttype not in task_types:
                # put it back — not for us
                self._pq.put((prio, ts, tid, ttype, payload))
                time.sleep(0.05)
                continue
            with self._lock:
                if tid in self._statuses:
                    self._statuses[tid]["status"] = "running"
            return tid, ttype, payload
        return None

    def ack(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._statuses:
                self._statuses[task_id]["status"] = "completed"
                self._statuses[task_id]["completed_at"] = time.time()

    def nack(self, task_id: str, error: str = "") -> None:
        with self._lock:
            if task_id in self._statuses:
                self._statuses[task_id]["status"] = "failed"
                self._statuses[task_id]["error"] = error

    def get_status(self, task_id: str) -> dict:
        with self._lock:
            return dict(self._statuses.get(task_id, {"task_id": task_id, "status": "unknown"}))


# ---------------------------------------------------------------------------
# Redis implementation (production / multi-node)
# ---------------------------------------------------------------------------

class RedisTaskQueue(TaskQueue):
    """Redis-backed queue using LPUSH/BRPOP, sorted sets for delays."""

    def __init__(self, redis_url: str | None = None) -> None:
        try:
            import redis as _redis
        except ImportError:
            raise RuntimeError(
                "The 'redis' package is required for RedisTaskQueue. "
                "Install it with: pip install redis"
            )
        url = redis_url or os.environ.get("MAIA_REDIS_URL", "redis://localhost:6379/0")
        self._r: Any = _redis.Redis.from_url(url, decode_responses=True)
        self._delayed_key = "maia:delayed_tasks"

    def _queue_key(self, task_type: str) -> str:
        return f"maia:queue:{task_type}"

    def _status_key(self, task_id: str) -> str:
        return f"maia:task:{task_id}"

    def _flush_delayed(self) -> None:
        now = time.time()
        ready = self._r.zrangebyscore(self._delayed_key, "-inf", now)
        for raw in ready:
            data = json.loads(raw)
            self._r.lpush(self._queue_key(data["task_type"]), raw)
            self._r.zrem(self._delayed_key, raw)

    def enqueue(self, task_type: str, payload: dict, *, priority: int = 0, delay_s: float = 0) -> str:
        task_id = uuid.uuid4().hex
        now = time.time()
        item = json.dumps({"task_id": task_id, "task_type": task_type, "payload": payload, "priority": priority})
        self._r.hset(self._status_key(task_id), mapping={
            "task_id": task_id, "task_type": task_type,
            "status": "queued", "created_at": str(now), "error": "",
        })
        if delay_s > 0:
            self._r.zadd(self._delayed_key, {item: now + delay_s})
        else:
            self._r.lpush(self._queue_key(task_type), item)
        return task_id

    def dequeue(self, task_types: list[str], timeout_s: float = 5) -> tuple[str, str, dict] | None:
        self._flush_delayed()
        keys = [self._queue_key(t) for t in task_types]
        result = self._r.brpop(keys, timeout=int(max(1, timeout_s)))
        if result is None:
            return None
        _key, raw = result
        data = json.loads(raw)
        tid = data["task_id"]
        self._r.hset(self._status_key(tid), "status", "running")
        return tid, data["task_type"], data["payload"]

    def ack(self, task_id: str) -> None:
        self._r.hset(self._status_key(task_id), mapping={
            "status": "completed", "completed_at": str(time.time()),
        })

    def nack(self, task_id: str, error: str = "") -> None:
        self._r.hset(self._status_key(task_id), mapping={
            "status": "failed", "error": error,
        })

    def get_status(self, task_id: str) -> dict:
        data = self._r.hgetall(self._status_key(task_id))
        if not data:
            return {"task_id": task_id, "status": "unknown"}
        return data


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_instance: TaskQueue | None = None
_instance_lock = threading.Lock()


def get_task_queue() -> TaskQueue:
    """Return the singleton TaskQueue, creating it on first call."""
    global _instance
    if _instance is not None:
        return _instance
    with _instance_lock:
        if _instance is not None:
            return _instance
        backend = os.environ.get("MAIA_TASK_BACKEND", "memory").lower()
        if backend == "redis":
            _instance = RedisTaskQueue()
        elif backend == "memory":
            _instance = MemoryTaskQueue()
        else:
            raise ValueError(f"Unknown MAIA_TASK_BACKEND: {backend!r} (expected 'memory' or 'redis')")
        return _instance
