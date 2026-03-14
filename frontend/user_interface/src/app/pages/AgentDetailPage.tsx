import { useMemo, useState } from "react";
import { toast } from "sonner";

import { AgentRunHistory } from "../components/agents/AgentRunHistory";
import { ImprovementSuggestion } from "../components/agents/ImprovementSuggestion";
import { AGENT_OS_AGENTS, AGENT_OS_RUNS } from "./agentOsData";
import { AgentBuilderPage } from "./AgentBuilderPage";

type AgentDetailPageProps = {
  agentId: string;
};

type AgentDetailTab = "builder" | "history" | "improvement";

export function AgentDetailPage({ agentId }: AgentDetailPageProps) {
  const [activeTab, setActiveTab] = useState<AgentDetailTab>("builder");
  const agent = useMemo(
    () => AGENT_OS_AGENTS.find((entry) => entry.id === agentId) || null,
    [agentId],
  );
  const runs = useMemo(() => AGENT_OS_RUNS.filter((run) => run.agentId === agentId), [agentId]);

  if (!agent) {
    return (
      <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
        <div className="mx-auto max-w-[1000px] rounded-2xl border border-black/[0.08] bg-white p-5">
          <h1 className="text-[24px] font-semibold text-[#101828]">Agent not found</h1>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1300px] space-y-4">
        <section className="rounded-[28px] border border-black/[0.08] bg-white px-6 py-5">
          <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">Agent detail</p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">{agent.name}</h1>
          <p className="mt-2 text-[15px] text-[#475467]">{agent.description}</p>
          <div className="mt-4 flex gap-2">
            {(["builder", "history", "improvement"] as const).map((tab) => (
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
          </div>
        </section>

        {activeTab === "builder" ? <AgentBuilderPage /> : null}
        {activeTab === "history" ? (
          <AgentRunHistory
            runs={runs}
            onOpenReplay={(runId) => toast.message(`Opening replay for ${runId}`)}
          />
        ) : null}
        {activeTab === "improvement" ? (
          <ImprovementSuggestion
            feedbackCount={12}
            currentPrompt="Write concise summaries with evidence links."
            suggestedPrompt="Write concise summaries with explicit risk markers, confidence notes, and next-step options."
            onApply={() => toast.success("Suggestion applied to draft prompt.")}
            onDismiss={() => toast.message("Suggestion dismissed.")}
          />
        ) : null}
      </div>
    </div>
  );
}

