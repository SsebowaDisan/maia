type AgentIconSource = {
  required_connectors?: unknown;
  connector_status?: unknown;
  has_computer_use?: unknown;
  category?: unknown;
  tags?: unknown;
};

const KNOWN_CONNECTOR_HINTS = new Set([
  "gmail",
  "google_analytics",
  "google_ads",
  "google_calendar",
  "google_docs",
  "google_drive",
  "google_sheets",
  "m365",
  "outlook",
  "microsoft_teams",
  "notion",
  "slack",
  "hubspot",
  "salesforce",
  "jira",
  "airtable",
  "zendesk",
  "stripe",
  "shopify",
  "sap",
  "quickbooks",
  "xero",
  "github",
  "postgresql",
  "supabase",
  "bigquery",
  "pinecone",
  "twilio",
  "youtube",
  "linkedin",
  "twitter",
  "brave_search",
  "bing_search",
  "zapier_webhooks",
]);

const CATEGORY_FALLBACK_CONNECTOR: Record<string, string> = {
  analytics: "google_analytics",
  automation: "zapier_webhooks",
  content: "notion",
  crm: "salesforce",
  data: "google_sheets",
  support: "zendesk",
};

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function readConnectorStatusKeys(value: unknown): string[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.keys(value)
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function readCategoryFallback(value: unknown): string {
  const normalized = String(value || "").trim().toLowerCase();
  return CATEGORY_FALLBACK_CONNECTOR[normalized] || "";
}

export function resolveAgentIconConnectorId(source: AgentIconSource): string {
  const requiredConnectors = readStringArray(source.required_connectors);
  if (requiredConnectors.length > 0) {
    return requiredConnectors[0];
  }

  const connectorStatusKeys = readConnectorStatusKeys(source.connector_status);
  if (connectorStatusKeys.length > 0) {
    return connectorStatusKeys[0];
  }

  const tags = readStringArray(source.tags).map((item) => item.toLowerCase());
  const tagConnectorHint = tags.find((item) => KNOWN_CONNECTOR_HINTS.has(item));
  if (tagConnectorHint) {
    return tagConnectorHint;
  }

  const categoryConnector = readCategoryFallback(source.category);
  if (categoryConnector) {
    return categoryConnector;
  }

  if (Boolean(source.has_computer_use)) {
    return "computer_use_browser";
  }

  return "generic";
}

