"""Tool Failure Pattern Database (Innovation #7).

Tracks every tool execution outcome in-memory with periodic flush to DB.
Provides failure rates, alternative suggestions, and reliability reports.

Tables
------
  maia_tool_outcome  -- one row per tool execution outcome
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from collections import Counter, defaultdict
from typing import Any, Optional

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM
# ---------------------------------------------------------------------------

class ToolOutcomeRecord(SQLModel, table=True):
    __tablename__ = "maia_tool_outcome"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tool_id: str = Field(index=True)
    params_hash: str = ""
    outcome_status: str = ""           # success | empty | failed | blocked | skipped
    error_type: str = ""
    context_tags_json: str = "[]"
    agent_id: str = Field(default="", index=True)
    tenant_id: str = Field(default="", index=True)
    created_at: float = Field(default_factory=time.time)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


# ---------------------------------------------------------------------------
# In-memory accumulator entry
# ---------------------------------------------------------------------------

class _AccumulatorEntry:
    __slots__ = ("tool_id", "params_hash", "outcome_status", "error_type",
                 "context_tags", "agent_id", "tenant_id", "timestamp")

    def __init__(
        self,
        tool_id: str,
        params_hash: str,
        outcome_status: str,
        error_type: str,
        context_tags: list[str],
        agent_id: str,
        tenant_id: str,
    ):
        self.tool_id = tool_id
        self.params_hash = params_hash
        self.outcome_status = outcome_status
        self.error_type = error_type
        self.context_tags = context_tags
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.timestamp = time.time()


# ---------------------------------------------------------------------------
# ToolPatternDB (singleton)
# ---------------------------------------------------------------------------

_FLUSH_THRESHOLD = 50   # flush after this many accumulated entries
_FLUSH_INTERVAL = 60.0  # or after this many seconds


class ToolPatternDB:
    """Singleton that tracks tool execution outcomes.

    Records are accumulated in-memory and periodically flushed to the DB
    for durability and cross-process querying.
    """

    _instance: Optional[ToolPatternDB] = None
    _lock = threading.Lock()

    def __new__(cls) -> ToolPatternDB:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False  # type: ignore[attr-defined]
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:  # type: ignore[has-type]
            return
        self._initialized = True
        self._buffer: list[_AccumulatorEntry] = []
        self._buffer_lock = threading.Lock()
        self._last_flush = time.time()
        # In-memory aggregates for fast lookups
        self._tool_success: Counter[str] = Counter()
        self._tool_total: Counter[str] = Counter()
        self._tool_errors: dict[str, Counter[str]] = defaultdict(Counter)
        self._tool_durations: dict[str, list[int]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        tool_id: str,
        params_hash: str,
        outcome_status: str,
        error_type: str = "",
        context_tags: list[str] | None = None,
        agent_id: str = "",
        tenant_id: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Record a single tool execution outcome."""
        entry = _AccumulatorEntry(
            tool_id=tool_id,
            params_hash=params_hash,
            outcome_status=outcome_status,
            error_type=error_type,
            context_tags=context_tags or [],
            agent_id=agent_id,
            tenant_id=tenant_id,
        )

        with self._buffer_lock:
            self._buffer.append(entry)
            # Update in-memory aggregates
            self._tool_total[tool_id] += 1
            if outcome_status == "success":
                self._tool_success[tool_id] += 1
            if error_type:
                self._tool_errors[tool_id][error_type] += 1
            if duration_ms > 0:
                durations = self._tool_durations[tool_id]
                durations.append(duration_ms)
                # Keep only last 200 durations per tool
                if len(durations) > 200:
                    self._tool_durations[tool_id] = durations[-200:]

            should_flush = (
                len(self._buffer) >= _FLUSH_THRESHOLD
                or (time.time() - self._last_flush) > _FLUSH_INTERVAL
            )

        if should_flush:
            self._flush()

    def get_failure_rate(
        self,
        tool_id: str,
        context_tags: list[str] | None = None,
    ) -> float:
        """Return failure rate (0.0-1.0) for a tool, optionally filtered by context."""
        if context_tags:
            # Query DB for tag-filtered stats
            return self._db_failure_rate(tool_id, context_tags)

        total = self._tool_total.get(tool_id, 0)
        if total == 0:
            return 0.0
        successes = self._tool_success.get(tool_id, 0)
        return 1.0 - (successes / total)

    def get_best_alternative(
        self,
        tool_id: str,
        context_tags: list[str] | None = None,
    ) -> str | None:
        """Return tool_id of a better alternative, or None.

        Looks at tools used in similar contexts (shared context_tags) that
        have a higher success rate.
        """
        _ensure_tables()
        tags = context_tags or []
        if not tags:
            return None

        with Session(engine) as session:
            # Find tools used with overlapping context tags
            all_records = session.exec(
                select(ToolOutcomeRecord)
                .where(ToolOutcomeRecord.tool_id != tool_id)
                .order_by(ToolOutcomeRecord.created_at.desc())  # type: ignore[arg-type]
                .limit(500)
            ).all()

        if not all_records:
            return None

        # Score alternatives by success rate with matching tags
        tag_set = set(tags)
        alt_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "total": 0})

        for rec in all_records:
            rec_tags = set(json.loads(rec.context_tags_json or "[]"))
            if not tag_set.intersection(rec_tags):
                continue
            alt_stats[rec.tool_id]["total"] += 1
            if rec.outcome_status == "success":
                alt_stats[rec.tool_id]["success"] += 1

        current_failure_rate = self.get_failure_rate(tool_id)
        best_tool: str | None = None
        best_rate = 1.0 - current_failure_rate  # current success rate

        for alt_tool, stats in alt_stats.items():
            if stats["total"] < 2:
                continue
            alt_success_rate = stats["success"] / stats["total"]
            if alt_success_rate > best_rate:
                best_rate = alt_success_rate
                best_tool = alt_tool

        return best_tool

    def get_tool_reliability_report(
        self,
        agent_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Return per-tool reliability stats for an agent.

        Returns dict of tool_id -> {success_rate, avg_duration, common_errors}.
        """
        _ensure_tables()
        with Session(engine) as session:
            records = session.exec(
                select(ToolOutcomeRecord)
                .where(ToolOutcomeRecord.agent_id == agent_id)
                .order_by(ToolOutcomeRecord.created_at.desc())  # type: ignore[arg-type]
                .limit(1000)
            ).all()

        report: dict[str, dict[str, Any]] = {}
        tool_groups: dict[str, list[ToolOutcomeRecord]] = defaultdict(list)
        for rec in records:
            tool_groups[rec.tool_id].append(rec)

        for tid, recs in tool_groups.items():
            total = len(recs)
            successes = sum(1 for r in recs if r.outcome_status == "success")
            errors: Counter[str] = Counter()
            for r in recs:
                if r.error_type:
                    errors[r.error_type] += 1

            # Use in-memory durations if available
            durations = self._tool_durations.get(tid, [])
            avg_dur = int(sum(durations) / len(durations)) if durations else 0

            report[tid] = {
                "success_rate": round(successes / max(total, 1), 3),
                "total_executions": total,
                "avg_duration_ms": avg_dur,
                "common_errors": dict(errors.most_common(5)),
            }

        return report

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        """Flush accumulated entries to the database."""
        with self._buffer_lock:
            entries = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.time()

        if not entries:
            return

        try:
            _ensure_tables()
            with Session(engine) as session:
                for entry in entries:
                    record = ToolOutcomeRecord(
                        tool_id=entry.tool_id,
                        params_hash=entry.params_hash,
                        outcome_status=entry.outcome_status,
                        error_type=entry.error_type,
                        context_tags_json=json.dumps(entry.context_tags),
                        agent_id=entry.agent_id,
                        tenant_id=entry.tenant_id,
                        created_at=entry.timestamp,
                    )
                    session.add(record)
                session.commit()
        except Exception as exc:
            logger.error("ToolPatternDB flush failed: %s", exc)

    def _db_failure_rate(
        self,
        tool_id: str,
        context_tags: list[str],
    ) -> float:
        """Query DB for failure rate filtered by context tags."""
        _ensure_tables()
        with Session(engine) as session:
            records = session.exec(
                select(ToolOutcomeRecord)
                .where(ToolOutcomeRecord.tool_id == tool_id)
                .order_by(ToolOutcomeRecord.created_at.desc())  # type: ignore[arg-type]
                .limit(500)
            ).all()

        if not records:
            return 0.0

        tag_set = set(context_tags)
        matched = [
            r for r in records
            if tag_set.intersection(set(json.loads(r.context_tags_json or "[]")))
        ]

        if not matched:
            return 0.0

        successes = sum(1 for r in matched if r.outcome_status == "success")
        return 1.0 - (successes / len(matched))


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def get_tool_pattern_db() -> ToolPatternDB:
    """Return the singleton ToolPatternDB instance."""
    return ToolPatternDB()


def hash_params(params: dict[str, Any] | None) -> str:
    """Produce a short stable hash of tool parameters for deduplication."""
    raw = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
