import type {
  ConnectorCredentialRecord,
  ConnectorPluginManifest,
} from "../../../api/client";
import type { ConnectorDefinition } from "../settings/connectorDefinitions";
import type { ConnectorSubService, ConnectorSummary } from "../../types/connectorSummary";

export type ConnectorHealthEntry = {
  ok: boolean;
  message: string;
};

export type ConnectorListFilter = "needs_setup" | "connected" | "attention" | "all";
export type ConnectorSuiteKey = "google_workspace" | "microsoft_365" | "standalone";
export type ConnectorSuiteFilter = "all" | ConnectorSuiteKey;

export type ConnectorSuiteSection = {
  key: ConnectorSuiteKey;
  label: string;
  description: string;
  connectors: ConnectorSummary[];
};

export type ConnectorCatalogRow = Record<string, unknown>;

export type ConnectorSummaryBuildArgs = {
  manualDefinitions: ConnectorDefinition[];
  plugins: ConnectorPluginManifest[];
  healthMap: Record<string, ConnectorHealthEntry>;
  credentialMap: Record<string, ConnectorCredentialRecord>;
  catalogRows: ConnectorCatalogRow[];
  googleEnabledServiceIds: string[];
  googleSelectedServiceIds: string[];
};

export const SUITE_DEFINITIONS: Omit<ConnectorSuiteSection, "connectors">[] = [
  {
    key: "google_workspace",
    label: "Google Suite",
    description: "Manage Gmail, Docs, Sheets, Analytics, Ads, and related Google services together.",
  },
  {
    key: "microsoft_365",
    label: "Microsoft 365",
    description: "Manage Outlook, OneDrive, Excel, Word, Teams, and related Microsoft services together.",
  },
  {
    key: "standalone",
    label: "Standalone Connectors",
    description: "Independent services and enterprise integrations configured separately.",
  },
];

// Use suite_id from backend metadata instead of hardcoded ID sets.
// These are kept as legacy fallbacks for records that lack suite_id.
export const GOOGLE_CONNECTOR_IDS = new Set([
  "google_workspace", "google_calendar", "google_analytics", "google_ads",
  "google_maps", "google_api_hub", "google_docs", "google_sheets",
  "google_drive", "gmail",
]);

// Internal/deprecated connectors — use visibility field from backend when available
export const INTERNAL_CONNECTOR_IDS = new Set([
  "gmail_playwright", "playwright_browser", "playwright_contact_form", "computer_use_browser",
]);

export function isGoogleConnector(connector: { id?: string; suite_id?: string }): boolean {
  return String(connector.suite_id || "").toLowerCase() === "google" || GOOGLE_CONNECTOR_IDS.has(String(connector.id || ""));
}

export function isInternalConnector(connector: { id?: string; visibility?: string }): boolean {
  return String(connector.visibility || "").toLowerCase() === "internal" || INTERNAL_CONNECTOR_IDS.has(String(connector.id || ""));
}

export const MICROSOFT_SERVICE_ROWS: ConnectorSubService[] = [
  {
    id: "outlook",
    label: "Outlook",
    description: "Mail and thread operations through Microsoft 365.",
    status: "Disabled",
    brandSlug: "outlook",
    sceneFamily: "email",
  },
  {
    id: "microsoft_calendar",
    label: "Microsoft Calendar",
    description: "Calendar events and scheduling inside Microsoft 365.",
    status: "Disabled",
    brandSlug: "microsoft_calendar",
    sceneFamily: "api",
  },
  {
    id: "onedrive",
    label: "OneDrive",
    description: "Cloud file access through the Microsoft 365 suite.",
    status: "Disabled",
    brandSlug: "onedrive",
    sceneFamily: "document",
  },
  {
    id: "excel",
    label: "Excel",
    description: "Spreadsheet reading and updates via Microsoft 365.",
    status: "Disabled",
    brandSlug: "excel",
    sceneFamily: "sheet",
  },
  {
    id: "word",
    label: "Word",
    description: "Document authoring and reading through Microsoft 365.",
    status: "Disabled",
    brandSlug: "word",
    sceneFamily: "document",
  },
  {
    id: "teams",
    label: "Teams",
    description: "Messaging and collaboration through Microsoft 365.",
    status: "Disabled",
    brandSlug: "teams",
    sceneFamily: "chat",
  },
];

export function uniqueIds(values: string[]): string[] {
  return Array.from(
    new Set(values.map((item) => String(item || "").trim()).filter(Boolean)),
  );
}

export function humanizeConnectorId(id: string): string {
  return id
    .split(/[_-]+/g)
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}
