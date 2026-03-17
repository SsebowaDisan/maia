from __future__ import annotations

import time

from api.services.computer_use.slo_metrics import ComputerUseSLOMetricsStore


def test_slo_summary_computes_percentiles_and_rates() -> None:
    store = ComputerUseSLOMetricsStore(max_recent_runs=10)
    now = time.time()

    store.record_stream_result(
        user_id="u1",
        session_id="s1",
        status="completed",
        started_at=now - 3.1,
        ended_at=now - 3.0,
        event_count=4,
        action_count=1,
    )
    store.record_stream_result(
        user_id="u1",
        session_id="s2",
        status="failed",
        started_at=now - 2.3,
        ended_at=now - 2.0,
        event_count=2,
        action_count=0,
    )
    store.record_stream_result(
        user_id="u1",
        session_id="s3",
        status="max_iterations",
        started_at=now - 1.5,
        ended_at=now - 1.0,
        event_count=6,
        action_count=2,
    )

    summary = store.summary(user_id="u1", window_seconds=600)

    assert summary["run_count"] == 3
    assert summary["success_rate"] == 0.3333
    assert summary["error_rate"] == 0.3333
    assert abs(int(summary["p50_latency_ms"]) - 300) <= 1
    assert summary["p95_latency_ms"] == 480
    assert summary["p99_latency_ms"] == 496
    assert abs(int(summary["avg_latency_ms"]) - 300) <= 1
    assert summary["avg_event_count"] == 4.0
    assert summary["avg_action_count"] == 1.0
    assert summary["status_counts"] == {
        "completed": 1,
        "failed": 1,
        "max_iterations": 1,
    }


def test_slo_summary_filters_by_user_and_window() -> None:
    store = ComputerUseSLOMetricsStore(max_recent_runs=10)
    now = time.time()

    store.record_stream_result(
        user_id="u1",
        session_id="old",
        status="completed",
        started_at=now - 1000,
        ended_at=now - 999.8,
        event_count=1,
        action_count=0,
    )
    store.record_stream_result(
        user_id="u2",
        session_id="other-user",
        status="failed",
        started_at=now - 10,
        ended_at=now - 9.5,
        event_count=3,
        action_count=1,
    )
    store.record_stream_result(
        user_id="u1",
        session_id="recent",
        status="completed",
        started_at=now - 8,
        ended_at=now - 7.7,
        event_count=2,
        action_count=1,
    )

    summary_u1_short = store.summary(user_id="u1", window_seconds=60)

    assert summary_u1_short["run_count"] == 1
    assert summary_u1_short["status_counts"] == {"completed": 1}

    summary_all = store.summary(window_seconds=60)
    assert summary_all["run_count"] == 2
    assert summary_all["status_counts"] == {"failed": 1, "completed": 1}
