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

function normalizeStage(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  return normalized.replace(/[^\w-]+/g, "_");
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
    const explicitStage = normalizeStage(
      row["stage"] || data["stage"] || metadata["stage"] || row["event_family"] || data["event_family"],
    );
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
      stage: explicitStage || (String(eventType || "").toLowerCase().includes("error") ? "error" : "execution"),
      eventType: eventType || state.eventType,
      updatedAt: Date.now(),
    }));
  },
}));

export { useAgentRunStore };
export type { AgentRunSnapshot };
