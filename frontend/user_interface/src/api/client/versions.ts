/**
 * API client for the version history + promote endpoints.
 */
import { request } from "./core";

type VersionRecord = {
  id: string;
  resource_type: string;
  resource_id: string;
  tenant_id: string;
  version: string;
  environment: string;
  definition_json: string;
  created_by: string;
  created_at: number;
  changelog: string;
  is_latest: boolean;
};

async function listVersions(
  resourceType: string,
  resourceId: string,
  environment?: string,
): Promise<VersionRecord[]> {
  const qs = environment ? `?environment=${encodeURIComponent(environment)}` : "";
  return request<VersionRecord[]>(`/api/versions/${resourceType}/${resourceId}${qs}`);
}

async function getVersion(
  resourceType: string,
  resourceId: string,
  version: string,
): Promise<VersionRecord> {
  return request<VersionRecord>(`/api/versions/${resourceType}/${resourceId}/${version}`);
}

async function promote(
  resourceType: string,
  resourceId: string,
  fromEnv: string,
  toEnv: string,
): Promise<VersionRecord> {
  return request<VersionRecord>(`/api/versions/${resourceType}/${resourceId}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ from_env: fromEnv, to_env: toEnv }),
  });
}

async function rollback(
  resourceType: string,
  resourceId: string,
  version: string,
  environment: string,
): Promise<VersionRecord> {
  return request<VersionRecord>(`/api/versions/${resourceType}/${resourceId}/rollback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version, environment }),
  });
}

export type { VersionRecord };
export { listVersions, getVersion, promote, rollback };
