from __future__ import annotations

from typing import Callable, Optional

from .models import ChatMessage


def _emit_chat_message(
    msg: ChatMessage,
    on_event: Optional[Callable] = None,
    *,
    to_agent: str = "team",
) -> None:
    entry_type = "summary" if msg.message_type == "summary" else "chat"
    event = {
        "event_type": "team_chat_message",
        "title": msg.speaker_name,
        "detail": msg.content[:300],
        "stage": "execute",
        "status": "info",
        "data": {
            **msg.to_dict(),
            "from_agent": msg.speaker_id,
            "to_agent": to_agent,
            "message": msg.content,
            "entry_type": entry_type,
            "scene_surface": "team_chat",
            "scene_family": "chat",
            "event_family": "chat",
        },
    }
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass
    try:
        from api.services.agent.live_events import get_live_event_broker

        get_live_event_broker().publish(user_id="", run_id=msg.run_id, event=event)
    except Exception:
        pass
