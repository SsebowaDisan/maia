import { request } from "./core";

type DeveloperStatus = "none" | "pending" | "verified" | "trusted_publisher" | "rejected";

type DeveloperStatusResponse = {
  status: DeveloperStatus;
  motivation?: string | null;
  rejection_reason?: string | null;
};

type ApplyRequest = {
  motivation: string;
  intended_agent_types?: string;
  agreed_to_guidelines: boolean;
};

type ApplyResponse = {
  status: string;
  message: string;
};

type DeveloperApplicationRecord = {
  user_id: string;
  status: DeveloperStatus;
  motivation: string;
  intended_agent_types: string;
  rejection_reason?: string | null;
  reviewed_by?: string | null;
  date_created?: string | null;
};

type AdminActionResponse = {
  status: string;
  user_id: string;
};

function getDeveloperStatus() {
  return request<DeveloperStatusResponse>("/api/developers/me");
}

function applyForDeveloper(body: ApplyRequest) {
  return request<ApplyResponse>("/api/developers/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function listDeveloperApplications(statusFilter?: string) {
  const query = new URLSearchParams();
  if (statusFilter) {
    query.set("status_filter", statusFilter);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DeveloperApplicationRecord[]>(
    `/api/developers/admin/applications${suffix}`,
  );
}

function approveDeveloper(userId: string) {
  return request<AdminActionResponse>(
    `/api/developers/admin/${encodeURIComponent(userId)}/approve`,
    { method: "POST" },
  );
}

function rejectDeveloper(userId: string, reason: string) {
  return request<AdminActionResponse>(
    `/api/developers/admin/${encodeURIComponent(userId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    },
  );
}

function promoteDeveloper(userId: string) {
  return request<AdminActionResponse>(
    `/api/developers/admin/${encodeURIComponent(userId)}/promote`,
    { method: "POST" },
  );
}

export {
  applyForDeveloper,
  approveDeveloper,
  getDeveloperStatus,
  listDeveloperApplications,
  promoteDeveloper,
  rejectDeveloper,
};

export type {
  AdminActionResponse,
  ApplyRequest,
  ApplyResponse,
  DeveloperApplicationRecord,
  DeveloperStatus,
  DeveloperStatusResponse,
};
