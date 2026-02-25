from __future__ import annotations

from typing import Any

from api.services.agent.live_events import get_live_event_broker


def emit_google_event(
    *,
    user_id: str,
    run_id: str | None,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    event_payload = {
        "type": event_type,
        "message": message,
        "data": dict(data or {}),
    }
    broker = get_live_event_broker()
    broker.publish(user_id=user_id, run_id=run_id, event=event_payload)
    if event_type != "status":
        status_payload = {
            "type": "status",
            "message": message,
            "data": {
                "event_type": event_type,
                **dict(data or {}),
            },
        }
        broker.publish(user_id=user_id, run_id=run_id, event=status_payload)
