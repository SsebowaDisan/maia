export type IntegrationStatus = {
  configured: boolean;
  source?: "env" | "stored" | null;
};

export type WebSearchResult = {
  provider: string;
  query: string;
  count: number;
  offset: number;
  country: string;
  safesearch: string;
  total: number;
  results: Array<{
    title: string;
    url: string;
    description?: string | null;
    source?: string | null;
    age?: string | null;
  }>;
};

function inferApiBase() {
  const envBase = (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE_URL;
  if (envBase) {
    return envBase;
  }
  if (typeof window === "undefined") {
    return "";
  }
  const { hostname, port } = window.location;
  if (port === "5173" || port === "4173") {
    return `http://${hostname || "127.0.0.1"}:8000`;
  }
  return "";
}

const API_BASE = inferApiBase();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export function getMapsIntegrationStatus() {
  return request<IntegrationStatus>("/api/agent/integrations/maps/status");
}

export function saveMapsIntegrationKey(apiKey: string) {
  return request<{ status: string; configured: boolean }>("/api/agent/integrations/maps/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export function clearMapsIntegrationKey() {
  return request<{ status: string; cleared: boolean }>("/api/agent/integrations/maps/clear", {
    method: "POST",
  });
}

export function getBraveIntegrationStatus() {
  return request<IntegrationStatus>("/api/agent/integrations/brave/status");
}

export function runBraveWebSearch(payload: {
  query: string;
  count?: number;
  offset?: number;
  country?: string;
  safesearch?: string;
  domain?: string;
  runId?: string;
}) {
  return request<WebSearchResult>("/api/agent/tools/web_search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query: payload.query,
      count: payload.count ?? 10,
      offset: payload.offset ?? 0,
      country: payload.country ?? "BE",
      safesearch: payload.safesearch ?? "moderate",
      domain: payload.domain,
      run_id: payload.runId,
    }),
  });
}
