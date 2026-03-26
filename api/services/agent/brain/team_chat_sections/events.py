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
            "message_id": msg.message_id,
            "reply_to_id": msg.reply_to_id,
            "entry_type": entry_type,
            "thread_id": msg.thread_id,
            "task_id": msg.task_id,
            "task_title": msg.task_title,
            "requires_ack": msg.requires_ack,
            "delivery_status": msg.delivery_status,
            "mentions": list(msg.mentions),
            "acked_by": list(msg.acked_by),
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
