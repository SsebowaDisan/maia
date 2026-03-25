import { fetchApi, request } from "../core";
import type {
  ConnectorBindingRecord,
  ConnectorCredentialRecord,
  ConnectorPluginManifest,
  RegisterWebhookResponse,
  WebhookRecord,
} from "./types";
import { isNotFoundError } from "./types";

function listAgentTools() {
  return request<Array<Record<string, unknown>>>("/api/agent/tools");
}

function listConnectorHealth() {
  return request<Array<Record<string, unknown>>>("/api/agent/connectors/health");
}

function testConnectorConnection(connectorId: string) {
  return request<{
    status: string;
    connector_id?: string;
    detail?: string;
  }>(`/api/connectors/${encodeURIComponent(connectorId)}/test`).catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return listConnectorHealth().then((rows) => {
      const row = rows.find((entry) => String(entry?.connector_id || "") === connectorId);
      if (!row) {
        return {
          status: "error",
          detail: "Connector health response did not include this connector.",
        };
      }
      return {
        status: Boolean(row?.ok) ? "ok" : "error",
        connector_id: connectorId,
        detail: String(row?.message || ""),
      };
    });
  });
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
  return request<{ status: string; connector_id: string }>(
    `/api/connectors/${encodeURIComponent(connectorId)}/credentials`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values }),
    },
  ).catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return request<ConnectorCredentialRecord>("/api/agent/connectors/credentials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ connector_id: connectorId, values }),
    });
  });
}

function deleteConnectorCredentials(connectorId: string) {
  return request<{ status: string; connector_id: string }>(
    `/api/connectors/${encodeURIComponent(connectorId)}/credentials`,
    { method: "DELETE" },
  ).catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return request<{ status: string; connector_id: string }>(
      `/api/agent/connectors/credentials/${encodeURIComponent(connectorId)}`,
      { method: "DELETE" },
    );
  });
}

function getConnectorBinding(connectorId: string) {
  return request<ConnectorBindingRecord>(`/api/connectors/${encodeURIComponent(connectorId)}/bindings`);
}

function patchConnectorBinding(
  connectorId: string,
  payload: { allowed_agent_ids?: string[]; enabled_tool_ids?: string[] },
) {
  return request<{ status: string; connector_id: string }>(
    `/api/connectors/${encodeURIComponent(connectorId)}/bindings`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

function listWebhooks() {
  return request<WebhookRecord[]>("/api/connectors/webhooks").catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return request<WebhookRecord[]>("/api/agent/connectors/webhooks");
  });
}

function registerWebhook(connectorId: string, eventTypes: string[]) {
  return request<RegisterWebhookResponse>(
    `/api/connectors/${encodeURIComponent(connectorId)}/webhooks`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event_types: eventTypes }),
    },
  ).catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return request<RegisterWebhookResponse>(
      `/api/agent/connectors/${encodeURIComponent(connectorId)}/webhooks`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_types: eventTypes }),
      },
    );
  });
}

async function deregisterWebhook(webhookId: string) {
  const response = await fetchApi(`/api/connectors/webhooks/${encodeURIComponent(webhookId)}`, {
    method: "DELETE",
  });
  if (response.status === 404) {
    const legacy = await fetchApi(`/api/agent/connectors/webhooks/${encodeURIComponent(webhookId)}`, {
      method: "DELETE",
    });
    if (legacy.ok || legacy.status === 204) {
      return;
    }
    const legacyDetail = (await legacy.text()).trim();
    throw new Error(legacyDetail || `Delete failed: ${legacy.status}`);
  }
  if (!response.ok && response.status !== 204) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Delete failed: ${response.status}`);
  }
}

export {
  deleteConnectorCredentials,
  deregisterWebhook,
  getConnectorBinding,
  getConnectorPlugin,
  listAgentTools,
  listConnectorCredentials,
  listConnectorHealth,
  listConnectorPlugins,
  listWebhooks,
  patchConnectorBinding,
  registerWebhook,
  testConnectorConnection,
  upsertConnectorCredentials,
};
