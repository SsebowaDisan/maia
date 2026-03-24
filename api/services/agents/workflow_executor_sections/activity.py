from __future__ import annotations

import time
from typing import Any, Callable, Optional

from api.services.agent.events import infer_stage, infer_status
from api.services.agent.models import AgentActivityEvent, new_id
from api.schemas.workflow_definition import WorkflowStep

from .common import (
    _display_label_for_url,
    _emit,
    _has_terminal_citation_section,
    _INLINE_CITATION_RE,
    _is_search_like_url,
    _normalize_http_url,
)


def _collect_step_activity_source_urls(*, run_id: str, step_agent_id: str, limit: int = 16) -> list[str]:
    try:
        from api.services.agent.activity import get_activity_store
    except Exception:
        return []

    store = get_activity_store()
    if not hasattr(store, "load_events"):
        return []
    rows = store.load_events(run_id)
    discovered: list[str] = []
    seen: set[str] = set()
    candidate_keys = ("target_url", "final_url", "page_url", "url", "source_url")
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        candidate_step_agent_id = str(
            payload.get("step_agent_id") or data.get("step_agent_id") or metadata.get("step_agent_id") or ""
        ).strip()
        if step_agent_id and candidate_step_agent_id != step_agent_id:
            continue
        event_type = str(payload.get("event_type") or payload.get("type") or "").strip().lower()
        if event_type.startswith("team_chat") or event_type.startswith("brain_"):
            continue
        candidates: list[str] = []
        for source in (data, metadata, payload):
            for key in candidate_keys:
                value = source.get(key)
                normalized = _normalize_http_url(value)
                if normalized:
                    candidates.append(normalized)
        for candidate in candidates:
            if _is_search_like_url(candidate) or candidate in seen:
                continue
            seen.add(candidate)
            discovered.append(candidate)
            if len(discovered) >= max(1, int(limit or 1)):
                return discovered
    return discovered


def _append_activity_citation_section(text: str, *, run_id: str, step_agent_id: str) -> str:
    body = str(text or "").strip()
    if not body or _has_terminal_citation_section(body):
        return body
    inline_refs = [int(match.group(1)) for match in _INLINE_CITATION_RE.finditer(body)]
    if not inline_refs:
        return body
    citation_urls = _collect_step_activity_source_urls(
        run_id=run_id,
        step_agent_id=step_agent_id,
        limit=max(4, max(inline_refs)),
    )
    if not citation_urls:
        return body
    rows = [
        f"- [{idx}] [{_display_label_for_url(url)}]({url})"
        for idx, url in enumerate(citation_urls[: max(inline_refs)], start=1)
    ]
    return f"{body}\n\n## Evidence Citations\n" + "\n".join(rows) if rows else body


def _normalize_child_activity_event(
    event: dict[str, Any],
    *,
    parent_run_id: str,
    step_agent_id: str = "",
) -> dict[str, Any]:
    payload = dict(event or {})
    original_run_id = str(payload.get("run_id") or "").strip()
    original_event_id = str(payload.get("event_id") or "").strip()
    if original_run_id and original_run_id != parent_run_id:
        payload.setdefault("source_run_id", original_run_id)
    if original_event_id:
        payload.setdefault("source_event_id", original_event_id)
    payload["run_id"] = parent_run_id
    payload["event_id"] = new_id("evt")
    if step_agent_id:
        payload["step_agent_id"] = step_agent_id

    for key in ("data", "metadata"):
        raw_map = payload.get(key)
        if not isinstance(raw_map, dict):
            continue
        next_map = dict(raw_map)
        nested_run_id = str(next_map.get("run_id") or "").strip()
        if nested_run_id and nested_run_id != parent_run_id:
            next_map.setdefault("source_run_id", nested_run_id)
        elif original_run_id and original_run_id != parent_run_id:
            next_map.setdefault("source_run_id", original_run_id)
        if step_agent_id:
            next_map.setdefault("step_agent_id", step_agent_id)
        next_map["run_id"] = parent_run_id
        payload[key] = next_map
    return payload


def _persist_parent_activity_event(event: dict[str, Any], *, parent_run_id: str) -> None:
    event_type = str(event.get("event_type") or "").strip()
    if not event_type:
        return
    raw_data = event.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    raw_metadata = event.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else dict(data)
    merged = dict(metadata)
    merged.update(data)
    record = AgentActivityEvent(
        event_id=str(event.get("event_id") or new_id("evt")).strip() or new_id("evt"),
        run_id=parent_run_id,
        event_type=event_type,
        title=str(event.get("title") or event_type.replace("_", " ").title()),
        detail=str(event.get("detail") or ""),
        timestamp=str(event.get("timestamp") or event.get("ts") or ""),
        metadata=merged,
        data=merged,
        seq=int(event.get("seq") or 0) if str(event.get("seq") or "").strip() else 0,
        stage=str(event.get("stage") or infer_stage(event_type)),
        status=str(event.get("status") or infer_status(event_type)),
        snapshot_ref=str(event.get("snapshot_ref") or "") or None,
    )
    from api.services.agent.activity import get_activity_store

    get_activity_store().append(record)


def _emit_parent_step_event(
    *,
    on_event: Optional[Callable],
    run_id: str,
    step: WorkflowStep,
    agent_id: str,
    event_type: str,
    title: str,
    detail: str,
    data: dict[str, Any] | None = None,
) -> None:
    event = {
        "event_id": new_id("evt"),
        "run_id": run_id,
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_id": agent_id,
        "step_agent_id": agent_id,
        "data": {
            "run_id": run_id,
            "step_id": step.step_id,
            "agent_id": agent_id,
            "step_agent_id": agent_id,
            **(data or {}),
        },
    }
    _persist_parent_activity_event(event, parent_run_id=run_id)
    _emit(on_event, event)
