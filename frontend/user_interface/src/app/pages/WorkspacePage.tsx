import { useMemo, useState } from "react";
import { toast } from "sonner";

import { AgentRunHistory } from "../components/agents/AgentRunHistory";
import { MemoryExplorer } from "../components/agents/MemoryExplorer";
import { WorkspaceSidebar } from "../components/workspace/WorkspaceSidebar";
import { UpdateBanner } from "../components/workspace/UpdateBanner";
import { AGENT_OS_AGENTS, AGENT_OS_CONNECTORS, AGENT_OS_RUNS, formatRelativeTime } from "./agentOsData";

export function WorkspacePage() {
  const [selectedConnectorId, setSelectedConnectorId] = useState<string | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);
  const [episodes, setEpisodes] = useState([
    { id: "ep_1", summary: "Drafted healthcare proposal for Acme account", createdAt: "2026-03-13T10:42:00Z" },
    { id: "ep_2", summary: "Summarized pipeline stage transitions for sales standup", createdAt: "2026-03-13T09:15:00Z" },
  ]);

  const updatesAvailable = 3;
  const activeConnector = AGENT_OS_CONNECTORS.find((connector) => connector.id === selectedConnectorId) || null;
  const connectorHint = activeConnector
    ? `${activeConnector.name} selected from workspace sidebar.`
    : "Select a connector from the sidebar for quick context.";

  const runsByAgent = useMemo(
    () =>
      AGENT_OS_AGENTS.map((agent) => ({
        agent,
        runs: AGENT_OS_RUNS.filter((run) => run.agentId === agent.id),
      })),
    [],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto flex max-w-[1360px] gap-4">
        <WorkspaceSidebar
          connectors={AGENT_OS_CONNECTORS}
          agents={AGENT_OS_AGENTS}
          onOpenConnector={setSelectedConnectorId}
        />

        <div className="min-w-0 flex-1 space-y-4">
          <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Workspace</p>
            <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">Agent operations dashboard</h1>
            <p className="mt-2 text-[15px] text-[#475467]">{connectorHint}</p>
          </section>

          {!bannerDismissed ? (
            <UpdateBanner
              totalUpdates={updatesAvailable}
              onOpenUpdates={() => toast.message("Update review panel will open in the marketplace phase.")}
              onDismiss={() => setBannerDismissed(true)}
            />
          ) : null}

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {runsByAgent.map(({ agent, runs }) => (
              <article
                key={agent.id}
                className="rounded-2xl border border-black/[0.08] bg-white p-4 shadow-[0_14px_36px_rgba(15,23,42,0.08)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                    <p className="mt-1 text-[13px] text-[#667085]">{agent.description}</p>
                    <p className="mt-1 text-[12px] text-[#98a2b3]">
                      Last run {formatRelativeTime(agent.lastRun)} · {agent.totalRuns} total runs
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      agent.status === "active"
                        ? "bg-[#ecfdf3] text-[#166534]"
                        : agent.status === "paused"
                          ? "bg-[#fff7ed] text-[#9a3412]"
                          : "bg-[#fff1f2] text-[#b91c1c]"
                    }`}
                  >
                    {agent.status}
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => toast.success(`Started run for ${agent.name}.`)}
                    className="rounded-full bg-[#111827] px-3 py-1.5 text-[12px] font-semibold text-white"
                  >
                    Run manually
                  </button>
                  <a
                    href={`/agents/${encodeURIComponent(agent.id)}`}
                    className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
                  >
                    Edit
                  </a>
                </div>
                <div className="mt-3 space-y-1 text-[12px] text-[#667085]">
                  {runs.slice(0, 2).map((run) => (
                    <p key={run.id}>
                      {run.id}: {run.status} · ${(run.llmCostUsd || 0).toFixed(2)}
                    </p>
                  ))}
                </div>
              </article>
            ))}
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <AgentRunHistory
              runs={AGENT_OS_RUNS}
              onOpenReplay={(runId) => toast.message(`Opening theatre replay for ${runId}.`)}
            />
            <MemoryExplorer
              episodes={episodes}
              onDeleteEpisode={(episodeId) =>
                setEpisodes((previous) => previous.filter((episode) => episode.id !== episodeId))
              }
            />
          </section>
        </div>
      </div>
    </div>
  );
}

