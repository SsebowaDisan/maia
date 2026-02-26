from __future__ import annotations

from typing import Any, Generator

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent


def truthy_with_default(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def desktop_mode_enabled(context: ToolExecutionContext, params: dict[str, Any]) -> bool:
    if "live_desktop" in params:
        return truthy_with_default(params.get("live_desktop"), default=False)
    return truthy_with_default(
        params.get("agent.gmail.desktop_live") or context.settings.get("agent.gmail.desktop_live"),
        default=True,
    )


def desktop_mode_required(context: ToolExecutionContext, params: dict[str, Any]) -> bool:
    if "desktop_required" in params:
        return truthy_with_default(params.get("desktop_required"), default=False)
    return truthy_with_default(
        params.get("agent.gmail.desktop_required") or context.settings.get("agent.gmail.desktop_required"),
        default=False,
    )


def trace_from_payload(payload: dict[str, Any]) -> ToolTraceEvent:
    return ToolTraceEvent(
        event_type=str(payload.get("event_type") or "tool_progress"),
        title=str(payload.get("title") or "Gmail desktop activity"),
        detail=str(payload.get("detail") or ""),
        data=dict(payload.get("data") or {}),
        snapshot_ref=str(payload.get("snapshot_ref") or "").strip() or None,
    )


def stream_live_desktop_compose(
    *,
    context: ToolExecutionContext,
    trace_events: list[ToolTraceEvent],
    to: str,
    subject: str,
    body: str,
    send: bool,
) -> Generator[ToolTraceEvent, None, dict[str, Any]]:
    connector = get_connector_registry().build("gmail_playwright", settings=context.settings)
    stream = connector.compose_live_stream(
        to=to,
        subject=subject,
        body=body,
        send=send,
    )
    while True:
        try:
            payload = next(stream)
        except StopIteration as stop:
            result = stop.value if isinstance(stop.value, dict) else {}
            return result
        trace = trace_from_payload(dict(payload or {}))
        trace_events.append(trace)
        yield trace
