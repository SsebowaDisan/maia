from __future__ import annotations

import time
from typing import Callable, Optional

from .events import _emit_chat_message
from .models import ChatMessage, TeamConversation
from .workflow import brain_facilitates as _brain_facilitates
from .workflow import kickoff_step as _kickoff_step


class AgentTeamChatService:
    """Manages real-time agent conversations with personality and tension."""

    def __init__(self) -> None:
        self._conversations: dict[str, TeamConversation] = {}

    def start_conversation(
        self,
        *,
        run_id: str,
        topic: str,
        initiated_by: str,
        step_id: str = "",
        on_event: Optional[Callable] = None,
    ) -> TeamConversation:
        conv_id = f"conv_{int(time.time() * 1000)}"
        conv = TeamConversation(conversation_id=conv_id, run_id=run_id, topic=topic)
        self._conversations[conv_id] = conv
        return conv

    def send_message(
        self,
        *,
        conversation: TeamConversation,
        speaker_id: str,
        speaker_name: str = "",
        speaker_role: str = "",
        content: str,
        step_id: str = "",
        thread_id: str = "",
        task_id: str = "",
        task_title: str = "",
        reply_to_id: str = "",
        message_type: str = "message",
        mood: str = "neutral",
        mentions: list[str] | None = None,
        requires_ack: bool = False,
        delivery_status: str = "delivered",
        acked_by: list[str] | None = None,
        reaction_to_id: str = "",
        reaction: str = "",
        to_agent: str = "team",
        on_event: Optional[Callable] = None,
    ) -> ChatMessage:
        msg = conversation.add(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            speaker_role=speaker_role,
            content=content,
            step_id=step_id,
            thread_id=thread_id or conversation.conversation_id,
            task_id=task_id or step_id,
            task_title=task_title or conversation.topic,
            reply_to_id=reply_to_id,
            message_type=message_type,
            mood=mood,
            mentions=mentions,
            requires_ack=requires_ack,
            delivery_status=delivery_status,
            acked_by=acked_by,
            reaction_to_id=reaction_to_id,
            reaction=reaction,
        )
        _emit_chat_message(msg, on_event, to_agent=to_agent)
        try:
            from api.services.agent.collaboration_logs import (
                get_collaboration_service,
            )

            normalized_entry_type = "summary" if message_type == "summary" else "chat"
            metadata = msg.to_dict()
            metadata.update(
                {
                    "event_type": "team_chat_message",
                    "from_agent": msg.speaker_id,
                    "to_agent": to_agent,
                    "message": msg.content,
                    "entry_type": normalized_entry_type,
                    "message_id": msg.message_id,
                    "reply_to_id": msg.reply_to_id,
                    "thread_id": msg.thread_id,
                    "task_id": msg.task_id,
                    "task_title": msg.task_title,
                    "requires_ack": msg.requires_ack,
                    "delivery_status": msg.delivery_status,
                    "mentions": list(msg.mentions),
                    "acked_by": list(msg.acked_by),
                }
            )
            get_collaboration_service().record(
                run_id=msg.run_id,
                from_agent=msg.speaker_id,
                to_agent=to_agent,
                message=msg.content,
                entry_type=normalized_entry_type,
                metadata=metadata,
            )
        except Exception:
            pass
        return msg

    def kickoff_step(
        self,
        *,
        conversation: TeamConversation,
        current_agent: str,
        step_description: str,
        original_task: str,
        agents: list[dict[str, str]],
        step_id: str = "",
        tenant_id: str = "",
        on_event: Optional[Callable] = None,
    ) -> list[ChatMessage]:
        return _kickoff_step(
            self,
            conversation=conversation,
            current_agent=current_agent,
            step_description=step_description,
            original_task=original_task,
            agents=agents,
            step_id=step_id,
            tenant_id=tenant_id,
            on_event=on_event,
        )

    def brain_facilitates(
        self,
        *,
        conversation: TeamConversation,
        step_output: str,
        original_task: str,
        agents: list[dict[str, str]],
        step_id: str = "",
        tenant_id: str = "",
        on_event: Optional[Callable] = None,
    ) -> list[ChatMessage]:
        return _brain_facilitates(
            self,
            conversation=conversation,
            step_output=step_output,
            original_task=original_task,
            agents=agents,
            step_id=step_id,
            tenant_id=tenant_id,
            on_event=on_event,
        )

    def get_conversation(self, conversation_id: str) -> TeamConversation | None:
        return self._conversations.get(conversation_id)

    def get_conversations_for_run(self, run_id: str) -> list[TeamConversation]:
        return [c for c in self._conversations.values() if c.run_id == run_id]
