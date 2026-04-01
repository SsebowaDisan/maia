"""RAG Pipeline Phase 16: Observability — stage event bus for tracing.

Every pipeline phase emits stage events at start and completion. Handlers
can be registered to receive events for logging, Theatre streaming, metrics,
or any other consumer.

Usage:
    from api.services.rag.observability import emit_stage, on_stage_event

    # Register a handler
    on_stage_event(lambda e: print(f"{e.stage} {e.status}"))

    # Emit from any phase
    emit_stage("trace-123", "retrieve", "src-1", "started")
    emit_stage("trace-123", "retrieve", "src-1", "completed", duration_ms=42.5)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from api.services.rag.types import StageEvent

logger = logging.getLogger(__name__)

# ── Module-level event bus ──────────────────────────────────────────────────

_event_handlers: list[Callable[[StageEvent], None]] = []


def on_stage_event(handler: Callable[[StageEvent], None]) -> None:
    """Register a handler that will be called for every stage event.

    Handlers are called synchronously in registration order. A handler that
    raises is logged but does not block other handlers or the pipeline.
    """
    _event_handlers.append(handler)
    logger.debug("Registered stage event handler: %s (total: %d)", handler, len(_event_handlers))


def remove_handler(handler: Callable[[StageEvent], None]) -> bool:
    """Remove a previously registered handler. Returns True if found."""
    try:
        _event_handlers.remove(handler)
        return True
    except ValueError:
        return False


def clear_handlers() -> None:
    """Remove all handlers. Useful for tests."""
    _event_handlers.clear()


def emit_stage(
    trace_id: str,
    stage: str,
    source_id: str,
    status: str,
    detail: str = "",
    duration_ms: float = 0.0,
    metadata: dict[str, Any] | None = None,
) -> StageEvent:
    """Create and dispatch a StageEvent to all registered handlers.

    Parameters
    ----------
    trace_id : correlation ID for the entire pipeline run
    stage : phase name ("retrieve", "rerank", "answer", etc.)
    source_id : the source being processed (or "" for query-level events)
    status : "started" | "completed" | "failed"
    detail : optional human-readable detail message
    duration_ms : milliseconds elapsed (usually set on "completed" events)
    metadata : optional extra data (counts, scores, etc.)

    Returns
    -------
    The created StageEvent, so callers can inspect or forward it.
    """
    event = StageEvent(
        trace_id=trace_id,
        stage=stage,
        source_id=source_id,
        status=status,
        detail=detail,
        duration_ms=duration_ms,
        metadata=metadata or {},
    )

    for handler in _event_handlers:
        try:
            handler(event)
        except Exception:
            logger.exception("Stage event handler %s raised for event %s/%s", handler, stage, status)

    if status == "failed":
        logger.warning("Stage %s failed for source %s: %s", stage, source_id, detail)
    else:
        logger.debug("Stage %s %s for source %s (%.1fms)", stage, status, source_id, duration_ms)

    return event


class StageTimer:
    """Context manager that emits started/completed events with timing.

    Usage:
        with StageTimer("trace-1", "rerank", "src-1") as timer:
            # ... do rerank work ...
            timer.metadata["reranked_count"] = 5
    """

    def __init__(self, trace_id: str, stage: str, source_id: str = ""):
        self.trace_id = trace_id
        self.stage = stage
        self.source_id = source_id
        self.metadata: dict[str, Any] = {}
        self._start: float = 0.0

    def __enter__(self) -> StageTimer:
        self._start = time.perf_counter()
        emit_stage(self.trace_id, self.stage, self.source_id, "started")
        return self

    def __exit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        duration_ms = (time.perf_counter() - self._start) * 1000
        if exc_type is not None:
            emit_stage(
                self.trace_id, self.stage, self.source_id, "failed",
                detail=str(exc_val), duration_ms=duration_ms, metadata=self.metadata,
            )
        else:
            emit_stage(
                self.trace_id, self.stage, self.source_id, "completed",
                duration_ms=duration_ms, metadata=self.metadata,
            )
