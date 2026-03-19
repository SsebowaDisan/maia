import { fetchApi, request } from "./core";

type CreatorProfileRecord = {
  id: string;
  user_id?: string;
  username: string;
  display_name: string;
  bio: string;
  avatar_url: string;
  website_url: string;
  github_url: string;
  twitter_url: string;
  follower_count: number;
  total_installs: number;
  published_agent_count: number;
  published_team_count: number;
  is_following?: boolean;
  exists?: boolean;
  date_created?: string | null;
  date_updated?: string | null;
};

type CreatorProfileCreateRequest = {
  username: string;
  display_name?: string;
  bio?: string;
  website_url?: string;
  github_url?: string;
  twitter_url?: string;
};

type CreatorProfileUpdateRequest = {
  display_name?: string;
  bio?: string;
  avatar_url?: string;
  website_url?: string;
  github_url?: string;
  twitter_url?: string;
};

type CreatorSimpleRecord = {
  user_id: string;
  username: string;
  display_name: string;
  avatar_url: string;
  date_created?: string | null;
};

type CreatorStatsResponse = {
  total_installs: number;
  published_agent_count: number;
  published_team_count: number;
  follower_count?: number;
  top_agents: Array<Record<string, unknown>>;
  top_teams: Array<Record<string, unknown>>;
};

type WorkflowAgentLineupRecord = {
  agent_id: string;
  step_id?: string;
  description?: string;
  step_type?: string;
};

type MarketplaceWorkflowRecord = {
  id: string;
  slug: string;
  creator_id: string;
  creator_username?: string;
  creator_display_name?: string;
  creator_avatar_url?: string;
  name: string;
  description: string;
  readme_md: string;
  definition?: Record<string, unknown>;
  agent_lineup: WorkflowAgentLineupRecord[];
  required_connectors: string[];
  screenshots: string[];
  tags: string[];
  category: string;
  version: string;
  status: string;
  install_count: number;
  avg_rating: number;
  review_count: number;
  date_created?: string | null;
  date_updated?: string | null;
};

type PublishMarketplaceWorkflowRequest = {
  source_workflow_id: string;
  name: string;
  description?: string;
  readme_md?: string;
  definition: Record<string, unknown>;
  category?: string;
  tags?: string[];
  screenshots?: string[];
};

type InstallMarketplaceWorkflowResponse = {
  installed: boolean;
  already_installed?: boolean;
  workflow_id: string;
  missing_connectors: string[];
  auto_mapped_agents?: Record<string, string>;
  redirect_path?: string;
  name?: string;
  agent_count?: number;
};

type ExploreCategoryRecord = {
  id: string;
  label: string;
  agents: Array<Record<string, unknown>>;
};

type ExploreHomeResponse = {
  trending_agents: Array<Record<string, unknown>>;
  trending_teams: MarketplaceWorkflowRecord[];
  new_agents: Array<Record<string, unknown>>;
  new_teams: MarketplaceWorkflowRecord[];
  categories: ExploreCategoryRecord[];
  featured_creators: CreatorProfileRecord[];
};

type ExploreSearchResponse = {
  query: string;
  agents: Array<Record<string, unknown>>;
  teams: MarketplaceWorkflowRecord[];
  creators: CreatorProfileRecord[];
};

type HubReviewRecord = {
  id: string;
  rating: number;
  review_text?: string;
  publisher_response?: string | null;
  created_at?: string | number | null;
};

function getCreatorProfile(username: string) {
  return request<CreatorProfileRecord>(`/api/creators/${encodeURIComponent(username)}`);
}

function getMyCreatorProfile() {
  return request<CreatorProfileRecord & { exists?: boolean }>("/api/creators/me");
}

function getMyCreatorStats() {
  return request<CreatorStatsResponse>("/api/creators/me/stats");
}

function createMyCreatorProfile(body: CreatorProfileCreateRequest) {
  return request<CreatorProfileRecord>("/api/creators/me", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function updateMyCreatorProfile(body: CreatorProfileUpdateRequest) {
  return request<CreatorProfileRecord>("/api/creators/me", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function uploadMyCreatorAvatar(file: File) {
  const formData = new FormData();
  formData.append("avatar", file);
  const response = await fetchApi("/api/creators/me/avatar", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    const detail = (await response.text()).trim();
    throw new Error(detail || "Failed to upload avatar.");
  }
  return (await response.json()) as {
    avatar_url: string;
    profile: CreatorProfileRecord;
  };
}

function listCreatorAgents(username: string) {
  return request<Array<Record<string, unknown>>>(`/api/creators/${encodeURIComponent(username)}/agents`);
}

function listCreatorTeams(username: string, limit = 50) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<MarketplaceWorkflowRecord[]>(
    `/api/creators/${encodeURIComponent(username)}/teams?${query.toString()}`,
  );
}

function listCreatorActivity(username: string, limit = 30) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<Array<Record<string, unknown>>>(
    `/api/creators/${encodeURIComponent(username)}/activity?${query.toString()}`,
  );
}

function followCreator(username: string) {
  return request<{ status: string; username: string }>(
    `/api/creators/${encodeURIComponent(username)}/follow`,
    { method: "POST" },
  );
}

function unfollowCreator(username: string) {
  return request<{ status: string; username: string }>(
    `/api/creators/${encodeURIComponent(username)}/follow`,
    { method: "DELETE" },
  );
}

function listCreatorFollowers(username: string, limit = 50) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<CreatorSimpleRecord[]>(
    `/api/creators/${encodeURIComponent(username)}/followers?${query.toString()}`,
  );
}

function listMyFollowing(limit = 100) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<CreatorSimpleRecord[]>(`/api/creators/me/following?${query.toString()}`);
}

