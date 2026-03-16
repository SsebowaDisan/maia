import { fetchApi, request } from "./core";

type MarketplaceAgentSummary = {
  id: string;
  agent_id: string;
  name: string;
  description: string;
  version: string;
  tags: string[];
  required_connectors: string[];
  pricing_tier: "free" | "paid" | "enterprise" | string;
  status: string;
  install_count: number;
  avg_rating: number;
  rating_count: number;
  has_computer_use: boolean;
  verified: boolean;
  published_at?: string | null;
};

type MarketplaceAgentDetail = MarketplaceAgentSummary & {
  definition: Record<string, unknown>;
  reviews: {
    avg: number;
    count: number;
    distribution: Record<string, number>;
  };
};

type MarketplaceAgentReview = {
  id: string;
  rating: number;
  review_text: string;
  publisher_response?: string | null;
  created_at?: string | null;
};

type MarketplaceAgentInstallResponse = {
  success: boolean;
  agent_id: string;
  missing_connectors?: string[];
  error?: string;
};

type MarketplaceAgentInstallRequest = {
  version?: string | null;
  connector_mapping?: Record<string, string>;
  gate_policies?: Record<string, boolean>;
};

type MarketplaceAgentUpdateRecord = {
  agent_id: string;
  current_version: string;
  latest_version: string;
  marketplace_id: string;
  changelog: string;
};

type MarketplaceApplyUpdateResponse = {
  success: boolean;
  agent_id?: string;
  new_version?: string;
  error?: string;
};

type MarketplaceListAgentsParams = {
  q?: string;
  tags?: string[];
  required_connectors?: string[];
  pricing?: "free" | "paid" | "enterprise";
  has_computer_use?: boolean;
  sort_by?: "installs" | "rating" | "newest";
  page?: number;
  limit?: number;
};

type ConnectorCatalogRecord = {
  id: string;
  name: string;
  description?: string;
  version?: string;
  author?: string;
  category?: string;
  tags?: string[];
  auth?: {
    kind?: string;
  };
  tools?: Array<{
    id: string;
    title?: string;
    description?: string;
  }>;
};

function buildListQuery(params?: MarketplaceListAgentsParams): string {
  const query = new URLSearchParams();
  if (!params) {
    return "";
  }
  if (params.q) {
    query.set("q", params.q);
  }
  if (params.tags?.length) {
    query.set("tags", params.tags.join(","));
  }
  if (params.required_connectors?.length) {
    query.set("required_connectors", params.required_connectors.join(","));
  }
  if (params.pricing) {
    query.set("pricing", params.pricing);
  }
  if (typeof params.has_computer_use === "boolean") {
    query.set("has_computer_use", String(params.has_computer_use));
  }
  if (params.sort_by) {
    query.set("sort_by", params.sort_by);
  }
  if (typeof params.page === "number") {
    query.set("page", String(params.page));
  }
  if (typeof params.limit === "number") {
    query.set("limit", String(params.limit));
  }
  const text = query.toString();
  return text ? `?${text}` : "";
}

function listMarketplaceAgents(params?: MarketplaceListAgentsParams) {
  const suffix = buildListQuery(params);
  return request<MarketplaceAgentSummary[]>(`/api/marketplace/agents${suffix}`);
}

function getMarketplaceAgent(agentId: string, options?: { version?: string }) {
  const query = new URLSearchParams();
  if (options?.version) {
    query.set("version", options.version);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<MarketplaceAgentDetail>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}${suffix}`,
  );
}

function getMarketplaceAgentReviews(agentId: string, options?: { limit?: number; offset?: number }) {
  const query = new URLSearchParams();
  if (typeof options?.limit === "number") {
    query.set("limit", String(options.limit));
  }
  if (typeof options?.offset === "number") {
    query.set("offset", String(options.offset));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<MarketplaceAgentReview[]>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/reviews${suffix}`,
  );
}

function installMarketplaceAgent(agentId: string, body?: MarketplaceAgentInstallRequest) {
  return request<MarketplaceAgentInstallResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/install`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version: body?.version || null,
        connector_mapping: body?.connector_mapping || {},
        gate_policies: body?.gate_policies || {},
      }),
    },
  );
}

function checkMarketplaceUpdates() {
  return request<MarketplaceAgentUpdateRecord[]>("/api/marketplace/updates");
}

function applyMarketplaceUpdate(agentId: string, targetVersion?: string | null) {
  return request<MarketplaceApplyUpdateResponse>(
    `/api/marketplace/updates/${encodeURIComponent(agentId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_version: targetVersion || null,
      }),
    },
  );
}

async function uninstallMarketplaceAgent(agentId: string) {
  const response = await fetchApi(`/api/marketplace/agents/${encodeURIComponent(agentId)}/install`, {
    method: "DELETE",
  });
  if (!response.ok && response.status !== 204) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Uninstall failed: ${response.status}`);
  }
}

// Connector marketplace endpoint is not available yet in backend.
// We use the live connector catalog as the discovery source.
function listConnectorCatalog() {
  return request<ConnectorCatalogRecord[]>("/api/connectors");
}

export {
  applyMarketplaceUpdate,
  checkMarketplaceUpdates,
  getMarketplaceAgent,
  getMarketplaceAgentReviews,
  installMarketplaceAgent,
  listConnectorCatalog,
  listMarketplaceAgents,
  uninstallMarketplaceAgent,
};

export type {
  ConnectorCatalogRecord,
  MarketplaceAgentUpdateRecord,
  MarketplaceAgentDetail,
  MarketplaceApplyUpdateResponse,
  MarketplaceAgentInstallResponse,
  MarketplaceAgentReview,
  MarketplaceAgentSummary,
};
