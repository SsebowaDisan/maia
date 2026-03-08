const CHAT_MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024;
const CHAT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024;

const WEB_SEARCH_SETTING_OVERRIDES: Record<string, unknown> = {
  __deep_search_enabled: true,
  __research_web_only: true,
  __llm_only_keyword_generation: true,
  __llm_only_keyword_generation_strict: true,
  __research_depth_tier: "deep_research",
  __research_web_search_budget: 200,
  __research_max_query_variants: 12,
  __research_results_per_query: 20,
  __research_fused_top_k: 200,
  __research_min_unique_sources: 60,
  __research_max_live_inspections: 12,
  __deep_search_max_source_ids: 200,
};

type ComposerMode = "ask" | "company_agent" | "deep_search" | "web_search";

export {
  CHAT_MAX_FILE_SIZE_BYTES,
  CHAT_MAX_TOTAL_BYTES,
  WEB_SEARCH_SETTING_OVERRIDES,
};
export type { ComposerMode };
