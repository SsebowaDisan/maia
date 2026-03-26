import type {
  ACPCapabilities,
  ACPRegistryLike,
  AgentPresence,
  MessageIntent,
} from "./types";

function scoreAgent(capabilities: ACPCapabilities): number {
  const presence = capabilities.presence;
  const availability = presence?.availability ?? "available";
  const taskCount = Number(presence?.active_task_count ?? 0);
  const capacity = Math.max(1, Number(capabilities.max_concurrent_tasks ?? 1));
  const loadPenalty = Math.min(0.6, taskCount / capacity);
  const availabilityBonus =
    availability === "available"
      ? 1
      : availability === "focused"
        ? 0.7
        : availability === "busy"
          ? 0.35
          : 0;
  return availabilityBonus - loadPenalty;
}

class ACPAgentRegistry implements ACPRegistryLike {
  private capabilities = new Map<string, ACPCapabilities>();

  upsertCapabilities(capabilities: ACPCapabilities): void {
    const previous = this.capabilities.get(capabilities.agent_id);
    this.capabilities.set(capabilities.agent_id, {
      ...previous,
      ...capabilities,
      presence: {
        ...(previous?.presence ?? {}),
        ...(capabilities.presence ?? {}),
      },
    });
  }

  updatePresence(agentId: string, presence: AgentPresence): void {
    const previous = this.capabilities.get(agentId);
    if (!previous) {
      this.capabilities.set(agentId, {
        agent_id: agentId,
        name: agentId.replace("agent://", ""),
        skills: [],
        presence,
      });
      return;
    }
    this.capabilities.set(agentId, {
      ...previous,
      presence: {
        ...(previous.presence ?? {}),
        ...presence,
      },
    });
  }

  getCapabilities(agentId: string): ACPCapabilities | undefined {
    return this.capabilities.get(agentId);
  }

  listAgents(): ACPCapabilities[] {
    return Array.from(this.capabilities.values());
  }

  listAvailableAgents(intent?: MessageIntent): ACPCapabilities[] {
    return this.listAgents()
      .filter((agent) => {
        if (agent.presence?.availability === "offline") {
          return false;
        }
        if (!intent) {
          return true;
        }
        if (!agent.accepts_intents || agent.accepts_intents.length === 0) {
          return true;
        }
        return agent.accepts_intents.includes(intent);
      })
      .sort((left, right) => scoreAgent(right) - scoreAgent(left));
  }

  resolveRecipient(input: {
    to?: string;
    intent?: MessageIntent;
    excludeAgentId?: string;
  }): ACPCapabilities | undefined {
    const direct = String(input.to || "").trim();
    if (direct && direct !== "agent://broadcast") {
      return this.getCapabilities(direct);
    }
    return this.listAvailableAgents(input.intent).find(
      (agent) => agent.agent_id !== input.excludeAgentId,
    );
  }
}

export { ACPAgentRegistry };
