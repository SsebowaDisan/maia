import type { ConnectorSummary } from "../../types/connectorSummary";
import type { ConnectorDefinition } from "../settings/connectorDefinitions";
import { buildGoogleSubServices, buildMicrosoftSubServices } from "./catalogModel.subServices";
import {
  connectorVisibility,
  normalizeSceneFamily,
  normalizeSetupMode,
  readAuthKind,
  readNumber,
  readString,
  readSubServices,
} from "./catalogModel.readers";
import { inferAuthType, resolveStatus, resolveStatusFromCatalog } from "./catalogModel.status";
import {
  buildFilteredSections,
  buildSuiteCounts,
  matchesFilter,
  primaryActionLabel,
  resolveConnectorSuite,
  suiteAccentClass,
  suiteFilterLabel,
} from "./catalogModel.suites";
import { findChangedConnectorId, isBindingMissingError, isNotFoundError } from "./catalogModel.errors";
import {
  SUITE_DEFINITIONS,
  humanizeConnectorId,
  uniqueIds,
  type ConnectorCatalogRow,
  type ConnectorHealthEntry,
  type ConnectorListFilter,
  type ConnectorSuiteFilter,
  type ConnectorSuiteKey,
  type ConnectorSuiteSection,
} from "./catalogModel.types";

function buildConnectorSummary(
  connectorId: string,
  args: {
    manualMap: Map<string, ConnectorDefinition>;
    pluginMap: Map<string, { label: string; actions?: Array<{ tool_ids?: string[] }> }>;
    catalogMap: Map<string, ConnectorCatalogRow>;
    healthMap: Record<string, ConnectorHealthEntry>;
    credentialMap: Record<string, { connector_id: string }>;
    googleEnabledServiceIds: string[];
    googleSelectedServiceIds: string[];
  },
): ConnectorSummary {
  const catalogRow = args.catalogMap.get(connectorId);
  const visibility = connectorVisibility(connectorId, catalogRow);
  const manual = args.manualMap.get(connectorId) || null;
  const plugin = args.pluginMap.get(connectorId) || null;
  const health = args.healthMap[connectorId] || null;
  const credential = args.credentialMap[connectorId] || null;
  const authType = inferAuthType(manual, readAuthKind(catalogRow));
  const statusState = resolveStatusFromCatalog(catalogRow) || resolveStatus(authType, health, credential);
  const actionsCount = Array.isArray(plugin?.actions) ? plugin.actions.length : 0;
  const tools = uniqueIds(
    (plugin?.actions || []).flatMap((action) =>
      Array.isArray(action.tool_ids) ? action.tool_ids : [],
    ),
  );
  const suiteId = readString(catalogRow, "suite_id") || undefined;
  const suiteLabel = readString(catalogRow, "suite_label") || undefined;
  const serviceOrder = readNumber(catalogRow, "service_order", 99);
  const sceneFamily = normalizeSceneFamily(readString(catalogRow, "scene_family").toLowerCase());
  const setupMode = normalizeSetupMode(readString(catalogRow, "setup_mode").toLowerCase(), authType);
  const brandSlug = readString(catalogRow, "brand_slug").toLowerCase() || connectorId;

  let subServices = readSubServices(catalogRow);
  const suiteIdLower = (suiteId || "").toLowerCase();
  if (!subServices.length && (suiteIdLower === "google" || connectorId === "google_workspace")) {
    subServices = buildGoogleSubServices(
      args.googleEnabledServiceIds,
      args.googleSelectedServiceIds,
      args.healthMap,
      args.credentialMap,
    );
  } else if (!subServices.length && (suiteIdLower === "microsoft" || connectorId === "m365" || connectorId === "microsoft_365")) {
    subServices = buildMicrosoftSubServices(
      connectorId,
      args.healthMap,
      args.credentialMap,
    );
  }

  return {
    id: connectorId,
    name: String(
      readString(catalogRow, "name") ||
        plugin?.label ||
        manual?.label ||
        humanizeConnectorId(connectorId),
    ),
    description: String(
      readString(catalogRow, "description") ||
        manual?.description ||
        (actionsCount > 0
          ? `${actionsCount} runtime actions available.`
          : "Connector is registered and ready for setup."),
    ),
    authType,
    status: statusState.status,
    statusMessage: statusState.statusMessage,
    actionsCount,
    tools,
    brandSlug,
    suiteId,
    suiteLabel,
    serviceOrder: Number.isFinite(serviceOrder) ? serviceOrder : 99,
    setupMode,
    sceneFamily,
    visibility,
    subServices,
  } satisfies ConnectorSummary;
}

function buildConnectorSummaries(args: {
  manualDefinitions: ConnectorDefinition[];
  plugins: Array<{ connector_id: string; label: string; actions?: Array<{ tool_ids?: string[] }> }>;
  healthMap: Record<string, ConnectorHealthEntry>;
  credentialMap: Record<string, { connector_id: string }>;
  catalogRows: ConnectorCatalogRow[];
  googleEnabledServiceIds: string[];
  googleSelectedServiceIds: string[];
}): ConnectorSummary[] {
  const manualMap = new Map<string, ConnectorDefinition>(
    args.manualDefinitions.map((definition) => [definition.id, definition]),
  );
  const pluginMap = new Map(
    args.plugins.map((plugin) => [plugin.connector_id, plugin]),
  );
  const catalogMap = new Map<string, ConnectorCatalogRow>();
  for (const row of args.catalogRows || []) {
    const connectorId = readString(row, "id");
    if (!connectorId) {
      continue;
    }
    catalogMap.set(connectorId, row);
  }

  const allConnectorIds = uniqueIds([
    ...manualMap.keys(),
    ...pluginMap.keys(),
    ...Object.keys(args.healthMap),
    ...Object.keys(args.credentialMap),
    ...catalogMap.keys(),
  ]);

  return allConnectorIds
    .map((connectorId) =>
      buildConnectorSummary(connectorId, {
        manualMap,
        pluginMap,
        catalogMap,
        healthMap: args.healthMap,
        credentialMap: args.credentialMap,
        googleEnabledServiceIds: args.googleEnabledServiceIds,
        googleSelectedServiceIds: args.googleSelectedServiceIds,
      }),
    )
    .filter((connector) => connector.visibility !== "internal")
    .sort((left, right) => {
      if (left.suiteId === right.suiteId) {
        const orderDiff = (left.serviceOrder || 99) - (right.serviceOrder || 99);
        if (orderDiff !== 0) {
          return orderDiff;
        }
      }
      return left.name.localeCompare(right.name);
    });
}

function buildConnectorStats(cards: ConnectorSummary[]) {
  return {
    connected: cards.filter((card) => card.status === "Connected").length,
    needsSetup: cards.filter((card) => card.status === "Not connected").length,
    attention: cards.filter(
      (card) => card.status === "Expired" || card.status === "Needs permission",
    ).length,
    total: cards.length,
  };
}

export {
  SUITE_DEFINITIONS,
  buildConnectorStats,
  buildConnectorSummaries,
  buildFilteredSections,
  buildSuiteCounts,
  findChangedConnectorId,
  isBindingMissingError,
  isNotFoundError,
  matchesFilter,
  primaryActionLabel,
  resolveConnectorSuite,
  suiteAccentClass,
  suiteFilterLabel,
  uniqueIds,
};

export type {
  ConnectorCatalogRow,
  ConnectorHealthEntry,
  ConnectorListFilter,
  ConnectorSuiteFilter,
  ConnectorSuiteKey,
  ConnectorSuiteSection,
};
