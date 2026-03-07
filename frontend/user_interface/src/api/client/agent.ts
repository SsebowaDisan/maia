import { API_BASE, request, withUserIdQuery } from "./core";
import type { AgentLiveEvent, ConnectorCredentialRecord, ConnectorPluginManifest } from "./types";

function getAgentEventSnapshotUrl(runId: string, eventId: string): string {
  return `${API_BASE}/api/agent/runs/${encodeURIComponent(runId)}/events/${encodeURIComponent(eventId)}/snapshot`;
}

function getAgentRunEvents(runId: string) {
  return request<Array<{ type: string; payload: unknown }>>(
    `/api/agent/runs/${encodeURIComponent(runId)}/events`,
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

function listAgentTools() {
  return request<Array<Record<string, unknown>>>("/api/agent/tools");
}

function listConnectorHealth() {
  return request<Array<Record<string, unknown>>>("/api/agent/connectors/health");
}

function listConnectorPlugins() {
  return request<ConnectorPluginManifest[]>("/api/agent/connectors/plugins");
}

function getConnectorPlugin(connectorId: string) {
  return request<ConnectorPluginManifest>(`/api/agent/connectors/plugins/${encodeURIComponent(connectorId)}`);
}

function listConnectorCredentials() {
  return request<ConnectorCredentialRecord[]>("/api/agent/connectors/credentials");
}

function upsertConnectorCredentials(connectorId: string, values: Record<string, string>) {
  return request<ConnectorCredentialRecord>("/api/agent/connectors/credentials", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      connector_id: connectorId,
      values,
    }),
  });
}

function deleteConnectorCredentials(connectorId: string) {
  return request<{ status: string; connector_id: string }>(
    `/api/agent/connectors/credentials/${encodeURIComponent(connectorId)}`,
    {
      method: "DELETE",
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
      // Ignore malformed event chunks.
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
  deleteConnectorCredentials,
  exportAgentRunEvents,
  getAgentEventSnapshotUrl,
  getAgentRunEvents,
  getConnectorPlugin,
  listAgentTools,
  listConnectorCredentials,
  listConnectorHealth,
  listConnectorPlugins,
  subscribeAgentEvents,
  upsertConnectorCredentials,
};
