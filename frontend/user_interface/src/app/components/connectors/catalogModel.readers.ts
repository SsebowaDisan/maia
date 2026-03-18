import type { ConnectorAuthType, ConnectorSubService, ConnectorSummary } from "../../types/connectorSummary";
import { INTERNAL_CONNECTOR_IDS, type ConnectorCatalogRow } from "./catalogModel.types";

export function readString(row: ConnectorCatalogRow | undefined, key: string): string {
  if (!row) {
    return "";
  }
  const value = row[key];
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  return "";
}

export function readNumber(row: ConnectorCatalogRow | undefined, key: string, fallback: number): number {
  if (!row) {
    return fallback;
  }
  const value = row[key];
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function readAuthKind(row: ConnectorCatalogRow | undefined): string {
  const explicit = readString(row, "auth_kind");
  if (explicit) {
    return explicit;
  }
  if (!row) {
    return "";
  }
  const auth = row["auth"];
  if (!auth || typeof auth !== "object") {
    return "";
  }
  const kind = (auth as Record<string, unknown>)["kind"];
  return typeof kind === "string" ? kind.trim() : "";
}

export function normalizeSceneFamily(value: string): ConnectorSummary["sceneFamily"] | undefined {
  if (
    value === "email" ||
    value === "sheet" ||
    value === "document" ||
    value === "api" ||
    value === "browser" ||
    value === "chat" ||
    value === "crm" ||
    value === "support" ||
    value === "commerce"
  ) {
    return value;
  }
  return undefined;
}

export function normalizeSetupMode(
  value: string,
  authType: ConnectorAuthType,
): ConnectorSummary["setupMode"] {
  if (
    value === "oauth_popup" ||
    value === "manual_credentials" ||
    value === "service_identity" ||
    value === "none"
  ) {
    if (value === "oauth_popup" && authType !== "oauth2") {
      return authType === "none" ? "none" : "manual_credentials";
    }
    return value;
  }
  if (authType === "oauth2") {
    return "oauth_popup";
  }
  if (authType === "none") {
    return "none";
  }
  return "manual_credentials";
}

function normalizeSubServiceStatus(value: unknown): ConnectorSubService["status"] {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "connected") {
    return "Connected";
  }
  if (normalized === "needs_permission") {
    return "Needs permission";
  }
  if (normalized === "needs_setup") {
    return "Needs setup";
  }
  if (normalized === "disabled") {
    return "Disabled";
  }
  return "Disabled";
}

export function readSubServices(row: ConnectorCatalogRow | undefined): ConnectorSubService[] {
  if (!row) {
    return [];
  }
  const raw = row["sub_services"];
  if (!Array.isArray(raw)) {
    return [];
  }
  const services: ConnectorSubService[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const obj = entry as Record<string, unknown>;
    const id = String(obj.id || "").trim();
    if (!id) {
      continue;
    }
    const label = String(obj.label || id).trim();
    const description = String(obj.description || "").trim();
    const brandSlug = String(obj.brand_slug || id).trim();
    const sceneFamily = normalizeSceneFamily(
      String(obj.scene_family || "").trim().toLowerCase(),
    );
    services.push({
      id,
      label,
      description,
      brandSlug,
      sceneFamily,
      status: normalizeSubServiceStatus(obj.status),
      requiredScopes: Array.isArray(obj.required_scopes)
        ? obj.required_scopes.map((scope) => String(scope || "").trim()).filter(Boolean)
        : [],
    });
  }
  return services;
}

export function connectorVisibility(
  connectorId: string,
  catalogRow?: ConnectorCatalogRow,
): "user_facing" | "internal" {
  const value = readString(catalogRow, "visibility").toLowerCase();
  if (value === "internal") {
    return "internal";
  }
  return INTERNAL_CONNECTOR_IDS.has(connectorId) ? "internal" : "user_facing";
}
