import type { ChatAttachment } from "../../types";

type AgentMode = "ask" | "rag" | "company_agent" | "deep_search" | "brain";
type AccessMode = "restricted" | "full_access";
type MindmapMapType = "structure" | "evidence" | "work_graph" | "context_mindmap";

type ConversationMindmapSettings = {
  enabled: boolean;
  maxDepth: number;
  includeReasoningMap: boolean;
  mapType: MindmapMapType;
};

type SendMessageOptions = {
  citationMode?: string;
  useMindmap?: boolean;
  mindmapSettings?: Record<string, unknown>;
  mindmapFocus?: Record<string, unknown>;
  settingOverrides?: Record<string, unknown>;
  agentMode?: AgentMode;
  agentId?: string;
  accessMode?: AccessMode;
};

const MINDMAP_SETTINGS_STORAGE_KEY = "maia.conversation-mindmap-settings";

const DEEP_SEARCH_SETTING_OVERRIDES: Record<string, unknown> = {
  __deep_search_enabled: true,
  __llm_only_keyword_generation: true,
  __llm_only_keyword_generation_strict: true,
  __deep_search_max_source_ids: 350,
  __research_depth_tier: "deep_research",
  __research_web_search_budget: 350,
  __research_max_query_variants: 14,
  __research_results_per_query: 25,
  __research_fused_top_k: 220,
  __research_min_unique_sources: 80,
  __research_source_budget_min: 80,
  __research_source_budget_max: 200,
  __file_research_source_budget_min: 120,
  __file_research_source_budget_max: 220,
  __file_research_max_sources: 220,
  __file_research_max_chunks: 1800,
  __file_research_max_scan_pages: 200,
};

const RAG_SETTING_OVERRIDES: Record<string, unknown> = {
  __rag_mode_enabled: true,
  __disable_auto_web_fallback: true,
};

function normalizeMindmapMapType(raw: unknown): MindmapMapType {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "context_mindmap") {
    return "context_mindmap";
  }
  if (value === "work_graph") {
    return "work_graph";
  }
  if (value === "evidence") {
    return "evidence";
  }
  return "structure";
}

function readStringList(value: unknown, limit = 8): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows = value.map((item) => String(item || "").trim()).filter((item) => item.length > 0);
  return Array.from(new Set(rows)).slice(0, Math.max(1, limit));
}

export {
  DEEP_SEARCH_SETTING_OVERRIDES,
  MINDMAP_SETTINGS_STORAGE_KEY,
  RAG_SETTING_OVERRIDES,
  normalizeMindmapMapType,
  readStringList,
};
export type {
  AccessMode,
  AgentMode,
  ChatAttachment,
  ConversationMindmapSettings,
  MindmapMapType,
  SendMessageOptions,
};
