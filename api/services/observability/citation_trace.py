from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from typing import Any


logger = logging.getLogger(__name__)

_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("citation_trace_id", default="")
_trace_events_var: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar(
    "citation_trace_events",
    default=None,
)
_trace_meta_var: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "citation_trace_meta",
    default=None,
)


class TraceHandle:
    def __init__(
        self,
        *,
        trace_id: str,
        trace_token: contextvars.Token,
        events_token: contextvars.Token,
        meta_token: contextvars.Token,
    ) -> None:
        self.trace_id = trace_id
        self._trace_token = trace_token
        self._events_token = events_token
        self._meta_token = meta_token


def begin_trace(
    *,
    kind: str,
    user_id: str = "",
    question: str = "",
    conversation_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> TraceHandle:
    trace_id = uuid.uuid4().hex
    events: list[dict[str, Any]] = []
    meta = {
        "trace_id": trace_id,
        "kind": str(kind or "").strip() or "unknown",
        "user_id": str(user_id or "").strip(),
        "question": " ".join(str(question or "").split()).strip(),
        "conversation_id": str(conversation_id or "").strip(),
    }
    if metadata:
        meta.update(dict(metadata))

    trace_token = _trace_id_var.set(trace_id)
    events_token = _trace_events_var.set(events)
    meta_token = _trace_meta_var.set(meta)
    record_trace_event("trace.started", meta)
    return TraceHandle(
        trace_id=trace_id,
        trace_token=trace_token,
        events_token=events_token,
        meta_token=meta_token,
    )


def get_trace_id() -> str:
    return str(_trace_id_var.get("") or "").strip()


def get_trace_meta() -> dict[str, Any]:
    meta = _trace_meta_var.get(None)
    return dict(meta or {})


def record_trace_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    events = _trace_events_var.get(None)
    if events is None:
        return
    events.append(
        {
            "type": str(event_type or "").strip() or "trace.event",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": dict(data or {}),
        }
    )


def snapshot_trace() -> dict[str, Any]:
    meta = get_trace_meta()
    events = list(_trace_events_var.get(None) or [])
    return {
        **meta,
        "events": events,
        "event_count": len(events),
    }


def summarize_trace(*, max_events: int = 12) -> dict[str, Any]:
    trace = snapshot_trace()
    events = list(trace.get("events") or [])
    event_types = [str(event.get("type") or "") for event in events]
    return {
        "trace_id": str(trace.get("trace_id") or ""),
        "kind": str(trace.get("kind") or ""),
        "event_count": len(events),
        "event_types": event_types[:max_events],
        "last_event_type": event_types[-1] if event_types else "",
    }


def emit_trace_log(*, level: int = logging.INFO) -> None:
    trace = snapshot_trace()
    if not trace.get("trace_id"):
        return
    logger.log(level, "citation_trace %s", json.dumps(trace, default=str))


def _safe_reset(var: contextvars.ContextVar[Any], token: contextvars.Token) -> None:
    """Best-effort contextvar reset.

    Streaming responses can finalize in a different execution context than the
    one where the trace started. In that case ContextVar.reset(token) raises,
    and we should not let observability teardown crash the request.
    """
    try:
        var.reset(token)
    except (ValueError, RuntimeError):
        logger.debug("Skipped citation trace context reset due to context mismatch.")


def end_trace(handle: TraceHandle, *, emit_log: bool = True, level: int = logging.INFO) -> None:
    try:
        record_trace_event("trace.completed", {"event_count": len(_trace_events_var.get(None) or [])})
        if emit_log:
            emit_trace_log(level=level)
    finally:
        _safe_reset(_trace_meta_var, handle._meta_token)
        _safe_reset(_trace_events_var, handle._events_token)
        _safe_reset(_trace_id_var, handle._trace_token)
