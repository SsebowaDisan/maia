import { request } from "./core";
import type {
  GoogleOAuthConfigStatus,
  GoogleOAuthStatus,
  GoogleOAuthToolCatalogEntry,
} from "./types";

function startGoogleOAuth(options?: {
  redirectUri?: string;
  scopes?: string[];
  toolIds?: string[];
  state?: string;
}) {
  const query = new URLSearchParams();
  if (options?.redirectUri) {
    query.set("redirect_uri", options.redirectUri);
  }
  if (options?.scopes && options.scopes.length > 0) {
    query.set("scopes", options.scopes.join(","));
  }
  if (options?.toolIds && options.toolIds.length > 0) {
    query.set("tool_ids", options.toolIds.join(","));
  }
  if (options?.state) {
    query.set("state", options.state);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{
    authorize_url: string;
    state: string;
    redirect_uri: string;
    scopes: string[];
  }>(`/api/agent/oauth/google/start${suffix}`);
}

function exchangeGoogleOAuthCode(payload: {
  code: string;
  redirectUri?: string;
  state?: string;
  connectorIds?: string[];
}) {
  return request<{
    status: string;
    stored_connectors: string[];
    token_type: string;
    expires_at: string | null;
    refresh_token_stored: boolean;
    deprecated?: boolean;
    warning?: string;
  }>("/api/agent/oauth/google/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: payload.code,
      redirect_uri: payload.redirectUri,
      state: payload.state,
      connector_ids: payload.connectorIds,
    }),
  });
}

function getGoogleOAuthStatus() {
  return request<GoogleOAuthStatus>("/api/agent/oauth/google/status");
}

function getGoogleOAuthConfig() {
  return request<GoogleOAuthConfigStatus>("/api/agent/oauth/google/config");
}

function getGoogleOAuthToolCatalog() {
  return request<{ tools: GoogleOAuthToolCatalogEntry[] }>("/api/agent/oauth/google/tools");
}

function saveGoogleOAuthConfig(payload: {
  clientId: string;
  clientSecret: string;
  redirectUri?: string;
}) {
  return request<GoogleOAuthConfigStatus>("/api/agent/oauth/google/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      client_id: payload.clientId,
      client_secret: payload.clientSecret,
      redirect_uri: payload.redirectUri,
    }),
  });
}

function requestGoogleOAuthSetup(payload?: { note?: string }) {
  return request<{
    status: string;
    request?: {
      id: string;
      requester_user_id: string;
      note: string;
      status: string;
      requested_at: string;
      resolved_at: string;
      resolved_by: string;
    };
    pending_count: number;
    workspace_owner_user_id?: string | null;
  }>("/api/agent/oauth/google/config/request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      note: payload?.note,
    }),
  });
}

function disconnectGoogleOAuth() {
  return request<{
    status: string;
    revoked: boolean;
    cleared_connectors: string[];
  }>("/api/agent/oauth/google/disconnect", {
    method: "POST",
  });
}

export {
  disconnectGoogleOAuth,
  exchangeGoogleOAuthCode,
  getGoogleOAuthConfig,
  getGoogleOAuthToolCatalog,
  getGoogleOAuthStatus,
  requestGoogleOAuthSetup,
  saveGoogleOAuthConfig,
  startGoogleOAuth,
};
