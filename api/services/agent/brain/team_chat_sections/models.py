from __future__ import annotations

import time
from typing import Any


class ChatMessage:
    """A single message in a team conversation."""

    __slots__ = (
        "message_id",
        "conversation_id",
        "run_id",
        "step_id",
        "speaker_id",
        "speaker_name",
        "speaker_role",
        "speaker_avatar",
        "speaker_color",
        "content",
        "reply_to_id",
        "timestamp",
        "message_type",
        "mood",
        "reaction_to_id",
        "reaction",
    )

    _COLORS = [
        "#ef4444",
        "#3b82f6",
        "#10b981",
        "#f59e0b",
        "#8b5cf6",
        "#ec4899",
        "#06b6d4",
        "#f97316",
    ]
    _color_map: dict[str, str] = {}
    _color_idx = 0

    def __init__(
        self,
        *,
        conversation_id: str,
        run_id: str,
        step_id: str = "",
        speaker_id: str,
        speaker_name: str = "",
        speaker_role: str = "",
        content: str,
        reply_to_id: str = "",
        message_type: str = "message",
        mood: str = "neutral",
        reaction_to_id: str = "",
        reaction: str = "",
    ):
        self.message_id = f"msg_{int(time.time() * 1000)}_{speaker_id[:6]}"
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.step_id = step_id
        self.speaker_id = speaker_id
        self.speaker_name = speaker_name or speaker_id
        self.speaker_role = speaker_role
        self.content = content
        self.reply_to_id = reply_to_id
        self.timestamp = time.time()
        self.message_type = message_type
        self.mood = mood
        self.reaction_to_id = reaction_to_id
        self.reaction = reaction
        if speaker_id not in ChatMessage._color_map:
            ChatMessage._color_map[speaker_id] = ChatMessage._COLORS[
                ChatMessage._color_idx % len(ChatMessage._COLORS)
            ]
            ChatMessage._color_idx += 1
        self.speaker_color = ChatMessage._color_map[speaker_id]
        self.speaker_avatar = (speaker_name or speaker_id or "?")[0].upper()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_role": self.speaker_role,
            "speaker_avatar": self.speaker_avatar,
            "speaker_color": self.speaker_color,
            "content": self.content,
            "reply_to_id": self.reply_to_id,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "mood": self.mood,
            "reaction_to_id": self.reaction_to_id,
            "reaction": self.reaction,
        }


class TeamConversation:
    """A conversation thread between agents."""

    def __init__(self, *, conversation_id: str, run_id: str, topic: str = ""):
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.topic = topic
        self.messages: list[ChatMessage] = []
        self.started_at = time.time()

    def add(self, **kwargs: Any) -> ChatMessage:
        kwargs["conversation_id"] = self.conversation_id
        kwargs["run_id"] = self.run_id
        msg = ChatMessage(**kwargs)
        self.messages.append(msg)
        return msg
