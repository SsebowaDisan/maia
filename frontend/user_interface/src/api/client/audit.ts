/**
 * API client for the audit trail endpoints.
 */
import { fetchApi, request } from "./core";

type AuditEvent = {
  id: string;
  timestamp: number;
  tenant_id: string;
  user_id: string;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: string;
  ip_address: string;
  metadata_json: string;
};

type AuditQueryParams = {
  action?: string;
  user_id?: string;
  resource_type?: string;
  since?: number;
  until?: number;
  limit?: number;
  offset?: number;
};

type AuditStats = {
  period_start: number;
  period_end: number;
  counts_by_action: Record<string, number>;
  total: number;
};

async function queryAuditEvents(params: AuditQueryParams = {}): Promise<AuditEvent[]> {
  const query = new URLSearchParams();
  if (params.action) query.set("action", params.action);
  if (params.user_id) query.set("user_id", params.user_id);
  if (params.resource_type) query.set("resource_type", params.resource_type);
  if (params.since != null) query.set("since", String(params.since));
  if (params.until != null) query.set("until", String(params.until));
  if (params.limit != null) query.set("limit", String(params.limit));
  if (params.offset != null) query.set("offset", String(params.offset));
  const qs = query.toString();
  return request<AuditEvent[]>(`/api/audit/events${qs ? `?${qs}` : ""}`);
}

async function getAuditStats(): Promise<AuditStats> {
  return request<AuditStats>("/api/audit/events/stats");
}

async function exportAuditNdjson(params: { since?: number; until?: number } = {}): Promise<Response> {
  const query = new URLSearchParams();
  if (params.since != null) query.set("since", String(params.since));
  if (params.until != null) query.set("until", String(params.until));
  const qs = query.toString();
  return fetchApi(`/api/audit/events/export${qs ? `?${qs}` : ""}`);
}

export type { AuditEvent, AuditQueryParams, AuditStats };
export { queryAuditEvents, getAuditStats, exportAuditNdjson };
