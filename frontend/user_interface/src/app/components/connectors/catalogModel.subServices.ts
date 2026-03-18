import {
  GOOGLE_SERVICE_DEFS,
  normalizeServiceIds,
  type GoogleServiceDefinition,
} from "../settings/tabs/integrations/googleServices";
import type { ConnectorCredentialRecord } from "../../../api/client";
import type { ConnectorSubService } from "../../types/connectorSummary";
import {
  MICROSOFT_SERVICE_ROWS,
  uniqueIds,
  type ConnectorHealthEntry,
} from "./catalogModel.types";

const GOOGLE_SERVICE_CONNECTOR_MAP: Record<GoogleServiceDefinition["id"], string[]> = {
  gmail: ["gmail", "google_workspace"],
  calendar: ["google_calendar", "gcalendar"],
  drive: ["google_workspace", "google_drive", "gdrive"],
  docs: ["google_workspace", "google_docs", "gdocs"],
  sheets: ["google_workspace", "google_sheets", "gsheets"],
  analytics: ["google_analytics"],
};

const PRIMARY_GOOGLE_SERVICE_IDS = [
  "gmail",
  "calendar",
  "drive",
  "docs",
  "sheets",
  "analytics",
] as const;

export function buildGoogleSubServices(
  enabledServiceIds: string[],
  selectedServiceIds: string[],
  healthMap: Record<string, ConnectorHealthEntry>,
  credentialMap: Record<string, ConnectorCredentialRecord>,
): ConnectorSubService[] {
  const enabled = new Set(normalizeServiceIds(enabledServiceIds));
  const selected = new Set(normalizeServiceIds(selectedServiceIds));
  const preferred = new Set<string>(PRIMARY_GOOGLE_SERVICE_IDS);
  const hintedIds = Object.keys(GOOGLE_SERVICE_CONNECTOR_MAP);
  const extras = uniqueIds([...enabled, ...selected, ...hintedIds]).filter(
    (id) => !preferred.has(id),
  );
  const orderedIds = [...PRIMARY_GOOGLE_SERVICE_IDS, ...extras];

  const hints: Partial<Record<GoogleServiceDefinition["id"], ConnectorSubService["status"]>> = {};
  for (const [serviceId, connectorIds] of Object.entries(
    GOOGLE_SERVICE_CONNECTOR_MAP,
  ) as Array<[GoogleServiceDefinition["id"], string[]]>) {
    const hasHealthyConnector = connectorIds.some(
      (connectorId) => Boolean(healthMap[connectorId]?.ok),
    );
    if (hasHealthyConnector) {
      hints[serviceId] = "Connected";
      continue;
    }
    const hasStoredCredential = connectorIds.some((connectorId) =>
      Boolean(credentialMap[connectorId]),
    );
    if (hasStoredCredential) {
      hints[serviceId] = "Needs permission";
    }
  }

  return orderedIds
    .map((id) => GOOGLE_SERVICE_DEFS.find((definition) => definition.id === id))
    .filter((definition): definition is (typeof GOOGLE_SERVICE_DEFS)[number] => Boolean(definition))
    .map((definition) => ({
      id: definition.id,
      label: definition.label,
      description: definition.description,
      brandSlug:
        definition.id === "gmail"
          ? "gmail"
          : definition.id === "calendar"
            ? "google_calendar"
            : definition.id === "drive"
              ? "google_drive"
              : definition.id === "docs"
                ? "google_docs"
                : definition.id === "sheets"
                  ? "google_sheets"
                  : definition.id === "analytics"
                    ? "google_analytics"
                    : "google",
      sceneFamily:
        definition.id === "gmail"
          ? "email"
          : definition.id === "sheets"
            ? "sheet"
            : definition.id === "drive" || definition.id === "docs"
              ? "document"
              : "api",
      status:
        hints[definition.id] ||
        (enabled.has(definition.id)
          ? "Connected"
          : selected.has(definition.id)
            ? "Needs permission"
            : "Disabled"),
    }));
}

export function buildMicrosoftSubServices(
  connectorId: string,
  healthMap: Record<string, ConnectorHealthEntry>,
  credentialMap: Record<string, ConnectorCredentialRecord>,
): ConnectorSubService[] {
  const hasHealthyConnector = Boolean(healthMap[connectorId]?.ok);
  const hasCredential = Boolean(credentialMap[connectorId]);
  const nextStatus: ConnectorSubService["status"] = hasHealthyConnector
    ? "Connected"
    : hasCredential
      ? "Needs permission"
      : "Disabled";
  return MICROSOFT_SERVICE_ROWS.map((service) => ({
    ...service,
    status: nextStatus,
  }));
}
