import { useCallback, useEffect, useMemo, useState } from "react";
import { Globe, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";

import {
  addMonitoredUrl,
  listMonitoredUrls,
  refreshMonitoredUrls,
  removeMonitoredUrl,
  type ChangeRecord,
  type MonitoredUrlRecord,
} from "../../../api/client";

type PageMonitorPanelProps = {
  agentId: string;
};

function isValidHttpsUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "Never fetched";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Never fetched";
  }
  return date.toLocaleString();
}

function hashPreview(value?: string | null): string {
  const hash = String(value || "").trim();
  if (!hash) {
    return "—";
  }
  if (hash.length <= 12) {
    return hash;
  }
  return `${hash.slice(0, 12)}...`;
}

export function PageMonitorPanel({ agentId }: PageMonitorPanelProps) {
  const [rows, setRows] = useState<MonitoredUrlRecord[]>([]);
  const [newUrl, setNewUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [removingUrl, setRemovingUrl] = useState("");
  const [error, setError] = useState("");
  const [changes, setChanges] = useState<ChangeRecord[]>([]);

  const load = useCallback(async () => {
    if (!agentId) {
      setRows([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const nextRows = await listMonitoredUrls(agentId);
      setRows(Array.isArray(nextRows) ? nextRows : []);
    } catch (nextError) {
      setError(String(nextError || "Failed to load monitored URLs."));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const changedUrls = useMemo(
    () => changes.filter((entry) => Boolean(entry.changed)).map((entry) => entry.url),
    [changes],
  );

  const handleAdd = async () => {
    const candidate = String(newUrl || "").trim();
    if (!candidate) {
      setError("Enter an HTTPS URL.");
      return;
    }
    if (!isValidHttpsUrl(candidate)) {
      setError("Only valid HTTPS URLs are allowed.");
      return;
    }
    setAdding(true);
    setError("");
    try {
      await addMonitoredUrl(agentId, candidate);
      setNewUrl("");
      setChanges([]);
      await load();
    } catch (nextError) {
      setError(String(nextError || "Failed to add URL."));
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (url: string) => {
    if (!window.confirm(`Remove monitored URL?\n\n${url}`)) {
      return;
    }
    setRemovingUrl(url);
    setError("");
    try {
      await removeMonitoredUrl(agentId, url);
      setChanges((previous) => previous.filter((entry) => entry.url !== url));
      await load();
    } catch (nextError) {
      setError(String(nextError || "Failed to remove URL."));
    } finally {
      setRemovingUrl("");
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError("");
    try {
      const result = await refreshMonitoredUrls(agentId);
      setChanges(Array.isArray(result?.changes) ? result.changes : []);
      await load();
    } catch (nextError) {
      setError(String(nextError || "Failed to refresh monitored URLs."));
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-[18px] font-semibold text-[#111827]">Monitored URLs</h2>
          <p className="mt-1 text-[13px] text-[#667085]">
            Track competitor pages and detect meaningful content changes.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleRefresh()}
          disabled={refreshing || loading}
          className="inline-flex items-center gap-2 rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054] disabled:opacity-50"
        >
          {refreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Check now
        </button>
      </div>

      <div className="mt-3 rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3">
        <label className="block text-[12px] font-semibold uppercase tracking-[0.08em] text-[#667085]">
          Add URL
        </label>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            value={newUrl}
            onChange={(event) => setNewUrl(event.target.value)}
            placeholder="https://example.com/pricing"
            className="min-w-[220px] flex-1 rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[13px] text-[#111827] focus:border-black/[0.28] focus:outline-none"
          />
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={adding}
            className="inline-flex items-center gap-2 rounded-full bg-[#111827] px-3.5 py-2 text-[12px] font-semibold text-white disabled:opacity-50"
          >
            {adding ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            Add URL
          </button>
        </div>
      </div>

      {changedUrls.length ? (
        <div className="mt-3 rounded-xl border border-[#bbf7d0] bg-[#ecfdf3] px-3 py-2.5">
          <p className="text-[12px] font-semibold text-[#166534]">
            Changes detected in {changedUrls.length} URL{changedUrls.length === 1 ? "" : "s"}:
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[12px] text-[#166534]">
            {changedUrls.map((url) => (
              <li key={url}>{url}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="mt-3 rounded-xl border border-black/[0.08] bg-white px-3 py-3 text-[13px] text-[#667085]">
          Loading monitored URLs...
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-3 rounded-xl border border-dashed border-black/[0.16] bg-white px-3 py-6 text-center">
          <Globe size={16} className="mx-auto text-[#98a2b3]" />
          <p className="mt-2 text-[13px] font-semibold text-[#344054]">
            No monitored URLs configured
          </p>
          <p className="mt-1 text-[12px] text-[#667085]">
            Add your first competitor page to start monitoring.
          </p>
        </div>
      ) : (
        <div className="mt-3 overflow-hidden rounded-xl border border-black/[0.08] bg-white">
          <table className="min-w-full text-left text-[12px] text-[#475467]">
            <thead className="bg-[#f8fafc] text-[#667085]">
              <tr>
                <th className="px-3 py-2 font-semibold">URL</th>
                <th className="px-3 py-2 font-semibold">Last fetched</th>
                <th className="px-3 py-2 font-semibold">Hash</th>
                <th className="px-3 py-2 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const busy = removingUrl === row.url;
                return (
                  <tr key={row.url} className="border-t border-black/[0.06]">
                    <td className="px-3 py-2.5">
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noreferrer"
                        className="line-clamp-1 text-[#1d4ed8] hover:underline"
                      >
                        {row.url}
                      </a>
                    </td>
                    <td className="px-3 py-2.5">{formatDate(row.last_fetched_at)}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px]">{hashPreview(row.content_hash)}</td>
                    <td className="px-3 py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => void handleRemove(row.url)}
                        disabled={busy}
                        className="inline-flex items-center gap-1 rounded-full border border-[#fda4af] bg-[#fff1f2] px-2.5 py-1 text-[11px] font-semibold text-[#9f1239] disabled:opacity-50"
                      >
                        {busy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
