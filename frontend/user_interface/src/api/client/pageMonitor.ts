import { fetchApi, request } from "./core";

type MonitoredUrlRecord = {
  url: string;
  content_hash?: string | null;
  last_fetched_at?: string | null;
};

type ChangeRecord = {
  url: string;
  changed: boolean;
};

function listMonitoredUrls(agentId: string) {
  return request<MonitoredUrlRecord[]>(
    `/api/page-monitor/${encodeURIComponent(agentId)}/urls`,
  );
}

function addMonitoredUrl(agentId: string, url: string) {
  return request<{ url: string; id: string }>(
    `/api/page-monitor/${encodeURIComponent(agentId)}/urls`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    },
  );
}

async function removeMonitoredUrl(agentId: string, url: string) {
  const response = await fetchApi(
    `/api/page-monitor/${encodeURIComponent(agentId)}/urls`,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    },
  );
  if (response.ok || response.status === 204) {
    return;
  }
  const detail = (await response.text()).trim();
  throw new Error(detail || `Failed to remove URL: ${response.status}`);
}

function refreshMonitoredUrls(agentId: string) {
  return request<{ refreshed: number; changes: ChangeRecord[] }>(
    `/api/page-monitor/${encodeURIComponent(agentId)}/urls/refresh`,
    {
      method: "POST",
    },
  );
}

export {
  addMonitoredUrl,
  listMonitoredUrls,
  refreshMonitoredUrls,
  removeMonitoredUrl,
};

export type { ChangeRecord, MonitoredUrlRecord };
