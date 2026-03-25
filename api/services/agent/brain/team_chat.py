"""Agent Team Chat - LLM-driven conversations between agents."""
from __future__ import annotations

from api.services.agent.brain.team_chat_sections.events import _emit_chat_message
from api.services.agent.brain.team_chat_sections.llm import (
    MAX_CHAT_TURNS,
    PERSONALITY_ARCHETYPES,
    PERSONALITY_PROMPT,
    _call_agent_llm,
    _call_json_llm,
    _get_personality,
    _infer_mood_from_response,
)
from api.services.agent.brain.team_chat_sections.models import ChatMessage, TeamConversation
from api.services.agent.brain.team_chat_sections.participants import (
    _humanize_agent_id,
    _normalize_agents,
    _normalized_role,
    _preferred_watcher_agent,
    _resolve_facilitator_agent,
    _resolve_participants,
)
from api.services.agent.brain.team_chat_sections.service import AgentTeamChatService
from api.services.agent.brain.team_chat_sections.workflow import brain_facilitates, kickoff_step

_service: AgentTeamChatService | None = None


def get_team_chat_service() -> AgentTeamChatService:
    global _service
    if _service is None:
        _service = AgentTeamChatService()
    return _service
