import type {
  GoogleWorkspaceLinkAccessResult,
  GoogleWorkspaceLinkAnalyzeResult,
} from "../../../../../api/integrations";

type GoogleServiceDefinition = {
  id: "gmail" | "drive" | "docs" | "sheets" | "analytics";
  label: string;
  description: string;
  scopes: string[];
};

const BASE_SCOPES = ["openid", "email", "profile"] as const;

const GOOGLE_SERVICE_DEFS: GoogleServiceDefinition[] = [
  {
    id: "gmail",
    label: "Gmail",
    description: "Send, draft, and read emails.",
    scopes: [
      "https://www.googleapis.com/auth/gmail.compose",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.readonly",
    ],
  },
  {
    id: "drive",
    label: "Drive",
    description: "Find and manage files.",
    scopes: ["https://www.googleapis.com/auth/drive"],
  },
  {
    id: "docs",
    label: "Docs",
    description: "Create and edit documents.",
    scopes: ["https://www.googleapis.com/auth/documents"],
  },
  {
    id: "sheets",
    label: "Sheets",
    description: "Create and edit spreadsheets.",
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  },
  {
    id: "analytics",
    label: "Analytics",
    description: "Read GA4 reporting.",
    scopes: ["https://www.googleapis.com/auth/analytics.readonly"],
  },
];

const DEFAULT_SERVICES: string[] = ["gmail", "drive", "docs", "sheets"];

function dedupe(values: string[]): string[] {
  const rows: string[] = [];
  for (const raw of values) {
    const value = String(raw || "").trim();
    if (!value || rows.includes(value)) {
      continue;
    }
    rows.push(value);
  }
  return rows;
}

function normalizeServiceIds(serviceIds: string[]): string[] {
  const allowed = new Set(GOOGLE_SERVICE_DEFS.map((item) => item.id));
  return dedupe(serviceIds).filter((value) => allowed.has(value as GoogleServiceDefinition["id"]));
}

function scopesFromServices(serviceIds: string[]): string[] {
  const selected = new Set(normalizeServiceIds(serviceIds));
  const scopes = GOOGLE_SERVICE_DEFS.filter((item) => selected.has(item.id)).flatMap((item) => item.scopes);
  return dedupe([...BASE_SCOPES, ...scopes]);
}

function hasAllScopes(requiredScopes: string[], grantedScopes: string[]): boolean {
  const granted = new Set(grantedScopes.map((item) => String(item || "").trim()).filter(Boolean));
  return requiredScopes.every((scope) => granted.has(scope));
}

function serviceIdsFromScopes(scopes: string[]): string[] {
  const granted = new Set(scopes.map((item) => String(item || "").trim()).filter(Boolean));
  return GOOGLE_SERVICE_DEFS.filter((item) => item.scopes.every((scope) => granted.has(scope))).map(
    (item) => item.id,
  );
}

function serviceLabel(id: string): string {
  const match = GOOGLE_SERVICE_DEFS.find((item) => item.id === id);
  return match ? match.label : id;
}

function normalizeAliasText(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildSuggestedAlias(
  analysis: GoogleWorkspaceLinkAnalyzeResult | null,
  access: GoogleWorkspaceLinkAccessResult | null,
): string {
  const fromName = normalizeAliasText(String(access?.resource_name || ""));
  if (fromName) {
    return fromName.slice(0, 72);
  }

  const resourceType = String(analysis?.resource_type || access?.resource_type || "").trim();
  const resourceId = String(analysis?.resource_id || access?.resource_id || "").trim();
  const shortId = resourceId ? resourceId.slice(-6) : "";

  if (resourceType === "ga4_property" && resourceId) {
    return `ga4 property ${resourceId}`;
  }
  if (resourceType === "google_sheet") {
    return shortId ? `sheet ${shortId}` : "sheet";
  }
  if (resourceType === "google_doc") {
    return shortId ? `doc ${shortId}` : "doc";
  }
  if (resourceType === "google_drive_file") {
    return shortId ? `file ${shortId}` : "file";
  }
  if (shortId) {
    return `resource ${shortId}`;
  }
  return "google resource";
}

function sameList(left: string[], right: string[]): boolean {
  if (left.length !== right.length) {
    return false;
  }
  const a = [...left].sort();
  const b = [...right].sort();
  return a.every((value, index) => value === b[index]);
}

export {
  GOOGLE_SERVICE_DEFS,
  DEFAULT_SERVICES,
  buildSuggestedAlias,
  hasAllScopes,
  normalizeAliasText,
  normalizeServiceIds,
  sameList,
  scopesFromServices,
  serviceIdsFromScopes,
  serviceLabel,
  type GoogleServiceDefinition,
};