function listMyFeed(limit = 30) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<Array<Record<string, unknown>>>(`/api/feed?${query.toString()}`);
}

function listMarketplaceWorkflows(params?: {
  q?: string;
  category?: string;
  sort?: "popular" | "newest" | "trending" | string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.q) {
    query.set("q", params.q);
  }
  if (params?.category) {
    query.set("category", params.category);
  }
  if (params?.sort) {
    query.set("sort", params.sort);
  }
  if (typeof params?.limit === "number") {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<MarketplaceWorkflowRecord[]>(`/api/marketplace/workflows${suffix}`);
}

function getMarketplaceWorkflow(slug: string) {
  return request<MarketplaceWorkflowRecord>(`/api/marketplace/workflows/${encodeURIComponent(slug)}`);
}

function listRelatedMarketplaceWorkflows(slug: string, limit = 6) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<MarketplaceWorkflowRecord[]>(
    `/api/marketplace/workflows/${encodeURIComponent(slug)}/related?${query.toString()}`,
  );
}

function publishMarketplaceWorkflow(body: PublishMarketplaceWorkflowRequest) {
  return request<MarketplaceWorkflowRecord>("/api/marketplace/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_workflow_id: body.source_workflow_id,
      name: body.name,
      description: body.description || "",
      readme_md: body.readme_md || "",
      definition: body.definition || {},
      category: body.category || "other",
      tags: body.tags || [],
      screenshots: body.screenshots || [],
    }),
  });
}

function installMarketplaceWorkflow(slug: string) {
  return request<InstallMarketplaceWorkflowResponse>(
    `/api/marketplace/workflows/${encodeURIComponent(slug)}/install`,
    { method: "POST" },
  );
}

function listMarketplaceWorkflowReviews(slug: string, limit = 20) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<HubReviewRecord[]>(
    `/api/marketplace/workflows/${encodeURIComponent(slug)}/reviews?${query.toString()}`,
  );
}

function submitMarketplaceWorkflowReview(slug: string, body: { rating: number; review_text?: string }) {
  return request<HubReviewRecord>(`/api/marketplace/workflows/${encodeURIComponent(slug)}/reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      rating: body.rating,
      review_text: body.review_text || "",
    }),
  });
}

function getExploreHome(limit = 8) {
  const query = new URLSearchParams();
  query.set("limit", String(limit));
  return request<ExploreHomeResponse>(`/api/explore?${query.toString()}`);
}

function searchExplore(params: { q: string; type?: "all" | "agents" | "teams" | "creators"; limit?: number }) {
  const query = new URLSearchParams();
  query.set("q", params.q || "");
  query.set("type", params.type || "all");
  query.set("limit", String(params.limit || 20));
  return request<ExploreSearchResponse>(`/api/explore/search?${query.toString()}`);
}

export {
  createMyCreatorProfile,
  followCreator,
  getCreatorProfile,
  getExploreHome,
  getMarketplaceWorkflow,
  getMyCreatorProfile,
  getMyCreatorStats,
  installMarketplaceWorkflow,
  listCreatorActivity,
  listCreatorAgents,
  listCreatorFollowers,
  listCreatorTeams,
  listMarketplaceWorkflowReviews,
  listMarketplaceWorkflows,
  listMyFeed,
  listMyFollowing,
  listRelatedMarketplaceWorkflows,
  publishMarketplaceWorkflow,
  searchExplore,
  submitMarketplaceWorkflowReview,
  unfollowCreator,
  updateMyCreatorProfile,
  uploadMyCreatorAvatar,
};

export type {
  CreatorProfileCreateRequest,
  CreatorProfileRecord,
  CreatorProfileUpdateRequest,
  CreatorSimpleRecord,
  CreatorStatsResponse,
  ExploreCategoryRecord,
  ExploreHomeResponse,
  ExploreSearchResponse,
  HubReviewRecord,
  InstallMarketplaceWorkflowResponse,
  MarketplaceWorkflowRecord,
  PublishMarketplaceWorkflowRequest,
  WorkflowAgentLineupRecord,
};
