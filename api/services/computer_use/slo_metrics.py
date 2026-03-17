"""Computer Use SLO metrics store.

Single responsibility:
- track recent Computer Use stream outcomes in-memory,
- compute SLO summary statistics for operational dashboards.
"""
from __future__ import annotations

import os
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

StreamStatus = Literal["completed", "max_iterations", "failed", "cancelled", "policy_blocked"]


def _read_positive_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return max(1, default)
    try:
        parsed = int(raw)
    except ValueError:
        return max(1, default)
    return max(1, parsed)


_MAX_RECENT_RUNS = _read_positive_int("MAIA_COMPUTER_USE_SLO_BUFFER_SIZE", 1000)


@dataclass(frozen=True)
class StreamRunMetric:
    user_id: str
    session_id: str
    status: StreamStatus
    started_at: float
    ended_at: float
    duration_ms: int
    event_count: int
    action_count: int


class ComputerUseSLOMetricsStore:
    def __init__(self, *, max_recent_runs: int = _MAX_RECENT_RUNS) -> None:
        self._max_recent_runs = max(1, int(max_recent_runs))
        self._rows: deque[StreamRunMetric] = deque(maxlen=self._max_recent_runs)
        self._lock = threading.Lock()

    def record_stream_result(
        self,
        *,
        user_id: str,
        session_id: str,
        status: StreamStatus,
        started_at: float,
        ended_at: float,
        event_count: int,
        action_count: int,
    ) -> None:
        started = float(started_at or time.time())
        ended = float(ended_at or time.time())
        if ended < started:
            ended = started
        duration_ms = int(max(0.0, (ended - started) * 1000.0))
        row = StreamRunMetric(
            user_id=str(user_id or "").strip(),
            session_id=str(session_id or "").strip(),
            status=status,
            started_at=started,
            ended_at=ended,
            duration_ms=duration_ms,
            event_count=max(0, int(event_count or 0)),
            action_count=max(0, int(action_count or 0)),
        )
        with self._lock:
            self._rows.append(row)

    def summary(self, *, user_id: str | None = None, window_seconds: int = 86400) -> dict[str, object]:
        normalized_user_id = str(user_id or "").strip()
        now = time.time()
        min_started_at = now - max(1, int(window_seconds))
        with self._lock:
            rows = list(self._rows)
        if normalized_user_id:
            rows = [row for row in rows if row.user_id == normalized_user_id]
        rows = [row for row in rows if row.started_at >= min_started_at]
        if not rows:
            return {
                "window_seconds": int(window_seconds),
                "run_count": 0,
                "success_rate": 0.0,
                "error_rate": 0.0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0,
                "avg_latency_ms": 0,
                "avg_event_count": 0.0,
                "avg_action_count": 0.0,
                "status_counts": {},
            }

        durations = [int(row.duration_ms) for row in rows]
        run_count = len(rows)
        success_statuses = {"completed"}
        failed_statuses = {"failed", "policy_blocked"}
        success_count = sum(1 for row in rows if row.status in success_statuses)
        failed_count = sum(1 for row in rows if row.status in failed_statuses)
        status_counts: dict[str, int] = {}
        for row in rows:
            status_counts[row.status] = int(status_counts.get(row.status, 0)) + 1

        return {
            "window_seconds": int(window_seconds),
            "run_count": run_count,
            "success_rate": round(success_count / run_count, 4),
            "error_rate": round(failed_count / run_count, 4),
            "p50_latency_ms": _percentile(durations, 50),
            "p95_latency_ms": _percentile(durations, 95),
            "p99_latency_ms": _percentile(durations, 99),
            "avg_latency_ms": int(round(statistics.fmean(durations))),
            "avg_event_count": round(statistics.fmean(row.event_count for row in rows), 2),
            "avg_action_count": round(statistics.fmean(row.action_count for row in rows), 2),
            "status_counts": status_counts,
        }


def _percentile(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(int(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    pct = max(0, min(100, int(percentile)))
    rank = (pct / 100.0) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    interpolated = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return int(round(interpolated))


_STORE: ComputerUseSLOMetricsStore | None = None
_STORE_LOCK = threading.Lock()


def get_computer_use_slo_store() -> ComputerUseSLOMetricsStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = ComputerUseSLOMetricsStore()
    return _STORE

