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
  connector_status?: Record<string, "connected" | "missing" | "not_required" | string>;
  is_installed?: boolean;
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

type MarketplaceAgentVersionRecord = {
  id: string;
  agent_id: string;
  version: string;
  status: string;
  changelog?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  published_at?: string | null;
  revision_count?: number | null;
  rejection_reason?: string | null;
};

type MarketplaceAgentInstallResponse = {
  success: boolean;
  agent_id: string;
  missing_connectors?: string[];
  error?: string;
  description?: string;
  trigger_family?: string | null;
  already_installed?: boolean;
  auto_mapped_connectors?: Record<string, string>;
  installed_agent?: {
    id: string;
    agent_id: string;
    name: string;
    version: string;
    is_active?: boolean;
    date_created?: string | null;
    date_updated?: string | null;
    definition?: Record<string, unknown>;
  } | null;
};

type MarketplaceAgentInstallRequest = {
  version?: string | null;
  connector_mapping?: Record<string, string>;
  gate_policies?: Record<string, boolean>;
};

type MarketplaceAgentInstallPreflightResponse = {
  can_install_immediately: boolean;
  already_installed: boolean;
  missing_connectors: string[];
  auto_mapped: Record<string, string>;
  agent_not_found: boolean;
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

type MarketplaceReviewStatus = "pending_review" | "approved" | "rejected" | "published" | "deprecated";

type MarketplaceReviewQueueItem = MarketplaceAgentSummary & {
  definition: Record<string, unknown>;
  rejection_reason?: string | null;
  revision_count?: number | null;
  reviewer_id?: string | null;
  review_started_at?: number | null;
};

type PublishMarketplaceAgentRequest = {
  definition: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

type PublishMarketplaceAgentResponse = {
  id: string;
  agent_id: string;
  status: string;
};

type SubmitMarketplaceAgentResponse = {
  status: string;
  agent_id: string;
};

type ReviseMarketplaceAgentRequest = {
  definition: Record<string, unknown>;
  changelog?: string;
};

type ReviseMarketplaceAgentResponse = {
  status: string;
  agent_id: string;
  revision_count?: number;
};

type MarketplaceNotificationRecord = {
  id: string;
  agent_id?: string | null;
  agent_name?: string | null;
  event_type: string;
  message: string;
  detail?: string | null;
  is_read: boolean;
  created_at?: string | null;
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

function preflightMarketplaceAgentInstall(agentId: string, options?: { version?: string | null }) {
  const query = new URLSearchParams();
  if (options?.version) {
    query.set("version", options.version);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<MarketplaceAgentInstallPreflightResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/install/preflight${suffix}`,
    {
      method: "POST",
    },
  );
}

function checkMarketplaceUpdates() {
  return request<MarketplaceAgentUpdateRecord[]>("/api/marketplace/updates");
}

function listMarketplaceAgentVersions(agentId: string) {
  return request<MarketplaceAgentVersionRecord[]>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/versions`,
  );
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

function listMarketplaceReviewQueue(status: MarketplaceReviewStatus = "pending_review") {
  const query = new URLSearchParams();
  query.set("status", status);
  return request<MarketplaceReviewQueueItem[]>(
    `/api/marketplace/admin/review-queue?${query.toString()}`,
  );
}

function claimMarketplaceReview(agentId: string, claim = true) {
  return fetchApi(`/api/marketplace/admin/review-queue/${encodeURIComponent(agentId)}/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim }),
  }).then(async (response) => {
    if (!response.ok && response.status !== 204) {
      const detail = (await response.text()).trim();
      throw new Error(detail || `Failed to ${claim ? "claim" : "unclaim"} review.`);
    }
  });
}

function approveMarketplaceAgent(agentId: string) {
  return request<SubmitMarketplaceAgentResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/approve`,
    {
      method: "POST",
    },
  );
}

function rejectMarketplaceAgent(agentId: string, reason: string) {
  return request<SubmitMarketplaceAgentResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    },
  );
}

function publishMarketplaceAgent(body: PublishMarketplaceAgentRequest) {
  return request<PublishMarketplaceAgentResponse>("/api/marketplace/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      definition: body.definition,
      metadata: body.metadata || {},
    }),
  });
}

function submitMarketplaceAgent(agentId: string) {
  return request<SubmitMarketplaceAgentResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/submit`,
    {
      method: "POST",
    },
  );
}

function reviseMarketplaceAgent(agentId: string, body: ReviseMarketplaceAgentRequest) {
  return request<ReviseMarketplaceAgentResponse>(
    `/api/marketplace/agents/${encodeURIComponent(agentId)}/revise`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        definition: body.definition,
        changelog: body.changelog || "",
      }),
    },
  );
}

function listMarketplaceNotifications(unreadOnly = false, limit = 50) {
  const query = new URLSearchParams();
  query.set("unread_only", unreadOnly ? "true" : "false");
  query.set("limit", String(limit));
  return request<MarketplaceNotificationRecord[]>(
    `/api/marketplace/notifications?${query.toString()}`,
  );
}

function getMarketplaceNotificationUnreadCount() {
  return request<{ count: number }>("/api/marketplace/notifications/unread-count");
}

function markMarketplaceNotificationRead(notificationId: string) {
  return fetchApi(`/api/marketplace/notifications/${encodeURIComponent(notificationId)}/read`, {
    method: "POST",
  }).then(async (response) => {
    if (!response.ok && response.status !== 204) {
      const detail = (await response.text()).trim();
      throw new Error(detail || "Failed to mark notification as read.");
    }
  });
}

function markAllMarketplaceNotificationsRead() {
  return fetchApi("/api/marketplace/notifications/read-all", {
    method: "POST",
  }).then(async (response) => {
    if (!response.ok && response.status !== 204) {
      const detail = (await response.text()).trim();
      throw new Error(detail || "Failed to mark all notifications as read.");
    }
  });
}

export {
  approveMarketplaceAgent,
  applyMarketplaceUpdate,
  checkMarketplaceUpdates,
  claimMarketplaceReview,
  getMarketplaceAgent,
  getMarketplaceAgentReviews,
  listMarketplaceAgentVersions,
  getMarketplaceNotificationUnreadCount,
  installMarketplaceAgent,
  preflightMarketplaceAgentInstall,
  listConnectorCatalog,
  listMarketplaceNotifications,
  listMarketplaceAgents,
  listMarketplaceReviewQueue,
  markAllMarketplaceNotificationsRead,
  markMarketplaceNotificationRead,
  publishMarketplaceAgent,
  rejectMarketplaceAgent,
  reviseMarketplaceAgent,
  submitMarketplaceAgent,
  uninstallMarketplaceAgent,
};

export type {
  ConnectorCatalogRecord,
  MarketplaceNotificationRecord,
  MarketplaceReviewQueueItem,
  MarketplaceReviewStatus,
  PublishMarketplaceAgentRequest,
  PublishMarketplaceAgentResponse,
  ReviseMarketplaceAgentRequest,
  ReviseMarketplaceAgentResponse,
  MarketplaceAgentUpdateRecord,
  MarketplaceAgentVersionRecord,
  MarketplaceAgentDetail,
  MarketplaceApplyUpdateResponse,
  MarketplaceAgentInstallResponse,
  MarketplaceAgentInstallPreflightResponse,
  MarketplaceAgentReview,
  MarketplaceAgentSummary,
};
