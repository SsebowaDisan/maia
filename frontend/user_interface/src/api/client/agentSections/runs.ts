import { API_BASE, request, withUserIdQuery } from "../core";
import type {
  AgentApiRunRecord,
  AgentLiveEvent,
  AgentRunRecord,
  GatePendingRecord,
  WorkGraphPayloadResponse,
  WorkGraphReplayStateResponse,
} from "./types";
import { isNotFoundError, toAgentRunFromApiRun } from "./types";

function getAgentEventSnapshotUrl(runId: string, eventId: string): string {
  return `${API_BASE}${withUserIdQuery(`/api/agent/runs/${encodeURIComponent(runId)}/events/${encodeURIComponent(eventId)}/snapshot`)}`;
}

function getAgentSnapshotRefUrl(snapshotRef: string): string {
  const query = new URLSearchParams();
  query.set("path", snapshotRef);
  return `${API_BASE}${withUserIdQuery(`/api/agent/snapshot-file?${query.toString()}`)}`;
}

function getAgentRunEvents(runId: string) {
  return request<unknown[]>(`/api/agent/runs/${encodeURIComponent(runId)}/events`);
}

function buildWorkGraphSuffix(filters?: {
  agent_role?: string;
  status?: string;
  event_index_min?: number;
  event_index_max?: number;
}): string {
  const query = new URLSearchParams();
  if (filters?.agent_role) {
    query.set("agent_role", filters.agent_role);
  }
  if (filters?.status) {
    query.set("status", filters.status);
  }
  if (typeof filters?.event_index_min === "number") {
    query.set("event_index_min", String(filters.event_index_min));
  }
  if (typeof filters?.event_index_max === "number") {
    query.set("event_index_max", String(filters.event_index_max));
  }
  return query.toString() ? `?${query.toString()}` : "";
}

function getAgentRunWorkGraph(
  runId: string,
  filters?: {
    agent_role?: string;
    status?: string;
    event_index_min?: number;
    event_index_max?: number;
  },
) {
  return request<WorkGraphPayloadResponse>(
    `/api/agent/runs/${encodeURIComponent(runId)}/work-graph${buildWorkGraphSuffix(filters)}`,
  );
}

function getAgentRunWorkGraphReplayState(
  runId: string,
  filters?: {
    agent_role?: string;
    status?: string;
    event_index_min?: number;
    event_index_max?: number;
  },
) {
  return request<WorkGraphReplayStateResponse>(
    `/api/agent/runs/${encodeURIComponent(runId)}/work-graph/replay-state${buildWorkGraphSuffix(filters)}`,
  );
}

function exportAgentRunEvents(runId: string) {
  return request<{
    run_id: string;
    run_started: Record<string, unknown>;
    run_completed: Record<string, unknown>;
    total_rows: number;
    total_events: number;
    events: Array<Record<string, unknown>>;
  }>(`/api/agent/runs/${encodeURIComponent(runId)}/events/export`);
}

function listAgentRuns(agentId: string, options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentRunRecord[]>(`/api/agents/${encodeURIComponent(agentId)}/runs${suffix}`).catch(
    async (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      const legacyRows = await listAgentApiRuns({ limit: options?.limit ?? 100 });
      const filtered = legacyRows.filter((row) => String(row.agent_id || "").trim() === agentId);
      const selected = filtered.length ? filtered : legacyRows;
      return selected.map(toAgentRunFromApiRun);
    },
  );
}

function listAgentApiRuns(options?: { limit?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<AgentApiRunRecord[]>(`/api/agent/runs${suffix}`);
}

function getAgentRun(runId: string) {
  return request<AgentRunRecord>(`/api/agents/runs/${encodeURIComponent(runId)}`).catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyRun = await request<AgentApiRunRecord>(`/api/agent/runs/${encodeURIComponent(runId)}`);
    return toAgentRunFromApiRun(legacyRun);
  });
}

function listPendingGates(runId: string) {
  return request<GatePendingRecord[]>(`/api/agents/runs/${encodeURIComponent(runId)}/gates`).catch(
    (error) => {
      if (isNotFoundError(error)) {
        return [] as GatePendingRecord[];
      }
      throw error;
    },
  );
}

function approveAgentRunGate(runId: string, gateId: string, editedParams?: Record<string, unknown>) {
  const body = editedParams && Object.keys(editedParams).length > 0 ? editedParams : {};
  return request<{ status: string; run_id: string; gate_id: string }>(
    `/api/agents/runs/${encodeURIComponent(runId)}/gates/${encodeURIComponent(gateId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

function rejectAgentRunGate(runId: string, gateId: string) {
  return request<{ status: string; run_id: string; gate_id: string }>(
    `/api/agents/runs/${encodeURIComponent(runId)}/gates/${encodeURIComponent(gateId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
}

function subscribeAgentEvents(options?: {
  runId?: string;
  replay?: number;
  onReady?: (payload: Record<string, unknown>) => void;
  onEvent?: (event: AgentLiveEvent) => void;
  onError?: () => void;
}) {
  const query = new URLSearchParams();
  if (options?.runId) {
    query.set("run_id", options.runId);
  }
  if (typeof options?.replay === "number") {
    query.set("replay", String(options.replay));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const eventSource = new EventSource(`${API_BASE}${withUserIdQuery(`/api/agent/events${suffix}`)}`);

  eventSource.addEventListener("ready", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onReady?.(parsed);
    } catch {
      options?.onReady?.({});
    }
  });
  eventSource.addEventListener("event", (event) => {
    try {
      const parsed = JSON.parse((event as MessageEvent<string>).data || "{}");
      options?.onEvent?.(parsed as AgentLiveEvent);
    } catch {
      // Ignore malformed event payloads.
    }
  });
  eventSource.onerror = () => {
    options?.onError?.();
  };

  return () => {
    eventSource.close();
  };
}

export {
  approveAgentRunGate,
  exportAgentRunEvents,
  getAgentEventSnapshotUrl,
  getAgentSnapshotRefUrl,
  getAgentRun,
  getAgentRunEvents,
  getAgentRunWorkGraph,
  getAgentRunWorkGraphReplayState,
  listAgentApiRuns,
  listAgentRuns,
  listPendingGates,
  rejectAgentRunGate,
  subscribeAgentEvents,
};
