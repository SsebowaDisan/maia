import { request } from "./client/core";

export type IntegrationStatus = {
  configured: boolean;
  source?: "env" | "stored" | null;
};

export type OllamaModelRecord = {
  name: string;
  size: number;
  digest: string;
  modified_at: string;
  details?: Record<string, unknown>;
};

export type OllamaStatus = {
  configured: boolean;
  reachable: boolean;
  base_url: string;
  version?: string | null;
  active_model?: string | null;
  active_embedding_model?: string | null;
  models: OllamaModelRecord[];
  recommended_models: string[];
  recommended_embedding_models: string[];
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
};

export type OllamaQuickstart = {
  platform: string;
  base_url: string;
  install_url: string;
  commands: {
    check: string;
    start: string;
    pull_model: string;
    pull_embedding: string;
  };
  tips: string[];
};

export type OllamaPullResponse = {
  status: string;
  base_url: string;
  pull: {
    model: string;
    status: string;
    percent: number;
    updates: number;
    completed: boolean;
  };
  selected_llm_name?: string | null;
  models: OllamaModelRecord[];
  active_model?: string | null;
};

export type OllamaApplyAllResponse = {
  status: string;
  model: string;
  embedding_name: string;
  base_url: string;
  indexes_total: number;
  indexes_updated: number;
  jobs_total: number;
  jobs: Array<{
    job_id: string;
    index_id: number;
    index_name: string;
    kind: "files" | "urls";
    total_items: number;
  }>;
  indexes: Array<{
    index_id: number;
    index_name: string;
    embedding_updated: boolean;
    previous_embedding?: string | null;
    embedding: string;
    files_queued: number;
    urls_queued: number;
    file_job_id?: string | null;
    url_job_id?: string | null;
    skipped_sources: number;
    total_sources: number;
  }>;
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

export function getOllamaIntegrationStatus() {
  return request<OllamaStatus>("/api/agent/integrations/ollama/status");
}

export function getOllamaQuickstart(baseUrl?: string) {
  const query = new URLSearchParams();
  if (baseUrl && baseUrl.trim()) {
    query.set("base_url", baseUrl.trim());
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<OllamaQuickstart>(`/api/agent/integrations/ollama/quickstart${suffix}`);
}

export function startLocalOllama(payload?: {
  baseUrl?: string;
  waitSeconds?: number;
  runId?: string;
}) {
  return request<{
    base_url: string;
    status: "already_running" | "started" | "starting";
    reachable: boolean;
    version?: string | null;
    pid?: number | null;
    error?: {
      code?: string;
      message?: string;
      details?: Record<string, unknown>;
    } | null;
  }>("/api/agent/integrations/ollama/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      base_url: payload?.baseUrl,
      wait_seconds: payload?.waitSeconds ?? 10,
      run_id: payload?.runId,
    }),
  });
}

export function saveOllamaIntegrationConfig(baseUrl: string) {
  return request<{ status: string; base_url: string }>("/api/agent/integrations/ollama/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ base_url: baseUrl }),
  });
}

export function listOllamaModels(baseUrl?: string) {
  const query = new URLSearchParams();
  if (baseUrl && baseUrl.trim()) {
    query.set("base_url", baseUrl.trim());
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<{ base_url: string; total: number; models: OllamaModelRecord[] }>(
    `/api/agent/integrations/ollama/models${suffix}`,
  );
}

export function pullOllamaModel(payload: {
  model: string;
  baseUrl?: string;
  autoSelect?: boolean;
  runId?: string;
}) {
  return request<OllamaPullResponse>("/api/agent/integrations/ollama/pull", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: payload.model,
      base_url: payload.baseUrl,
      auto_select: payload.autoSelect ?? true,
      run_id: payload.runId,
    }),
  });
}

export function selectOllamaModel(payload: {
  model: string;
  baseUrl?: string;
  runId?: string;
}) {
  return request<{ status: string; model: string; llm_name: string; base_url: string }>(
    "/api/agent/integrations/ollama/select",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: payload.model,
        base_url: payload.baseUrl,
        run_id: payload.runId,
      }),
    },
  );
}

export function selectOllamaEmbeddingModel(payload: {
  model: string;
  baseUrl?: string;
  runId?: string;
}) {
  return request<{ status: string; model: string; embedding_name: string; base_url: string }>(
    "/api/agent/integrations/ollama/embeddings/select",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: payload.model,
        base_url: payload.baseUrl,
        run_id: payload.runId,
      }),
    },
  );
}

export function applyOllamaEmbeddingToAllCollections(payload: {
  model: string;
  baseUrl?: string;
  runId?: string;
}) {
  return request<OllamaApplyAllResponse>("/api/agent/integrations/ollama/embeddings/apply-all", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: payload.model,
      base_url: payload.baseUrl,
      run_id: payload.runId,
    }),
  });
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
