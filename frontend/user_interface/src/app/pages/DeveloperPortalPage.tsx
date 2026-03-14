import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getSettings,
  listAgentApiRuns,
  listAgents,
  patchSettings,
  type AgentApiRunRecord,
  type AgentSummaryRecord,
} from "../../api/client";

function resolveRunStatus(run: AgentApiRunRecord): string {
  return String(run.status || "unknown").trim().toLowerCase();
}

function resolveRunCost(run: AgentApiRunRecord): number {
  const value = Number(run.llm_cost_usd ?? run.cost_usd ?? Number.NaN);
  return Number.isFinite(value) ? value : 0;
}

function maskSecret(value: string): string {
  const normalized = String(value || "").trim();
  if (!normalized) {
    return "";
  }
  if (normalized.length <= 6) {
    return "••••••";
  }
  return `${normalized.slice(0, 3)}••••••${normalized.slice(-3)}`;
}

export function DeveloperPortalPage() {
  const [releaseVersion, setReleaseVersion] = useState("1.3.0");
  const [releaseNotes, setReleaseNotes] = useState("Improved tool routing and cleaner evidence summaries.");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agents, setAgents] = useState<AgentSummaryRecord[]>([]);
  const [runs, setRuns] = useState<AgentApiRunRecord[]>([]);
  const [developerApiKeyInput, setDeveloperApiKeyInput] = useState("");
  const [developerApiKeySaved, setDeveloperApiKeySaved] = useState("");
  const [savingApiKey, setSavingApiKey] = useState(false);

  const loadPortalData = async () => {
    setLoading(true);
    setError("");
    try {
      const [agentRows, runRows, settings] = await Promise.all([
        listAgents(),
        listAgentApiRuns({ limit: 400 }),
        getSettings(),
      ]);
      setAgents(agentRows || []);
      setRuns(runRows || []);
      const savedApiKey = String(settings?.values?.["developer.api_key"] || "").trim();
      setDeveloperApiKeySaved(savedApiKey);
      setDeveloperApiKeyInput(savedApiKey);
    } catch (nextError) {
      setError(String(nextError || "Failed to load developer portal."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPortalData();
  }, []);

  const metrics = useMemo(() => {
    const successCount = runs.filter((run) => {
      const status = resolveRunStatus(run);
      return status === "completed" || status === "success";
    }).length;
    const successRate = runs.length ? (successCount / runs.length) * 100 : 0;
    const totalCost = runs.reduce((total, run) => total + resolveRunCost(run), 0);
    const avgCost = runs.length ? totalCost / runs.length : 0;
    return {
      publishedAgents: agents.length,
      totalRuns: runs.length,
      successRate,
      totalCost,
      avgCost,
    };
  }, [agents.length, runs]);

  const agentRows = useMemo(
    () =>
      agents.map((agent) => {
        const relatedRuns = runs.filter((run) => String(run.agent_id || "").trim() === agent.agent_id);
        const lastRun = relatedRuns[0];
        return {
          agentId: agent.agent_id,
          name: agent.name,
          version: agent.version,
          runCount: relatedRuns.length,
          lastStatus: resolveRunStatus(lastRun || {}),
        };
      }),
    [agents, runs],
  );

  const saveDeveloperApiKey = async (nextInput?: string) => {
    setSavingApiKey(true);
    try {
      const nextValue = String((nextInput ?? developerApiKeyInput) || "").trim();
      const updated = await patchSettings({ "developer.api_key": nextValue });
      const saved = String(updated?.values?.["developer.api_key"] || "").trim();
      setDeveloperApiKeySaved(saved);
      setDeveloperApiKeyInput(saved);
      toast.success(saved ? "Developer API key saved." : "Developer API key cleared.");
    } catch (nextError) {
      toast.error(`Failed to save API key: ${String(nextError)}`);
    } finally {
      setSavingApiKey(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
            Developer portal
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
            Publisher operations
          </h1>
          <p className="mt-2 text-[15px] text-[#475467]">
            Track your agent portfolio, release updates, and monitor run performance.
          </p>
        </section>

        {error ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {error}
          </section>
        ) : null}
        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            Loading developer portal...
          </section>
        ) : null}

        <section className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Published agents</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{metrics.publishedAgents}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Total runs</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{metrics.totalRuns.toLocaleString()}</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Success rate</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">{metrics.successRate.toFixed(1)}%</p>
          </article>
          <article className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <p className="text-[12px] text-[#667085]">Average run cost</p>
            <p className="mt-1 text-[26px] font-semibold text-[#111827]">${metrics.avgCost.toFixed(3)}</p>
          </article>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Agent performance</h2>
          <div className="mt-3 space-y-2">
            {agentRows.length === 0 ? (
              <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
                No published agents yet.
              </p>
            ) : (
              agentRows.map((agent) => (
                <div key={agent.agentId} className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[13px] font-semibold text-[#111827]">{agent.name}</p>
                    <span className="rounded-full border border-black/[0.1] bg-white px-2 py-0.5 text-[11px] text-[#344054]">
                      v{agent.version}
                    </span>
                  </div>
                  <p className="mt-1 text-[12px] text-[#667085]">
                    Runs: {agent.runCount} · Last status: {agent.lastStatus || "unknown"}
                  </p>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Developer API key</h2>
          <p className="mt-1 text-[13px] text-[#667085]">
            Use this key for publishing automation and SDK integrations.
          </p>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_auto]">
            <input
              value={developerApiKeyInput}
              onChange={(event) => setDeveloperApiKeyInput(event.target.value)}
              placeholder="Enter developer API key"
              className="rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
            />
            <button
              type="button"
              onClick={() => {
                void saveDeveloperApiKey();
              }}
              disabled={savingApiKey}
              className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white disabled:opacity-60"
            >
              {savingApiKey ? "Saving..." : "Save"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDeveloperApiKeyInput("");
                void saveDeveloperApiKey("");
              }}
              disabled={savingApiKey && !developerApiKeySaved}
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              Clear
            </button>
          </div>
          {developerApiKeySaved ? (
            <p className="mt-2 text-[12px] text-[#667085]">
              Saved key: <span className="font-semibold text-[#344054]">{maskSecret(developerApiKeySaved)}</span>
            </p>
          ) : null}
        </section>

        <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
          <h2 className="text-[18px] font-semibold text-[#111827]">Publish new version</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <label>
              <span className="text-[12px] font-semibold text-[#667085]">Version</span>
              <input
                value={releaseVersion}
                onChange={(event) => setReleaseVersion(event.target.value)}
                className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
              />
            </label>
            <label>
              <span className="text-[12px] font-semibold text-[#667085]">Release notes</span>
              <input
                value={releaseNotes}
                onChange={(event) => setReleaseNotes(event.target.value)}
                className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => toast.success(`Submitted ${releaseVersion} for review.`)}
              className="rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white"
            >
              Submit for review
            </button>
            <a
              href="/developer/docs"
              className="rounded-full border border-black/[0.12] bg-white px-4 py-2 text-[12px] font-semibold text-[#344054]"
            >
              Open SDK docs
            </a>
          </div>
        </section>
      </div>
    </div>
  );
}
