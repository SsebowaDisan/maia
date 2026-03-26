"""ACP Client — connect to event streams and emit typed ACP events."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable, Protocol

from maia_acp.builders import envelope
from maia_acp.registry import ACPAgentRegistry
from maia_acp.stream import connect_sse
from maia_acp.types import (
    ACPActivity,
    ACPCapabilities,
    ACPEvent,
    ACPHandoff,
    ACPMessage,
    ACPReview,
    AgentPresence,
)

logger = logging.getLogger(__name__)

EventCallback = Callable[[ACPEvent], None]


class ACPTransport(Protocol):
    def deliver(
        self,
        event: ACPEvent,
        *,
        recipient: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        ...


def _presence_from_activity(activity: ACPActivity) -> AgentPresence:
    kind = str(activity.activity or "").strip().lower()
    detail = str(activity.detail or "").strip() or None
    if kind in {"idle", "waiting"}:
        return AgentPresence(
            availability="available",
            current_focus=detail,
        )
    if kind == "error":
        return AgentPresence(
            availability="busy",
            current_focus=detail,
        )
    return AgentPresence(
        availability="focused" if kind == "reviewing" else "busy",
        current_focus=detail,
        active_task_count=1,
    )


class ACPClient:
    """Client for the Agent Collaboration Protocol.

    Usage:
        client = ACPClient(agent_id="agent://researcher")
        client.connect("http://localhost:8000/acp/events")

        @client.on("message")
        def handle(event):
            msg = event.as_message()
            print(f"{msg.from_agent}: {msg.content}")
    """

    def __init__(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        role: str | None = None,
        transport: ACPTransport | None = None,
        registry: ACPAgentRegistry | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.name = name or agent_id.replace("agent://", "")
        self.role = role or "agent"
        self.transport = transport
        self.registry = registry or ACPAgentRegistry()
        self._run_id = ""
        self._listeners: dict[str, list[EventCallback]] = defaultdict(list)
        self._buffer: list[ACPEvent] = []
        self._connected = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self, stream_url: str, *, background: bool = True) -> None:
        """Connect to an ACP event stream.

        Args:
            stream_url: SSE endpoint URL.
            background: Run in a background thread (default True).
        """
        self._stop_event.clear()

        if background:
            self._thread = threading.Thread(
                target=self._listen_loop,
                args=(stream_url,),
                daemon=True,
            )
            self._thread.start()
        else:
            self._listen_loop(stream_url)

    def disconnect(self) -> None:
        self._stop_event.set()
        self._connected = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def connected(self) -> bool:
        return self._connected

    def _listen_loop(self, stream_url: str) -> None:
        try:
            self._connected = True
            for event in connect_sse(stream_url):
                if self._stop_event.is_set():
                    break
                self._handle_event(event)
        except Exception as exc:
            logger.warning("ACP stream error: %s", exc)
        finally:
            self._connected = False

    # ── Event Handling ────────────────────────────────────────────────────

    def on(self, event_type: str) -> Callable:
        """Decorator to register an event handler.

        Usage:
            @client.on("message")
            def handle(event):
                ...
        """
        def decorator(fn: EventCallback) -> EventCallback:
            self._listeners[event_type].append(fn)
            return fn
        return decorator

    def off(self, event_type: str, fn: EventCallback) -> None:
        if fn in self._listeners[event_type]:
            self._listeners[event_type].remove(fn)

    def _handle_event(self, event: ACPEvent) -> None:
        self._buffer.append(event)
        self._run_id = event.run_id
        if event.event_type == "capabilities":
            self.registry.upsert_capabilities(event.as_capabilities())
        elif event.event_type == "event":
            activity = event.as_activity()
            self.registry.update_presence(activity.agent_id, _presence_from_activity(activity))

        # Fire specific listeners
        for cb in self._listeners.get(event.event_type, []):
            try:
                cb(event)
            except Exception as exc:
                logger.warning("ACP handler error: %s", exc)

        # Fire wildcard listeners
        for cb in self._listeners.get("*", []):
            try:
                cb(event)
            except Exception as exc:
                logger.warning("ACP handler error: %s", exc)

    # ── Emit ──────────────────────────────────────────────────────────────

    def emit_message(self, payload: dict[str, Any]) -> ACPEvent:
        return envelope(self.agent_id, self._run_id, "message", payload)

    def emit_handoff(self, payload: dict[str, Any]) -> ACPEvent:
        return envelope(self.agent_id, self._run_id, "handoff", payload)

    def emit_review(self, payload: dict[str, Any]) -> ACPEvent:
        return envelope(self.agent_id, self._run_id, "review", payload)

    def emit_activity(self, payload: dict[str, Any]) -> ACPEvent:
        return envelope(self.agent_id, self._run_id, "event", payload)

    def emit_capabilities(self, payload: dict[str, Any]) -> ACPEvent:
        self.registry.upsert_capabilities(ACPCapabilities.model_validate(payload))
        return envelope(self.agent_id, self._run_id, "capabilities", payload)

    def _deliver(
        self,
        event: ACPEvent,
        *,
        recipient: str | None = None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        if self.transport is None:
            return {"status": "queued", "recipient": recipient}
        try:
            return self.transport.deliver(
                event,
                recipient=recipient,
                timeout_ms=timeout_ms,
            )
        except Exception as exc:
            return {
                "status": "failed",
                "recipient": recipient,
                "error": str(exc),
            }

    def send_message(
        self,
        payload: dict[str, Any],
        *,
        timeout_ms: int | None = None,
    ) -> ACPEvent:
        msg = ACPMessage.model_validate(payload)
        resolved = self.registry.resolve_recipient(
            to=msg.to,
            intent=msg.intent,
            exclude_agent_id=self.agent_id,
        )
        recipient = resolved.agent_id if resolved else msg.to
        msg.context = {
            **(msg.context or {}),
            "delivery_status": "queued",
        }
        msg.to = recipient
        event = self.emit_message(msg.model_dump(by_alias=True))
        receipt = self._deliver(event, recipient=recipient, timeout_ms=timeout_ms)
        msg.context["delivery_status"] = receipt.get("status", "queued")
        return event.model_copy(update={"payload": msg.model_dump(by_alias=True)})

    def send_handoff(
        self,
        payload: dict[str, Any],
        *,
        timeout_ms: int | None = None,
    ) -> ACPEvent:
        handoff_payload = ACPHandoff.model_validate(payload)
        resolved = self.registry.resolve_recipient(
            to=handoff_payload.to,
            intent="handoff",
            exclude_agent_id=self.agent_id,
        )
        recipient = resolved.agent_id if resolved else handoff_payload.to
        handoff_payload.to = recipient
        if not handoff_payload.status:
            handoff_payload.status = "proposed"
        event = self.emit_handoff(handoff_payload.model_dump(by_alias=True))
        receipt = self._deliver(event, recipient=recipient, timeout_ms=timeout_ms)
        if receipt.get("status") == "failed":
            handoff_payload.status = "rejected"
            handoff_payload.declined_reason = receipt.get("error")
        return event.model_copy(update={"payload": handoff_payload.model_dump(by_alias=True)})

    def send_review(
        self,
        payload: dict[str, Any],
        *,
        recipient: str | None = None,
        timeout_ms: int | None = None,
    ) -> ACPEvent:
        review_payload = ACPReview.model_validate(payload)
        event = self.emit_review(review_payload.model_dump(by_alias=True))
        self._deliver(
            event,
            recipient=recipient or review_payload.author,
            timeout_ms=timeout_ms,
        )
        return event

    # ── Buffer / Query ────────────────────────────────────────────────────

    @property
    def events(self) -> list[ACPEvent]:
        return list(self._buffer)

    @property
    def run_id(self) -> str:
        return self._run_id

    def messages(self) -> list[ACPEvent]:
        return [e for e in self._buffer if e.event_type == "message"]

    def total_cost(self) -> dict[str, float]:
        tokens = 0
        usd = 0.0
        for event in self._buffer:
            if event.event_type == "event":
                cost = event.payload.get("cost")
                if isinstance(cost, dict):
                    tokens += cost.get("tokens_used", 0)
                    usd += cost.get("cost_usd", 0.0)
        return {"tokens": tokens, "usd": usd}

    def clear_buffer(self) -> None:
        self._buffer.clear()

    def list_agents(self) -> list[ACPCapabilities]:
        return self.registry.list_agents()

    def list_available_agents(self, intent: str | None = None) -> list[ACPCapabilities]:
        return self.registry.list_available_agents(intent)  # type: ignore[arg-type]
