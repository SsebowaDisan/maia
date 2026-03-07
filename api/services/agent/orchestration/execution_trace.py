from __future__ import annotations

from typing import Any

from api.services.agent.models import utc_now

from .models import ExecutionState


def _append_bounded_trace(
    *,
    settings: dict[str, Any],
    key: str,
    entry: dict[str, Any],
    limit: int = 120,
) -> list[dict[str, Any]]:
    history_raw = settings.get(key)
    history = list(history_raw) if isinstance(history_raw, list) else []
    history.append(dict(entry))
    bounded = history[-max(20, int(limit)) :]
    settings[key] = bounded
    return bounded


def record_retry_trace(
    *,
    state: ExecutionState,
    step_index: int,
    tool_id: str,
    reason: str,
    status: str,
) -> dict[str, Any]:
    entry = {
        "timestamp": utc_now().isoformat(),
        "step": max(1, int(step_index)),
        "tool_id": str(tool_id or "").strip(),
        "reason": " ".join(str(reason or "").split()).strip()[:240],
        "status": " ".join(str(status or "").split()).strip().lower() or "unknown",
    }
    state.retry_trace.append(entry)
    state.retry_trace = state.retry_trace[-120:]
    _append_bounded_trace(
        settings=state.execution_context.settings,
        key="__retry_trace",
        entry=entry,
        limit=120,
    )
    return entry


def record_remediation_trace(
    *,
    state: ExecutionState,
    step_index: int,
    blocked_tool_id: str,
    inserted_steps: list[str],
    reason: str,
) -> dict[str, Any]:
    entry = {
        "timestamp": utc_now().isoformat(),
        "step": max(1, int(step_index)),
        "blocked_tool_id": str(blocked_tool_id or "").strip(),
        "inserted_tool_ids": [str(item).strip() for item in inserted_steps if str(item).strip()][:12],
        "reason": " ".join(str(reason or "").split()).strip()[:240],
        "attempt": max(0, int(state.remediation_attempts)),
    }
    state.remediation_trace.append(entry)
    state.remediation_trace = state.remediation_trace[-120:]
    _append_bounded_trace(
        settings=state.execution_context.settings,
        key="__remediation_trace",
        entry=entry,
        limit=120,
    )
    return entry


def record_parallel_research_trace(
    *,
    state: ExecutionState,
    step_index: int,
    tool_id: str,
    batch_type: str,
    inserted_steps: list[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "timestamp": utc_now().isoformat(),
        "step": max(1, int(step_index)),
        "tool_id": str(tool_id or "").strip(),
        "batch_type": " ".join(str(batch_type or "").split()).strip().lower()[:80] or "adaptive",
        "inserted_tool_ids": [str(item).strip() for item in inserted_steps if str(item).strip()][:20],
    }
    if isinstance(metadata, dict) and metadata:
        entry["metadata"] = dict(metadata)
    state.parallel_research_trace.append(entry)
    state.parallel_research_trace = state.parallel_research_trace[-120:]
    _append_bounded_trace(
        settings=state.execution_context.settings,
        key="__parallel_research_trace",
        entry=entry,
        limit=120,
    )
    return entry
