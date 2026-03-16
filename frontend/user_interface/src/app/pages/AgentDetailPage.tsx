import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import {
  getAgent,
  getImprovementSuggestion,
  listAgentRuns,
  recordFeedback,
  updateAgent,
  type AgentDefinitionInput,
  type AgentDefinitionRecord,
  type ImprovementSuggestionRecord,
} from "../../api/client";
import { AgentRunHistory, type AgentRunHistoryRecord } from "../components/agents/AgentRunHistory";
import { ImprovementSuggestion } from "../components/agents/ImprovementSuggestion";

type AgentDetailPageProps = {
  agentId: string;
  initialTab?: AgentDetailTab;
};

type AgentDetailTab = "overview" | "history" | "improvement";

function mapRunToUi(run: {
  run_id: string;
  agent_id: string;
  status: string;
  trigger_type: string;
  started_at: string;
  ended_at?: string | null;
  error?: string | null;
  result_summary?: string | null;
}): AgentRunHistoryRecord {
  const startedAt = String(run.started_at || new Date().toISOString());
  const endedAt = run.ended_at || null;
  const startMs = new Date(startedAt).getTime();
  const endMs = endedAt ? new Date(endedAt).getTime() : Date.now();
  const durationMs = Number.isFinite(startMs) && Number.isFinite(endMs) && endMs >= startMs ? endMs - startMs : 0;
  return {
    runId: String(run.run_id || ""),
    agentId: String(run.agent_id || ""),
    triggerType: String(run.trigger_type || "manual"),
    status: String(run.status || "unknown"),
    durationMs,
    llmCostUsd: 0,
    startedAt,
    outputSummary: String(run.result_summary || "No summary available."),
    errorMessage: String(run.error || ""),
  };
}

export function AgentDetailPage({ agentId, initialTab = "overview" }: AgentDetailPageProps) {
  const [activeTab, setActiveTab] = useState<AgentDetailTab>(initialTab);
  const [agentDetail, setAgentDetail] = useState<AgentDefinitionRecord | null>(null);
  const [runs, setRuns] = useState<AgentRunHistoryRecord[]>([]);
  const [suggestion, setSuggestion] = useState<ImprovementSuggestionRecord | null>(null);
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [suggestionDismissed, setSuggestionDismissed] = useState(false);
  const [applyingSuggestion, setApplyingSuggestion] = useState(false);
  const [suggestionRefreshNonce, setSuggestionRefreshNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab, agentId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [agent, runRows] = await Promise.all([getAgent(agentId), listAgentRuns(agentId)]);
        setAgentDetail(agent);
        setRuns((runRows || []).map(mapRunToUi));
      } catch (nextError) {
        setError(String(nextError));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [agentId]);

  useEffect(() => {
    if (activeTab !== "improvement" || suggestionDismissed) {
      return;
    }
    let cancelled = false;
    const loadSuggestion = async () => {
      setSuggestionLoading(true);
      setSuggestionError("");
      try {
        const row = await getImprovementSuggestion(agentId);
        if (cancelled) {
          return;
        }
        setSuggestion(row);
      } catch (nextError) {
        if (cancelled) {
          return;
        }
        setSuggestion(null);
        setSuggestionError(String(nextError || "No suggestion available yet."));
      } finally {
        if (!cancelled) {
          setSuggestionLoading(false);
        }
      }
    };
    void loadSuggestion();
    return () => {
      cancelled = true;
    };
  }, [activeTab, agentId, suggestionDismissed, suggestionRefreshNonce]);

  const definitionPreview = useMemo(
    () => JSON.stringify(agentDetail?.definition || {}, null, 2),
    [agentDetail?.definition],
  );

  if (loading) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-black/[0.08] bg-white p-5 text-[14px] text-[#667085]">
          Loading agent details...
        </div>
      </div>
    );
  }

  if (error || !agentDetail) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1080px] rounded-2xl border border-[#fecaca] bg-[#fff1f2] p-5">
          <h1 className="text-[24px] font-semibold text-[#9f1239]">Agent not found</h1>
          <p className="mt-2 text-[13px] text-[#b42318]">{error || "No agent data returned."}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_20px_54px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Agent detail</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agentDetail.name}</h1>
          <p className="mt-2 text-[14px] text-[#475467]">
            Agent ID: <span className="font-semibold text-[#111827]">{agentDetail.agent_id}</span> · Version{" "}
            <span className="font-semibold text-[#111827]">{agentDetail.version}</span>
          </p>
          <div className="mt-4 flex gap-2">
            {(["overview", "history", "improvement"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`rounded-full px-3 py-1.5 text-[12px] font-semibold capitalize ${
                  activeTab === tab ? "bg-[#111827] text-white" : "border border-black/[0.12] bg-white text-[#344054]"
                }`}
              >
                {tab}
              </button>
            ))}
            <a
              href="/agent-builder"
              className="rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[12px] font-semibold text-[#344054]"
            >
              Open builder
            </a>
          </div>
        </section>

        {activeTab === "overview" ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
            <h2 className="text-[18px] font-semibold text-[#111827]">Definition</h2>
            <pre className="mt-3 overflow-x-auto rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] text-[#344054]">
              <code>{definitionPreview}</code>
            </pre>
          </section>
        ) : null}

        {activeTab === "history" ? (
          <AgentRunHistory
            runs={runs}
            onOpenReplay={(runId) => toast.message(`Opening replay for ${runId}`)}
            onSubmitFeedback={async ({ runId, feedbackType, originalOutput, correctedOutput }) => {
              await recordFeedback(agentId, runId, originalOutput, correctedOutput, feedbackType);
              toast.success("Feedback saved.");
              if (activeTab === "improvement") {
                setSuggestionDismissed(false);
              }
            }}
          />
        ) : null}

        {activeTab === "improvement" ? (
          <ImprovementSuggestion
            feedbackCount={suggestion?.feedback_count || 0}
            currentPrompt={String((agentDetail.definition as { system_prompt?: string })?.system_prompt || "")}
            suggestedPrompt={suggestion?.suggested_prompt || ""}
            reasoning={suggestion?.reasoning || ""}
            loading={suggestionLoading || applyingSuggestion}
            error={suggestionError}
            onApply={async () => {
              if (!agentDetail || !suggestion?.suggested_prompt) {
                toast.error("No suggestion available to apply.");
                return;
              }
              setApplyingSuggestion(true);
              try {
                const currentDefinition = (agentDetail.definition || {}) as Record<string, unknown>;
                const payload: AgentDefinitionInput = {
                  ...(currentDefinition as AgentDefinitionInput),
                  id: String(currentDefinition.id || agentDetail.agent_id || ""),
                  name: String(currentDefinition.name || agentDetail.name || agentDetail.agent_id),
                  system_prompt: suggestion.suggested_prompt,
                };
                await updateAgent(agentId, payload);
                const refreshed = await getAgent(agentId);
                setAgentDetail(refreshed);
                toast.success("Improvement suggestion applied.");
              } catch (nextError) {
                toast.error(`Failed to apply suggestion: ${String(nextError)}`);
              } finally {
                setApplyingSuggestion(false);
              }
            }}
            onRefresh={() => {
              setSuggestionDismissed(false);
              setSuggestion(null);
              setSuggestionError("");
              setSuggestionRefreshNonce((previous) => previous + 1);
            }}
            onDismiss={() => {
              setSuggestionDismissed(true);
              setSuggestion(null);
              setSuggestionError("");
            }}
          />
        ) : null}
      </div>
    </div>
  );
}
