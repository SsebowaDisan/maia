import { useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Loader2, Search, Sparkles, Store, X } from "lucide-react";
import { toast } from "sonner";

import {
  installMarketplaceAgent,
  listAgents,
  listMarketplaceAgents,
  type MarketplaceAgentSummary,
} from "../../../api/client";

type WorkflowSelectableAgent = {
  id: string;
  agentId: string;
  name: string;
  description: string;
  tags: string[];
  triggerFamily: string;
  version: string;
  isInstalled: boolean;
  requiredConnectors: string[];
};

type AgentPickerPanelProps = {
  open: boolean;
  preferredAgentId?: string | null;
  onClose: () => void;
  onSelectAgent: (agent: WorkflowSelectableAgent) => void;
};

export function normalizeAgentRow(
  row: MarketplaceAgentSummary,
  installedIds: Set<string>,
): WorkflowSelectableAgent {
  const candidate = row as MarketplaceAgentSummary & {
    is_installed?: boolean;
    trigger_family?: string;
  };
  const agentId = String(candidate.agent_id || "").trim();
  const explicitInstalled = Boolean(candidate.is_installed);
  const isInstalled = explicitInstalled || installedIds.has(agentId);
  return {
    id: String(candidate.id || agentId).trim() || agentId,
    agentId,
    name: String(candidate.name || agentId || "Untitled agent").trim(),
    description: String(candidate.description || "").trim(),
    tags: Array.isArray(candidate.tags)
      ? candidate.tags.map((tag) => String(tag || "").trim()).filter(Boolean)
      : [],
    triggerFamily: String(candidate.trigger_family || "").trim().toLowerCase(),
    version: String(candidate.version || "").trim(),
    isInstalled,
    requiredConnectors: Array.isArray(candidate.required_connectors)
      ? candidate.required_connectors.map((c) => String(c || "").trim()).filter(Boolean)
      : [],
  };
}

function matchesSearch(agent: WorkflowSelectableAgent, query: string): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return (
    agent.name.toLowerCase().includes(q) ||
    agent.description.toLowerCase().includes(q) ||
    agent.tags.some((tag) => tag.toLowerCase().includes(q))
  );
}

function sortAgents(
  rows: WorkflowSelectableAgent[],
  preferredAgentId: string,
): WorkflowSelectableAgent[] {
  const preferred = preferredAgentId.toLowerCase();
  return [...rows].sort((a, b) => {
    const aP = a.agentId.toLowerCase() === preferred;
    const bP = b.agentId.toLowerCase() === preferred;
    if (aP && !bP) return -1;
    if (!aP && bP) return 1;
    return a.name.localeCompare(b.name);
  });
}

function agentMonogram(name: string): string {
  const t = String(name || "").trim();
  return t ? t.charAt(0).toUpperCase() : "A";
}

