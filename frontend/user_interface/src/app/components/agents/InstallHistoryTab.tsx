import { useEffect, useState } from "react";

import { listAgentInstallHistory, type AgentInstallHistoryRecord } from "../../../api/client";

type InstallHistoryTabProps = {
  agentId: string;
};

function formatTimestamp(value: number): string {
  const ms = Number(value || 0) * 1000;
  if (!Number.isFinite(ms) || ms <= 0) {
    return "Unknown time";
  }
  return new Date(ms).toLocaleString();
}

export function InstallHistoryTab({ agentId }: InstallHistoryTabProps) {
  const [rows, setRows] = useState<AgentInstallHistoryRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!agentId) {
        setRows([]);
        return;
      }
      setLoading(true);
      setError("");
      try {
        const historyRows = await listAgentInstallHistory(agentId, { limit: 100 });
        if (!cancelled) {
          setRows(Array.isArray(historyRows) ? historyRows : []);
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(String(nextError || "Failed to load install history."));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [agentId]);

  if (loading) {
    return (
      <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
        <h2 className="text-[16px] font-semibold text-[#111827]">Install history</h2>
        <p className="mt-3 text-[13px] text-[#667085]">Loading install events...</p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-5">
      <h2 className="text-[16px] font-semibold text-[#111827]">Install history</h2>
      <p className="mt-1 text-[12px] text-[#667085]">
        Audit trail of installs and updates for this agent.
      </p>

      {error ? (
        <p className="mt-3 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#9f1239]">
          {error}
        </p>
      ) : null}

      {rows.length ? (
        <ol className="mt-4 space-y-3">
          {rows.map((row) => {
            const connectorEntries = Object.entries(row.connector_mapping || {});
            return (
              <li key={row.id} className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[#667085]">
                    {formatTimestamp(row.timestamp)}
                  </p>
                  <span className="rounded-full border border-[#d0d5dd] bg-white px-2 py-0.5 text-[11px] font-semibold text-[#344054]">
                    v{row.version}
                  </span>
                </div>
                <p className="mt-2 text-[13px] text-[#344054]">User: {row.user_id || "Unknown"}</p>
                {connectorEntries.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {connectorEntries.map(([requiredId, mappedId]) => (
                      <span
                        key={`${row.id}:${requiredId}:${mappedId}`}
                        className="rounded-full border border-[#c4b5fd] bg-[#f5f3ff] px-2 py-0.5 text-[11px] font-semibold text-[#7c3aed]"
                      >
                        {requiredId} {"->"} {mappedId}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 text-[12px] text-[#667085]">No connector mapping details recorded.</p>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="mt-3 rounded-xl border border-dashed border-black/[0.1] bg-[#f9fafb] px-3 py-2 text-[13px] text-[#667085]">
          No install history yet.
        </p>
      )}
    </section>
  );
}
