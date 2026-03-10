import { request } from "./client/core";

export type IntegrationStatus = {
  configured: boolean;
  source?: "env" | "stored" | null;
};

export type GoogleServiceAccountStatus = {
  configured: boolean;
  usable: boolean;
  email: string;
  client_id?: string | null;
  project_id?: string | null;
  source?: string | null;
  auth_mode: "oauth" | "service_account";
  message: string;
  instructions: string[];
  aliases_count?: number;
};

export type GoogleWorkspaceAliasRecord = {
  alias: string;
  resource_type: string;
  resource_id: string;
  canonical_url: string;
};

export type GoogleOAuthServicesResponse = {
  services: string[];
  scopes: string[];
};

export type GoogleWorkspaceLinkAnalyzeResult = {
  detected: boolean;
  source: "link" | "alias" | "unknown";
  resource_type?: string;
  resource_id?: string;
  canonical_url?: string;
  label?: string;
  message?: string;
};

export type GoogleWorkspaceLinkAccessResult = {
  action: "read" | "edit";
  resource_type: string;
  checked_at: string;
  ready: boolean;
  required_role: string;
  can_read: boolean;
  can_edit: boolean;
  resource_name: string;
  resource_mime_type: string;
  canonical_url: string;
  resource_id: string;
  message: string;
  error_code?: string;
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

export function getGoogleServiceAccountStatus() {
  return request<GoogleServiceAccountStatus>(
    "/api/agent/integrations/google-workspace/service-account/status",
  );
}

export function saveGoogleWorkspaceAuthMode(mode: "oauth" | "service_account") {
  return request<{ status: string; mode: "oauth" | "service_account" }>(
    "/api/agent/integrations/google-workspace/service-account/auth-mode",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    },
  );
}

export function getGoogleOAuthServices() {
  return request<GoogleOAuthServicesResponse>("/api/agent/integrations/google/oauth/services");
}

export function saveGoogleOAuthServices(services: string[]) {
  return request<{ status: string; services: string[]; scopes: string[] }>(
    "/api/agent/integrations/google/oauth/services",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ services }),
    },
  );
}

export function getGoogleAnalyticsProperty() {
  return request<{ property_id: string; configured: boolean }>(
    "/api/agent/integrations/google/analytics/property",
  );
}

export function saveGoogleAnalyticsProperty(propertyId: string) {
  return request<{ status: string; property_id: string }>(
    "/api/agent/integrations/google/analytics/property",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ property_id: propertyId }),
    },
  );
}

export function listGoogleWorkspaceLinkAliases() {
  return request<{ aliases: GoogleWorkspaceAliasRecord[] }>(
    "/api/agent/integrations/google-workspace/link-assistant/aliases",
  );
}

export function analyzeGoogleWorkspaceLink(link: string) {
  return request<GoogleWorkspaceLinkAnalyzeResult>(
    "/api/agent/integrations/google-workspace/link-assistant/analyze",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ link }),
    },
  );
}

export function checkGoogleWorkspaceLinkAccess(payload: {
  link: string;
  action: "read" | "edit";
}) {
  return request<GoogleWorkspaceLinkAccessResult>(
    "/api/agent/integrations/google-workspace/link-assistant/check-access",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
}

export function saveGoogleWorkspaceLinkAlias(payload: {
  alias: string;
  link: string;
}) {
  return request<{ status: string; alias: GoogleWorkspaceAliasRecord; aliases: GoogleWorkspaceAliasRecord[] }>(
    "/api/agent/integrations/google-workspace/link-assistant/aliases/save",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
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
    status: "already_running" | "started" | "starting" | "installing";
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

// ─── llama-cpp-python (local models, no Ollama) ─────────────────────────────

export type LlamaCppModelRecord = {
  filename: string;
  size_bytes: number;
  path: string;
};

export type LlamaCppCatalogEntry = {
  name: string;
  filename: string;
  url: string;
  size_gb: number;
  type: "chat" | "embedding";
  recommended: boolean;
};

export type LlamaCppStatus = {
  installed: boolean;
  reachable: boolean;
  port: number;
  pid: number | null;
  base_url: string;
  active_model: string | null;
  active_embedding: string | null;
  server_models: { id: string; object: string }[];
};

export function getLlamaCppStatus() {
  return request<LlamaCppStatus>("/api/agent/integrations/llamacpp/status");
}

export function getLlamaCppCatalog() {
  return request<{ models: LlamaCppCatalogEntry[] }>("/api/agent/integrations/llamacpp/catalog");
}

export function listLlamaCppModels() {
  return request<{ total: number; models: LlamaCppModelRecord[] }>(
    "/api/agent/integrations/llamacpp/models",
  );
}

export function downloadLlamaCppModel(payload: {
  url: string;
  filename: string;
  runId?: string;
}) {
  return request<{ status: string; filename: string; size_bytes: number; path: string }>(
    "/api/agent/integrations/llamacpp/download",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: payload.url, filename: payload.filename, run_id: payload.runId }),
    },
  );
}

export function startLlamaCppServer(payload: {
  modelFilename: string;
  port?: number;
  nGpuLayers?: number;
  waitSeconds?: number;
  runId?: string;
}) {
  return request<{ status: string; reachable: boolean; pid: number | null; base_url: string }>(
    "/api/agent/integrations/llamacpp/start",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model_filename: payload.modelFilename,
        port: payload.port,
        n_gpu_layers: payload.nGpuLayers,
        wait_seconds: payload.waitSeconds,
        run_id: payload.runId,
      }),
    },
  );
}

export function stopLlamaCppServer() {
  return request<{ status: string; port: number }>("/api/agent/integrations/llamacpp/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function selectLlamaCppModel(payload: { modelFilename: string; runId?: string }) {
  return request<{ status: string; filename: string; llm_name: string; type: string }>(
    "/api/agent/integrations/llamacpp/select",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_filename: payload.modelFilename, run_id: payload.runId }),
    },
  );
}

export function saveLlamaCppConfig(payload: { port?: number; modelDir?: string }) {
  return request<{ status: string; port: number }>("/api/agent/integrations/llamacpp/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port: payload.port, model_dir: payload.modelDir }),
  });
}

// ─── end llama-cpp-python ────────────────────────────────────────────────────

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
