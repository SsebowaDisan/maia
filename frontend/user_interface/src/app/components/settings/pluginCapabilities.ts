import type { ConnectorPluginManifest } from "../../../api/client";

export type ConnectorCapabilitySummary = {
  connectorId: string;
  enabled: boolean;
  actionCount: number;
  evidenceEmitterCount: number;
  graphMappingCount: number;
  sceneTypes: Array<"system" | "browser" | "document" | "email" | "sheet" | "api">;
  featuredActions: string[];
};

function normalizeActionTitle(value: string): string {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    return "";
  }
  return trimmed;
}

export function summarizeConnectorCapabilities(
  manifests: ConnectorPluginManifest[],
): Record<string, ConnectorCapabilitySummary> {
  const summaries: Record<string, ConnectorCapabilitySummary> = {};
  for (const manifest of manifests || []) {
    const connectorId = String(manifest?.connector_id || "").trim();
    if (!connectorId) {
      continue;
    }
    const actionRows = Array.isArray(manifest.actions) ? manifest.actions : [];
    const evidenceRows = Array.isArray(manifest.evidence_emitters) ? manifest.evidence_emitters : [];
    const graphRows = Array.isArray(manifest.graph_mapping) ? manifest.graph_mapping : [];
    const scenes = new Set<ConnectorCapabilitySummary["sceneTypes"][number]>();
    for (const row of Array.isArray(manifest.scene_mapping) ? manifest.scene_mapping : []) {
      const sceneType = row?.scene_type;
      if (sceneType === "system" || sceneType === "browser" || sceneType === "document" || sceneType === "email" || sceneType === "sheet" || sceneType === "api") {
        scenes.add(sceneType);
      }
    }
    for (const row of actionRows) {
      const sceneType = row?.scene_type;
      if (sceneType === "system" || sceneType === "browser" || sceneType === "document" || sceneType === "email" || sceneType === "sheet" || sceneType === "api") {
        scenes.add(sceneType);
      }
    }
    const featuredActions = actionRows
      .map((row) => normalizeActionTitle(row?.title || row?.action_id || ""))
      .filter(Boolean)
      .slice(0, 3);

    summaries[connectorId] = {
      connectorId,
      enabled: Boolean(manifest.enabled),
      actionCount: actionRows.length,
      evidenceEmitterCount: evidenceRows.length,
      graphMappingCount: graphRows.length,
      sceneTypes: Array.from(scenes).sort(),
      featuredActions,
    };
  }
  return summaries;
}

export function formatSceneSummary(sceneTypes: ConnectorCapabilitySummary["sceneTypes"]): string {
  if (!sceneTypes.length) {
    return "system";
  }
  return sceneTypes.join(", ");
}
