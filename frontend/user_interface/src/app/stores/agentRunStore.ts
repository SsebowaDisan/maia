import { create } from "zustand";

type AgentRunSnapshot = {
  runId: string | null;
  agentId: string | null;
  toolId: string | null;
  stage: string | null;
  eventType: string | null;
  updatedAt: number | null;
};

type AgentRunStoreState = AgentRunSnapshot & {
  setSnapshot: (snapshot: Partial<AgentRunSnapshot>) => void;
  clear: () => void;
  hydrateFromActivityEvent: (event: Record<string, unknown> | null | undefined) => void;
};

function normalizeStage(eventType: string): string {
  const normalized = String(eventType || "").trim().toLowerCase();
  if (!normalized) {
    return "execution";
  }
  if (normalized.includes("plan") || normalized.includes("preflight")) {
    return "planning";
  }
  if (normalized.includes("verify") || normalized.includes("approval") || normalized.includes("handoff")) {
    return "verification";
  }
  if (normalized.includes("deliver") || normalized.includes("completed")) {
    return "delivery";
  }
  if (normalized.includes("error") || normalized.includes("failed")) {
    return "error";
  }
  return "execution";
}

const emptySnapshot: AgentRunSnapshot = {
  runId: null,
  agentId: null,
  toolId: null,
  stage: null,
  eventType: null,
  updatedAt: null,
};

const useAgentRunStore = create<AgentRunStoreState>()((set) => ({
  ...emptySnapshot,
  setSnapshot: (snapshot) =>
    set((state) => ({
      ...state,
      ...snapshot,
      updatedAt: Date.now(),
    })),
  clear: () => set({ ...emptySnapshot }),
  hydrateFromActivityEvent: (event) => {
    const row = event || {};
    const data = (row["data"] as Record<string, unknown> | undefined) || {};
    const metadata = (row["metadata"] as Record<string, unknown> | undefined) || {};
    const eventType = String(row["event_type"] || row["type"] || "").trim();
    const runId = String(
      row["run_id"] || data["run_id"] || metadata["run_id"] || "",
    ).trim();
    const agentId = String(
      row["agent_id"] || metadata["agent_id"] || data["agent_id"] || "",
    ).trim();
    const toolId = String(
      data["tool_id"] || metadata["tool_id"] || row["title"] || "",
    ).trim();
    set((state) => ({
      ...state,
      runId: runId || state.runId,
      agentId: agentId || state.agentId,
      toolId: toolId || state.toolId,
      stage: normalizeStage(eventType),
      eventType: eventType || state.eventType,
      updatedAt: Date.now(),
    }));
  },
}));

export { useAgentRunStore };
export type { AgentRunSnapshot };

