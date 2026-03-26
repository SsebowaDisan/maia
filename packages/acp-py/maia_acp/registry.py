"""Agent registry and lightweight routing helpers for ACP."""

from __future__ import annotations

from dataclasses import dataclass

from maia_acp.types import ACPCapabilities, AgentPresence, MessageIntent


def _score_agent(capabilities: ACPCapabilities) -> float:
    presence = capabilities.presence
    availability = presence.availability if presence else "available"
    task_count = int(presence.active_task_count or 0) if presence else 0
    capacity = max(1, int(capabilities.max_concurrent_tasks or 1))
    load_penalty = min(0.6, task_count / capacity)
    availability_bonus = {
        "available": 1.0,
        "focused": 0.7,
        "busy": 0.35,
        "offline": 0.0,
    }.get(availability or "available", 0.5)
    return availability_bonus - load_penalty


@dataclass
class ACPAgentRegistry:
    _capabilities: dict[str, ACPCapabilities]

    def __init__(self) -> None:
        self._capabilities = {}

    def upsert_capabilities(self, capabilities: ACPCapabilities) -> None:
        previous = self._capabilities.get(capabilities.agent_id)
        if previous is None:
            self._capabilities[capabilities.agent_id] = capabilities
            return
        merged_presence = (
            previous.presence.model_copy(
                update=capabilities.presence.model_dump(exclude_none=True)
            )
            if previous.presence and capabilities.presence
            else (capabilities.presence or previous.presence)
        )
        self._capabilities[capabilities.agent_id] = capabilities.model_copy(update={"presence": merged_presence})

    def update_presence(self, agent_id: str, presence: AgentPresence) -> None:
        previous = self._capabilities.get(agent_id)
        if previous is None:
            self._capabilities[agent_id] = ACPCapabilities(
                agent_id=agent_id,
                name=agent_id.replace("agent://", ""),
                skills=[],
                presence=presence,
            )
            return
        merged = previous.presence.model_copy(update=presence.model_dump(exclude_none=True)) if previous.presence else presence
        self._capabilities[agent_id] = previous.model_copy(update={"presence": merged})

    def get_capabilities(self, agent_id: str) -> ACPCapabilities | None:
        return self._capabilities.get(agent_id)

    def list_agents(self) -> list[ACPCapabilities]:
        return list(self._capabilities.values())

    def list_available_agents(self, intent: MessageIntent | None = None) -> list[ACPCapabilities]:
        candidates = []
        for agent in self._capabilities.values():
            if agent.presence and agent.presence.availability == "offline":
                continue
            if intent and agent.accepts_intents and intent not in agent.accepts_intents:
                continue
            candidates.append(agent)
        return sorted(candidates, key=_score_agent, reverse=True)

    def resolve_recipient(
        self,
        *,
        to: str | None = None,
        intent: MessageIntent | None = None,
        exclude_agent_id: str | None = None,
    ) -> ACPCapabilities | None:
        if to and to != "agent://broadcast":
            return self._capabilities.get(to)
        for agent in self.list_available_agents(intent):
            if agent.agent_id != exclude_agent_id:
                return agent
        return None
