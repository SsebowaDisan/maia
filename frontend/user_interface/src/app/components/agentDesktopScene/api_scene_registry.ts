import type { ApiSceneState } from "./api_scene_state";
import type { ConnectorCloneSceneVariant } from "./scenes/ConnectorCloneScene";

type ApiSceneKind = "generic" | "clone";

type ApiSceneRegistryResult =
  | { kind: "generic" }
  | { kind: "clone"; variant: ConnectorCloneSceneVariant };

function normalizeTokens(state: ApiSceneState): Set<string> {
  const raw = [
    state.connectorId,
    state.connectorLabel,
    state.brandSlug,
    state.sceneFamily,
    state.operationLabel,
  ]
    .map((value) => String(value || "").trim().toLowerCase())
    .filter(Boolean);
  return new Set(raw);
}

function hasAny(tokens: Set<string>, values: string[]): boolean {
  return values.some((value) => tokens.has(value));
}

function hasContains(tokens: Set<string>, values: string[]): boolean {
  const rows = Array.from(tokens);
  return rows.some((token) => values.some((value) => token.includes(value)));
}

// Metadata-driven scene variant resolution — uses brand_slug and scene_family
// from event data instead of token heuristics.
const BRAND_SLUG_TO_VARIANT: Record<string, ConnectorCloneSceneVariant> = {
  gmail: "gmail",
  slack: "slack",
  sap: "sap",
  excel: "excel",
  outlook: "outlook",
  google_sheets: "sheets",
  microsoft_calendar: "outlook",
  onedrive: "outlook",
  word: "outlook",
  teams: "slack",
};

const SCENE_FAMILY_FALLBACK: Record<string, ConnectorCloneSceneVariant> = {
  email: "gmail",
  sheet: "sheets",
  chat: "slack",
  commerce: "sap",
};

function resolveCloneVariant(state: ApiSceneState): ConnectorCloneSceneVariant | null {
  // Priority 1: Use brand_slug from event metadata
  const slug = (state.brandSlug || "").trim().toLowerCase();
  if (slug && BRAND_SLUG_TO_VARIANT[slug]) {
    return BRAND_SLUG_TO_VARIANT[slug];
  }

  // Priority 2: Use scene_family from event metadata
  const family = (state.sceneFamily || "").trim().toLowerCase();
  if (family && SCENE_FAMILY_FALLBACK[family]) {
    return SCENE_FAMILY_FALLBACK[family];
  }

  // Priority 3: Legacy token heuristics (backward compat for events without metadata)
  const tokens = normalizeTokens(state);
  if (hasAny(tokens, ["gmail"]) || hasContains(tokens, ["gmail."])) return "gmail";
  if (hasAny(tokens, ["slack"]) || hasContains(tokens, ["slack."])) return "slack";
  if (hasAny(tokens, ["sap"]) || hasContains(tokens, ["sap."])) return "sap";
  if (hasAny(tokens, ["excel"]) || hasContains(tokens, ["excel."])) return "excel";
  if (hasAny(tokens, ["outlook"]) || hasContains(tokens, ["outlook."])) return "outlook";
  if (hasAny(tokens, ["sheets", "google_sheets"]) || hasContains(tokens, ["sheets."])) return "sheets";

  return null;
}

function resolveApiScene(state: ApiSceneState): ApiSceneRegistryResult {
  const variant = resolveCloneVariant(state);
  if (!variant) {
    return { kind: "generic" };
  }
  return { kind: "clone", variant };
}

export type { ApiSceneKind, ApiSceneRegistryResult };
export { resolveApiScene };
