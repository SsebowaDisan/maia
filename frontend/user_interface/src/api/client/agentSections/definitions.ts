import { fetchApi, request } from "../core";
import type {
  AgentDefinitionInput,
  AgentDefinitionRecord,
  AgentInstallHistoryRecord,
  AgentPlaybookRecord,
  AgentScheduleRecord,
  AgentSummaryRecord,
  FeedbackRecord,
  ImprovementSuggestionRecord,
} from "./types";
import {
  isNotFoundError,
  toAgentDefinitionFromPlaybook,
  toAgentSummaryFromPlaybook,
  toLegacyPlaybookPayload,
} from "./types";

function createAgent(definition: AgentDefinitionInput) {
  return request<{ id: string; agent_id: string; version: string }>("/api/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  }).catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyPayload = toLegacyPlaybookPayload(definition);
    const created = await request<AgentPlaybookRecord>("/api/agent/playbooks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(legacyPayload),
    });
    const id = String(created.id || legacyPayload.name || definition.agent_id || definition.id || "").trim();
    return {
      id,
      agent_id: id || String(definition.agent_id || definition.id || legacyPayload.name || "legacy-agent"),
      version: String(created.version || definition.version || "1"),
    };
  });
}

function listPlaybooks(options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentPlaybookRecord[]>(`/api/agent/playbooks${suffix}`);
}

function listAgents() {
  return request<AgentSummaryRecord[]>("/api/agents").catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const playbooks = await listPlaybooks({ limit: 500 });
    return playbooks.map(toAgentSummaryFromPlaybook);
  });
}

function listRecentAgents() {
  return request<AgentSummaryRecord[]>("/api/agents/recent").catch((error) => {
    if (isNotFoundError(error)) {
      return [] as AgentSummaryRecord[];
    }
    throw error;
  });
}

function getAgent(agentId: string, options?: { version?: string }) {
  const query = new URLSearchParams();
  if (options?.version) {
    query.set("version", options.version);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentDefinitionRecord>(`/api/agents/${encodeURIComponent(agentId)}${suffix}`).catch(
    async (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      const playbooks = await listPlaybooks({ limit: 500 });
      const match = playbooks.find((row) => String(row.id || "").trim() === agentId);
      if (!match) {
        throw new Error("Agent not found.");
      }
      return toAgentDefinitionFromPlaybook(match);
    },
  );
}

function updateAgent(agentId: string, definition: AgentDefinitionInput) {
  return request<{ id: string; agent_id: string; version: string }>(
    `/api/agents/${encodeURIComponent(agentId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(definition),
    },
  ).catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyPayload = toLegacyPlaybookPayload(definition);
    const updated = await request<AgentPlaybookRecord>(`/api/agent/playbooks/${encodeURIComponent(agentId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(legacyPayload),
    });
    const id = String(updated.id || agentId).trim();
    return {
      id,
      agent_id: id,
      version: String(updated.version || definition.version || "1"),
    };
  });
}

async function deleteAgent(agentId: string) {
  const response = await fetchApi(`/api/agents/${encodeURIComponent(agentId)}`, {
    method: "DELETE",
  });
  if (response.ok || response.status === 204) {
    return;
  }
  if (response.status === 404) {
    throw new Error("Delete is not supported by this backend API.");
  }
  const detail = (await response.text()).trim();
  throw new Error(detail || `Delete failed: ${response.status}`);
}

function listSchedules() {
  return request<AgentScheduleRecord[]>("/api/agent/schedules");
}

function recordFeedback(
  agentId: string,
  runId: string,
  originalOutput: string,
  correctedOutput: string,
  feedbackType: "correction" | "approval" | "rejection" = "correction",
) {
  return request<FeedbackRecord>(`/api/agents/${encodeURIComponent(agentId)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      original_output: originalOutput,
      corrected_output: correctedOutput,
      feedback_type: feedbackType,
    }),
  }).catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return request<FeedbackRecord>(`/api/agent/${encodeURIComponent(agentId)}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        original_output: originalOutput,
        corrected_output: correctedOutput,
        feedback_type: feedbackType,
      }),
    });
  });
}

function getImprovementSuggestion(agentId: string) {
  return request<ImprovementSuggestionRecord>(`/api/agents/${encodeURIComponent(agentId)}/improvement`).catch(
    (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      return request<ImprovementSuggestionRecord>(`/api/agent/${encodeURIComponent(agentId)}/improvement`);
    },
  );
}

function listAgentInstallHistory(agentId: string, options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (Number.isFinite(Number(options?.limit)) && Number(options?.limit) > 0) {
    query.set("limit", String(Math.max(1, Number(options?.limit))));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentInstallHistoryRecord[]>(
    `/api/agents/${encodeURIComponent(agentId)}/install-history${suffix}`,
  ).catch((error) => {
    if (isNotFoundError(error)) {
      return [] as AgentInstallHistoryRecord[];
    }
    throw error;
  });
}

export {
  createAgent,
  deleteAgent,
  getAgent,
  getImprovementSuggestion,
  listAgentInstallHistory,
  listAgents,
  listPlaybooks,
  listRecentAgents,
  listSchedules,
  recordFeedback,
  updateAgent,
};
