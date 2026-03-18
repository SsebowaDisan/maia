import type { ConnectorDefinition } from "../settings/connectorDefinitions";
import type { ConnectorAuthType, ConnectorStatus } from "../../types/connectorSummary";
import type { ConnectorCredentialRecord } from "../../../api/client";
import { readString } from "./catalogModel.readers";
import type { ConnectorCatalogRow, ConnectorHealthEntry } from "./catalogModel.types";

export function normalizeAuthType(raw: unknown): ConnectorAuthType {
  const normalized = String(raw || "").trim().toLowerCase();
  if (normalized === "oauth2") {
    return "oauth2";
  }
  if (normalized === "api_key" || normalized === "apikey") {
    return "api_key";
  }
  if (normalized === "basic") {
    return "basic";
  }
  if (normalized === "bearer") {
    return "bearer";
  }
  if (normalized === "service_identity") {
    return "service_identity";
  }
  return "none";
}

export function inferAuthType(
  definition: ConnectorDefinition | null,
  authHint: unknown,
): ConnectorAuthType {
  const hinted = normalizeAuthType(authHint);
  if (hinted !== "none") {
    return hinted;
  }
  if (!definition) {
    return "none";
  }
  const keys = definition.fields.map((field) => String(field.key || "").toUpperCase());
  if (keys.some((key) => key.includes("PASSWORD"))) {
    return "basic";
  }
  if (keys.some((key) => key.includes("TOKEN"))) {
    return "bearer";
  }
  if (keys.some((key) => key.includes("API_KEY") || key.endsWith("_KEY"))) {
    return "api_key";
  }
  return definition.fields.length ? "api_key" : "none";
}

export function resolveStatus(
  authType: ConnectorAuthType,
  health: ConnectorHealthEntry | null,
  credential: ConnectorCredentialRecord | null,
): { status: ConnectorStatus; statusMessage: string } {
  if (authType === "none") {
    return {
      status: "Connected",
      statusMessage: "Public connector with no credentials required.",
    };
  }
  const message = String(health?.message || "").trim();
  const normalizedMessage = message.toLowerCase();
  const cleanMessage = normalizedMessage === "configured" ? "Connected and ready." : message;
  if (health?.ok) {
    return {
      status: "Connected",
      statusMessage: cleanMessage || "Connection healthy.",
    };
  }
  if (credential) {
    if (/(expired|refresh|unauthorized|forbidden|invalid)/i.test(cleanMessage)) {
      return {
        status: "Expired",
        statusMessage: cleanMessage || "Credential needs refresh.",
      };
    }
    return {
      status: "Not connected",
      statusMessage: cleanMessage || "Credential stored but the connection test failed.",
    };
  }
  return {
    status: "Not connected",
    statusMessage: cleanMessage || "No credential configured yet.",
  };
}

export function resolveStatusFromCatalog(
  row: ConnectorCatalogRow | undefined,
): { status: ConnectorStatus; statusMessage: string } | null {
  const setupStatus = readString(row, "setup_status").toLowerCase();
  if (!setupStatus) {
    return null;
  }
  const setupMessage = readString(row, "setup_message");
  if (setupStatus === "connected") {
    return { status: "Connected", statusMessage: setupMessage || "Connected and ready." };
  }
  if (setupStatus === "expired") {
    return { status: "Expired", statusMessage: setupMessage || "Credential expired." };
  }
  if (setupStatus === "needs_permission") {
    return { status: "Needs permission", statusMessage: setupMessage || "Missing required permissions." };
  }
  return { status: "Not connected", statusMessage: setupMessage || "Connector setup is required." };
}