function AgentRow({
  agent,
  busy,
  preferred,
  onAddInstalled,
  onInstallAndAdd,
}: {
  agent: WorkflowSelectableAgent;
  busy: boolean;
  preferred: boolean;
  onAddInstalled: (agent: WorkflowSelectableAgent) => void;
  onInstallAndAdd: (agent: WorkflowSelectableAgent) => void;
}) {
  const installed = agent.isInstalled;
  const monogram = agentMonogram(agent.name);
  const triggerLabel = agent.triggerFamily === "scheduled" ? "Scheduled" : "On demand";
  const tags = Array.isArray(agent.tags) ? agent.tags.slice(0, 4) : [];

  return (
    <article
      className={`flex h-full flex-col rounded-2xl border p-4 transition-shadow hover:shadow-[0_6px_20px_-8px_rgba(15,23,42,0.2)] ${
        preferred
          ? "border-[#bfc8d6] bg-[#f8fafc] ring-1 ring-[#dbe3ef]"
          : "border-black/[0.08] bg-white"
      }`}
    >
      {/* Top row: monogram + name + status badge */}
      <div className="flex items-start gap-3">
        <div className="inline-flex aspect-square w-11 shrink-0 items-center justify-center rounded-xl border border-black/[0.08] bg-gradient-to-br from-[#f8fafc] to-[#eef2f7] text-[15px] font-bold text-[#344054] shadow-sm">
          {monogram}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className="text-[14px] font-semibold leading-snug text-[#101828]">{agent.name}</p>
            <span
              className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                installed
                  ? "border border-[#bbf7d0] bg-[#ecfdf3] text-[#166534]"
                  : "border border-black/[0.12] bg-white text-[#475467]"
              }`}
            >
              {installed ? <CheckCircle2 size={10} /> : null}
              {installed ? "Installed" : "Available"}
            </span>
          </div>
          {agent.version ? (
            <p className="mt-0.5 text-[11px] text-[#98a2b3]">v{agent.version}</p>
          ) : null}
        </div>
      </div>

      {/* Description — 3 lines */}
      <p className="mt-3 line-clamp-3 text-[12px] leading-[1.6] text-[#475467]">
        {agent.description || "No description provided."}
      </p>

      {/* Tags row */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        <span className="rounded-full border border-black/[0.1] bg-[#f8fafc] px-2 py-0.5 text-[10px] font-medium text-[#475467]">
          {triggerLabel}
        </span>
        {tags.map((tag) => (
          <span
            key={`${agent.id}:${tag}`}
            className="rounded-full border border-black/[0.08] bg-[#f0f4ff] px-2 py-0.5 text-[10px] font-medium text-[#3b5bdb]"
          >
            {tag}
          </span>
        ))}
      </div>

      {/* Spacer pushes CTA to the bottom of every card uniformly */}
      <div className="flex-1" />

      {/* CTA */}
      <div className="mt-4">
        {installed ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => onAddInstalled(agent)}
            className="w-full rounded-full bg-[#7c3aed] px-3 py-2.5 text-[12px] font-semibold text-white transition-colors hover:bg-[#6d28d9] disabled:opacity-55"
          >
            Add to workflow
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => onInstallAndAdd(agent)}
            className="w-full rounded-full border border-black/[0.14] bg-white px-3 py-2.5 text-[12px] font-semibold text-[#344054] transition-colors hover:bg-[#f8fafc] disabled:opacity-55"
          >
            {busy ? (
              <span className="inline-flex items-center justify-center gap-1.5">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Installing…
              </span>
            ) : (
              "Install and add"
            )}
          </button>
        )}
      </div>
    </article>
  );
}

export function AgentPickerPanel({
  open,
  preferredAgentId = null,
  onClose,
  onSelectAgent,
}: AgentPickerPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [agents, setAgents] = useState<WorkflowSelectableAgent[]>([]);
  const [installingAgentId, setInstallingAgentId] = useState("");
  const [loadKey, setLoadKey] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);

  // Load agents when opened
  useEffect(() => {
    if (!open) return;
    let disposed = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [catalogRows, installedRows] = await Promise.all([
          listMarketplaceAgents({ sort_by: "installs", limit: 100 }),
          listAgents().catch(() => []),
        ]);
        const installedIds = new Set(
          (installedRows || [])
            .map((row) => String(row.agent_id || "").trim())
            .filter(Boolean),
        );
        const normalized = (catalogRows || [])
          .map((row) => normalizeAgentRow(row, installedIds))
          .filter((row) => row.agentId);
        if (!disposed) setAgents(normalized);
      } catch (err) {
        if (!disposed) {
          const raw = String(err || "");
          const isConnErr =
            raw.includes("Unable to reach") ||
            raw.includes("Failed to fetch") ||
            raw.includes("NetworkError");
          setError(
            isConnErr
              ? "Could not connect to the server. Make sure the API is running and try again."
              : raw || "Failed to load agents.",
          );
        }
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    void load();
    return () => { disposed = true; };
  }, [open, loadKey]);

  // Focus search on open
  useEffect(() => {
    if (open) {
      setTimeout(() => searchRef.current?.focus(), 60);
    } else {
      setSearchQuery("");
    }
  }, [open]);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const filteredAgents = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return agents.filter((a) => matchesSearch(a, q));
  }, [agents, searchQuery]);

  const installedAgents = useMemo(
    () => sortAgents(filteredAgents.filter((a) => a.isInstalled), String(preferredAgentId || "")),
    [filteredAgents, preferredAgentId],
  );
  const availableAgents = useMemo(
    () => sortAgents(filteredAgents.filter((a) => !a.isInstalled), String(preferredAgentId || "")),
    [filteredAgents, preferredAgentId],
  );

  const handleInstallAndAdd = async (agent: WorkflowSelectableAgent) => {
    setInstallingAgentId(agent.agentId);
    try {
      const result = await installMarketplaceAgent(agent.agentId, {
        version: agent.version || null,
        connector_mapping: {},
        gate_policies: {},
      });
      if (!result.success) {
        const missing = Array.isArray(result.missing_connectors) ? result.missing_connectors : [];
        toast.error(
          missing.length
            ? `Missing connectors: ${missing.join(", ")}`
            : result.error || "Install failed.",
        );
        return;
      }
      setAgents((prev) =>
        prev.map((row) => (row.agentId === agent.agentId ? { ...row, isInstalled: true } : row)),
      );
      onSelectAgent({ ...agent, isInstalled: true });
    } catch (err) {
      toast.error(`Install failed: ${String(err)}`);
    } finally {
      setInstallingAgentId("");
    }
  };

  if (!open) return null;

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-200"
      style={{ background: "rgba(15, 23, 42, 0.38)", animation: "fadeIn 200ms ease-out" }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Dialog */}
      <div
        className="relative flex w-[820px] max-h-[88vh] flex-col overflow-hidden rounded-[24px] border border-black/[0.08] bg-white shadow-[0_32px_72px_-20px_rgba(15,23,42,0.5)]"
        style={{ animation: "scaleIn 200ms ease-out" }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="shrink-0 border-b border-black/[0.06] bg-[#fcfcfd] px-5 pt-5 pb-4">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl border border-black/[0.08] bg-white shadow-sm">
                <Store className="h-4 w-4 text-[#344054]" />
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                  Marketplace
                </p>
                <p className="text-[15px] font-semibold leading-tight text-[#101828]">
                  Add an agent step
                </p>
              </div>
            </div>
            <button
              type="button"
              tabIndex={-1}
              onMouseDown={(e) => e.preventDefault()}
              onClick={onClose}
              className="rounded-full border border-black/[0.08] p-1.5 text-[#667085] transition-colors hover:bg-[#f2f4f7] hover:text-[#344054]"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          {/* Search */}
          <label className="mt-3.5 flex items-center gap-2 rounded-xl border border-black/[0.12] bg-white px-3 py-2 focus-within:border-black/[0.25]">
            <Search className="h-4 w-4 shrink-0 text-[#98a2b3]" />
            <input
              ref={searchRef}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search agents by name, description, or tag…"
              className="w-full bg-transparent text-[13px] text-[#101828] outline-none placeholder:text-[#98a2b3]"
            />
            {searchQuery ? (
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setSearchQuery("")}
                className="shrink-0 text-[#98a2b3] hover:text-[#475467]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </label>
        </div>

        {/* Scrollable body */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-none px-5 py-4">
          {loading ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-[#667085]">
              <Loader2 className="h-5 w-5 animate-spin" />
              <p className="text-[12px]">Loading agents…</p>
            </div>
          ) : null}

          {!loading && error ? (
            <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-4 py-3 text-[12px] text-[#b42318]">
              <p>{error}</p>
              <button
                type="button"
                onClick={() => setLoadKey((k) => k + 1)}
                className="mt-2 rounded-full border border-[#fca5a5] bg-white px-3 py-1 text-[11px] font-semibold hover:bg-[#fff1f2]"
              >
                Retry
              </button>
            </div>
          ) : null}

          {!loading && !error ? (
            <div className="space-y-5">
              {/* Installed / Your agents */}
              <section>
                <div className="mb-2.5 flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#667085]">
                    Your agents
                  </h4>
                  <span className="text-[11px] text-[#98a2b3]">{installedAgents.length}</span>
                </div>
                <div className="grid auto-rows-fr grid-cols-3 gap-3">
                  {installedAgents.length ? (
                    installedAgents.map((agent) => (
                      <AgentRow
                        key={`installed:${agent.id}`}
                        agent={agent}
                        busy={installingAgentId === agent.agentId}
                        preferred={agent.agentId === preferredAgentId}
                        onAddInstalled={onSelectAgent}
                        onInstallAndAdd={handleInstallAndAdd}
                      />
                    ))
                  ) : (
                    <p className="col-span-3 rounded-xl border border-dashed border-black/[0.12] bg-[#f8fafc] px-4 py-3 text-[12px] text-[#667085]">
                      {searchQuery
                        ? "No installed agents match this search."
                        : "You have no agents installed yet. Browse the marketplace below."}
                    </p>
                  )}
                </div>
              </section>

              {/* Marketplace / Available */}
              <section>
                <div className="mb-2.5 flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#667085]">
                    Available in marketplace
                  </h4>
                  <span className="text-[11px] text-[#98a2b3]">{availableAgents.length}</span>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  {availableAgents.length ? (
                    availableAgents.map((agent) => (
                      <AgentRow
                        key={`available:${agent.id}`}
                        agent={agent}
                        busy={installingAgentId === agent.agentId}
                        preferred={agent.agentId === preferredAgentId}
                        onAddInstalled={onSelectAgent}
                        onInstallAndAdd={handleInstallAndAdd}
                      />
                    ))
                  ) : (
                    <p className="col-span-3 rounded-xl border border-dashed border-black/[0.12] bg-[#f8fafc] px-4 py-3 text-[12px] text-[#667085]">
                      No available agents match this search.
                    </p>
                  )}
                </div>
              </section>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-black/[0.06] bg-[#fcfcfd] px-5 py-3">
          <p className="inline-flex items-center gap-1.5 text-[11px] text-[#98a2b3]">
            <Sparkles className="h-3 w-3" />
            Install and add to your workflow in one step.
          </p>
        </div>
      </div>
    </div>
  );
}

export type { AgentPickerPanelProps, WorkflowSelectableAgent };
