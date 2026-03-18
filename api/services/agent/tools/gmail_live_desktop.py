from __future__ import annotations

from typing import Any, Generator

from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent


def desktop_mode_enabled(context: ToolExecutionContext, params: dict[str, Any]) -> bool:
    # Gmail desktop mode is retired. Gmail tools execute via Gmail API only.
    del context, params
    return False


def desktop_mode_required(context: ToolExecutionContext, params: dict[str, Any]) -> bool:
    del context, params
    return False


def stream_live_desktop_compose(
    *,
    context: ToolExecutionContext,
    trace_events: list[ToolTraceEvent],
    to: str,
    subject: str,
    body: str,
    send: bool,
) -> Generator[ToolTraceEvent, None, dict[str, Any]]:
    del context, trace_events, to, subject, body, send
    raise RuntimeError(
        "Gmail live desktop execution is retired. Use gmail.send/gmail.draft (Gmail API) "
        "or computer_use_browser for browser automation."
    )
