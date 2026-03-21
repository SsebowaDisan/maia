import { useEffect, useMemo, useState } from "react";

import {
  getMarketplaceAgent,
  installMarketplaceAgent,
  listConnectorCatalog,
  type ConnectorCatalogRecord,
  type MarketplaceAgentDetail,
} from "../../../api/client";
import { ConnectorBrandIcon } from "../../components/connectors/ConnectorBrandIcon";
import { resolveAgentIconConnectorId } from "../../utils/agentIconResolver";

type HubAgentDetailPageProps = {
  slug: string;
  onNavigate: (path: string) => void;
};

function buildAgentChatPath(agentId: string): string {
  const params = new URLSearchParams();
  params.set("agent", agentId);
  return `/?${params.toString()}`;
}

export function HubAgentDetailPage({ slug, onNavigate }: HubAgentDetailPageProps) {
  const [loading, setLoading] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<MarketplaceAgentDetail | null>(null);
  const [connectorCatalog, setConnectorCatalog] = useState<ConnectorCatalogRecord[]>([]);
  const [installed, setInstalled] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [agent, catalog] = await Promise.all([
          getMarketplaceAgent(slug),
          listConnectorCatalog(),
        ]);
        setDetail(agent);
        setConnectorCatalog(catalog || []);
        setInstalled(Boolean(agent.is_installed));
      } catch (nextError) {
        setError(String(nextError || "Failed to load agent."));
      } finally {
        setLoading(false);
      }
    };
    if (!slug) {
      setError("Missing agent slug.");
      setLoading(false);
      return;
    }
    void load();
  }, [slug]);

  const connectorNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of connectorCatalog) {
      map.set(String(row.id || "").trim(), String(row.name || "").trim());
    }
    return map;
  }, [connectorCatalog]);

  const headerIconConnectorId = useMemo(
    () =>
      resolveAgentIconConnectorId({
        required_connectors: detail?.required_connectors,
        connector_status: detail?.connector_status,
        has_computer_use: detail?.has_computer_use,
        category: detail?.category,
        tags: detail?.tags,
      }),
    [
      detail?.category,
      detail?.connector_status,
      detail?.has_computer_use,
      detail?.required_connectors,
      detail?.tags,
    ],
  );

  const installAgent = async () => {
    if (!detail?.agent_id) {
      return;
    }
    setInstalling(true);
    setError("");
    try {
      const result = await installMarketplaceAgent(detail.agent_id, {
        connector_mapping: {},
        gate_policies: {},
      });
      if (!result.success) {
        throw new Error(result.error || "Install failed.");
      }
      setInstalled(true);
      onNavigate(buildAgentChatPath(detail.agent_id));
    } catch (nextError) {
      setError(String(nextError || "Install failed."));
    } finally {
      setInstalling(false);
    }
  };

  if (loading) {
    return <p className="text-[14px] text-[#64748b]">Loading agent details...</p>;
  }
  if (error) {
    return <p className="text-[14px] text-[#b42318]">{error}</p>;
  }
  if (!detail) {
    return <p className="text-[14px] text-[#64748b]">Agent not found.</p>;
  }

  const readme = String(detail.readme_md || detail.description || "").trim();

  return (
    <div className="grid gap-6 lg:grid-cols-[1.6fr_0.8fr]">
      <section className="rounded-[24px] border border-black/[0.08] bg-white p-6 shadow-[0_16px_34px_rgba(15,23,42,0.08)]">
        <button
          type="button"
          onClick={() => onNavigate("/marketplace")}
          className="text-[12px] font-semibold text-[#667085] hover:text-[#111827]"
        >
          Back to Marketplace
        </button>
        <div className="mt-4 flex items-center gap-3">
          <ConnectorBrandIcon connectorId={headerIconConnectorId} label={detail.name} size={30} />
          <div>
            <h1 className="text-[28px] font-semibold tracking-[-0.03em] text-[#0f172a]">{detail.name}</h1>
            <button
              type="button"
              onClick={() => {
                if (detail.creator_username) {
                  onNavigate(`/creators/${encodeURIComponent(detail.creator_username)}`);
                }
              }}
              className="text-[13px] text-[#475467] hover:text-[#0f172a]"
            >
              {detail.creator_display_name || detail.creator_username || "Community creator"}
            </button>
          </div>
        </div>

        <div className="mt-6 space-y-4 rounded-2xl border border-black/[0.08] bg-[#f8fafc] p-4">
          <h2 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-[#64748b]">Overview</h2>
          <p className="whitespace-pre-wrap text-[14px] leading-6 text-[#334155]">
            {readme || detail.description || "No overview yet."}
          </p>
        </div>
      </section>

      <aside className="space-y-4">
        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-[#64748b]">Install</p>
          <button
            type="button"
            onClick={installAgent}
            disabled={installing || installed}
            className={`mt-3 h-10 w-full rounded-xl text-[13px] font-semibold transition ${
              installed
                ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                : "bg-[#111827] text-white hover:bg-[#0b1220] disabled:opacity-60"
            }`}
          >
            {installed ? "Installed" : installing ? "Installing..." : "Install"}
          </button>
          {installed ? (
            <button
              type="button"
              onClick={() => onNavigate(buildAgentChatPath(detail.agent_id))}
              className="mt-2 w-full text-[12px] font-semibold text-[#334155] hover:text-[#0f172a]"
            >
              Open in Chat
            </button>
          ) : null}
        </div>

        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-[#64748b]">Details</p>
          <div className="mt-2 space-y-2 text-[13px] text-[#334155]">
            <p>Version: {detail.version || "1.0.0"}</p>
            <p>Installs: {detail.install_count || 0}</p>
            <p>Rating: {Number(detail.avg_rating || 0).toFixed(1)} / 5</p>
            <p>Success rate: {Math.round(Number(detail.run_success_rate || 0) * 100)}%</p>
          </div>
        </div>

        <div className="rounded-[22px] border border-black/[0.08] bg-white p-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.1em] text-[#64748b]">Required connectors</p>
          <div className="mt-2 space-y-2">
            {(detail.required_connectors || []).length ? (
              detail.required_connectors.map((connectorId) => (
                <div
                  key={connectorId}
                  className="flex items-center gap-2 rounded-lg border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#334155]"
                >
                  <ConnectorBrandIcon connectorId={connectorId} label={connectorId} size={16} />
                  {connectorNameById.get(connectorId) || connectorId}
                </div>
              ))
            ) : (
              <p className="text-[12px] text-[#667085]">No connector setup required.</p>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}
