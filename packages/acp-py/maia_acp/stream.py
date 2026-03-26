"""ACP stream utilities — parse raw SSE into typed ACP events."""

from __future__ import annotations

import json
import logging
from typing import Any, Generator

import httpx

from maia_acp.types import ACPEvent

logger = logging.getLogger(__name__)


def parse_sse_line(line: str) -> ACPEvent | None:
    """Parse a single SSE line into an ACPEvent.

    Returns None for non-data lines, keep-alive, or [DONE].
    Gracefully wraps non-ACP JSON payloads as activity events.
    """
    trimmed = line.strip()
    if not trimmed or not trimmed.startswith("data: "):
        return None

    data_str = trimmed[6:]
    if data_str == "[DONE]":
        return None

    try:
        parsed = json.loads(data_str)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    # Native ACP event
    if parsed.get("acp_version"):
        return ACPEvent.model_validate(parsed)

    # Non-ACP event — wrap intelligently
    return _wrap_non_acp(parsed)


def _wrap_non_acp(data: dict[str, Any]) -> ACPEvent:
    """Wrap a non-ACP JSON payload into an ACP envelope.

    This enables Theatre to render events from ANY existing SSE stream,
    even if the backend doesn't know about ACP.
    """
    agent_id = (
        data.get("agent_id")
        or data.get("agent")
        or data.get("sender")
        or data.get("name")
        or "unknown"
    )
    agent_uri = agent_id if agent_id.startswith("agent://") else f"agent://{agent_id}"

    content = (
        data.get("content")
        or data.get("message")
        or data.get("text")
        or data.get("output")
        or json.dumps(data, default=str)
    )

    event_type = "event"
    if data.get("content") or data.get("message") or data.get("text"):
        event_type = "message"

    if event_type == "message":
        payload = {
            "from": agent_uri,
            "to": "agent://user",
            "intent": "propose",
            "content": str(content),
        }
    else:
        payload = {
            "agent_id": agent_uri,
            "activity": "tool_calling",
            "detail": str(content),
        }

    return ACPEvent(
        run_id=str(data.get("run_id", data.get("thread_id", "unknown"))),
        agent_id=agent_uri,
        event_type=event_type,  # type: ignore[arg-type]
        payload=payload,
    )


def stream_events(lines: Generator[str, None, None]) -> Generator[ACPEvent, None, None]:
    """Convert a line generator into an ACPEvent generator."""
    for line in lines:
        event = parse_sse_line(line)
        if event is not None:
            yield event


def connect_sse(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
) -> Generator[ACPEvent, None, None]:
    """Connect to an SSE endpoint and yield ACP events.

    Works with both ACP-native and non-ACP SSE streams.

    Usage:
        for event in connect_sse("http://localhost:8000/acp/events"):
            if event.event_type == "message":
                msg = event.as_message()
                print(f"{msg.from_agent}: {msg.content}")
    """
    request_headers = {
        "Accept": "text/event-stream",
        **(headers or {}),
    }

    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        with client.stream("GET", url, headers=request_headers) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                event = parse_sse_line(line)
                if event is not None:
                    yield event
