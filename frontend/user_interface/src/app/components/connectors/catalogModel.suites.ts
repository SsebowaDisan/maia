import type { ConnectorStatus, ConnectorSummary } from "../../types/connectorSummary";
import {
  GOOGLE_CONNECTOR_IDS,
  SUITE_DEFINITIONS,
  type ConnectorListFilter,
  type ConnectorSuiteFilter,
  type ConnectorSuiteKey,
  type ConnectorSuiteSection,
} from "./catalogModel.types";

export function resolveConnectorSuite(connector: {
  id: string;
  suiteId?: string;
}): ConnectorSuiteKey {
  const explicit = String(connector.suiteId || "").trim().toLowerCase();
  if (explicit === "google" || explicit === "google_workspace") {
    return "google_workspace";
  }
  if (explicit === "microsoft" || explicit === "microsoft_365" || explicit === "m365") {
    return "microsoft_365";
  }

  // Legacy fallback — ID heuristics for connectors without suite_id metadata.
  // Once all connectors have suite_id from the backend, these can be removed.
  const id = String(connector.id || "").trim().toLowerCase();
  if (
    GOOGLE_CONNECTOR_IDS.has(id) ||
    id.startsWith("google_") ||
    id === "gmail"
  ) {
    return "google_workspace";
  }
  if (
    id === "m365" ||
    id.startsWith("m365_") ||
    id.startsWith("microsoft_") ||
    id.startsWith("office_") ||
    id.startsWith("outlook_") ||
    id.startsWith("onedrive_")
  ) {
    return "microsoft_365";
  }
  return "standalone";
}

export function suiteAccentClass(suite: ConnectorSuiteKey): string {
  if (suite === "google_workspace") {
    return "bg-[#7c3aed]";
  }
  if (suite === "microsoft_365") {
    return "bg-[#0f766e]";
  }
  return "bg-[#6b7280]";
}

export function matchesFilter(status: ConnectorStatus, filter: ConnectorListFilter): boolean {
  if (filter === "all") {
    return true;
  }
  if (filter === "connected") {
    return status === "Connected";
  }
  if (filter === "attention") {
    return status === "Expired" || status === "Needs permission";
  }
  return status === "Not connected";
}

export function primaryActionLabel(status: ConnectorStatus): string {
  if (status === "Connected") {
    return "Manage";
  }
  if (status === "Needs permission") {
    return "Reconnect";
  }
  if (status === "Expired") {
    return "Reconnect";
  }
  return "Connect";
}

export function suiteFilterLabel(value: ConnectorSuiteFilter): string {
  if (value === "all") {
    return "All suites";
  }
  const match = SUITE_DEFINITIONS.find((suite) => suite.key === value);
  return match ? match.label : value;
}

export function buildSuiteCounts(cards: ConnectorSummary[]) {
  const counts: Record<ConnectorSuiteKey, number> = {
    google_workspace: 0,
    microsoft_365: 0,
    standalone: 0,
  };
  for (const card of cards) {
    counts[resolveConnectorSuite(card)] += 1;
  }
  return counts;
}

export function buildFilteredSections(args: {
  cards: ConnectorSummary[];
  activeFilter: ConnectorListFilter;
  activeSuite: ConnectorSuiteFilter;
}): ConnectorSuiteSection[] {
  const filteredCards = args.cards.filter((card) =>
    matchesFilter(card.status, args.activeFilter),
  );
  const grouped: Record<ConnectorSuiteKey, ConnectorSummary[]> = {
    google_workspace: [],
    microsoft_365: [],
    standalone: [],
  };
  for (const card of filteredCards) {
    grouped[resolveConnectorSuite(card)].push(card);
  }
  return SUITE_DEFINITIONS
    .map((definition) => ({
      ...definition,
      connectors: grouped[definition.key].sort((left, right) =>
        left.name.localeCompare(right.name),
      ),
    }))
    .filter((section) => args.activeSuite === "all" || section.key === args.activeSuite)
    .filter((section) => section.connectors.length > 0);
}
