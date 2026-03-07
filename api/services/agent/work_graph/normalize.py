from __future__ import annotations

from datetime import datetime
from typing import Any


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalized_token(value: Any) -> str:
    return clean_text(value).lower().replace(".", "_").replace("-", "_").replace(" ", "_")


def unique_strings(value: Any, *, limit: int = 48) -> list[str]:
    if isinstance(value, list):
        rows = [clean_text(item) for item in value]
    elif value in (None, ""):
        rows = []
    else:
        rows = [clean_text(value)]
    cleaned = [item for item in rows if item]
    if not cleaned:
        return []
    return list(dict.fromkeys(cleaned))[: max(1, int(limit or 1))]


def positive_int(value: Any) -> int:
    try:
        parsed = int(value)
    except Exception:
        return 0
    return parsed if parsed > 0 else 0


def bounded_float(
    value: Any,
    *,
    low: float = 0.0,
    high: float = 1.0,
) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:  # NaN check
        return None
    if parsed < low:
        return low
    if parsed > high:
        return high
    return parsed


def progress_percent(value: Any) -> float | None:
    parsed = bounded_float(value, low=0.0, high=100.0)
    if parsed is None:
        return None
    if parsed <= 1.0:
        return round(parsed * 100.0, 2)
    return round(parsed, 2)


def parse_iso_datetime(value: Any) -> datetime | None:
    raw = clean_text(value)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def duration_ms(*, started_at: str | None, ended_at: str | None) -> int | None:
    start_dt = parse_iso_datetime(started_at)
    end_dt = parse_iso_datetime(ended_at)
    if start_dt is None or end_dt is None:
        return None
    delta = (end_dt - start_dt).total_seconds() * 1000.0
    if delta < 0:
        return None
    return int(delta)


def normalize_status(value: Any) -> str:
    token = normalized_token(value)
    if token in {"completed", "success", "succeeded"}:
        return "completed"
    if token in {"failed", "error"}:
        return "failed"
    if token in {"blocked", "skipped"}:
        return "blocked"
    if token in {"in_progress", "running", "waiting"}:
        return "running"
    return "queued"


def status_precedence(value: str) -> int:
    token = normalized_token(value)
    if token == "failed":
        return 5
    if token == "blocked":
        return 4
    if token == "running":
        return 3
    if token == "completed":
        return 2
    return 1


def infer_node_type(
    *,
    event_type: str,
    event_family: str,
    data: dict[str, Any],
) -> str:
    explicit = normalized_token(data.get("node_type") or data.get("work_graph_node_type"))
    if explicit:
        return explicit

    normalized_event = normalized_token(event_type)
    normalized_family = normalized_token(event_family)
    if normalized_event in {"agent_handoff", "role_handoff", "agent_handoff"}:
        return "decision"
    if normalized_event in {"agent_waiting", "handoff_paused", "approval_required"}:
        return "approval"
    if normalized_family == "plan":
        return "plan_step"
    if normalized_family == "browser":
        return "browser_action"
    if normalized_family in {"pdf", "doc"}:
        return "document_review"
    if normalized_family == "sheet":
        return "spreadsheet_analysis"
    if normalized_family == "email":
        return "email_draft"
    if normalized_family == "verify":
        return "verification"
    if normalized_family == "approval":
        return "approval"
    if normalized_family == "memory":
        return "memory_lookup"
    if normalized_family == "api":
        return "api_operation"
    if normalized_family == "artifact":
        return "artifact"
    if normalized_family == "scene":
        return "browser_action"
    return "plan_step"
