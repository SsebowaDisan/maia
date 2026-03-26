import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";

type ApiFieldDiff = {
  field: string;
  fromValue: string;
  toValue: string;
};

type ApiValidationCheck = {
  label: string;
  status: "passed" | "failed" | "pending";
  detail: string;
};

type ApiSceneState = {
  isApiScene: boolean;
  connectorId: string;
  connectorLabel: string;
  brandSlug: string;
  sceneFamily: string;
  objectType: string;
  objectId: string;
  operationLabel: string;
  summaryText: string;
  statusLabel: string;
  approvalRequired: boolean;
  approvalReason: string;
  fieldDiffs: ApiFieldDiff[];
  validations: ApiValidationCheck[];
  /** Raw tool parameters from the connector execution — used by skins for rich display. */
  toolParams: Record<string, unknown>;
};

function compact(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value).trim();
  }
  return "";
}

function parseFieldDiffs(source: unknown): ApiFieldDiff[] {
  if (!Array.isArray(source)) {
    return [];
  }
  const rows: ApiFieldDiff[] = [];
  for (const row of source) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const field = compact((row as Record<string, unknown>).field || (row as Record<string, unknown>).name);
    const fromValue = compact((row as Record<string, unknown>).from || (row as Record<string, unknown>).before);
    const toValue = compact((row as Record<string, unknown>).to || (row as Record<string, unknown>).after);
    if (!field) {
      continue;
    }
    rows.push({ field, fromValue, toValue });
    if (rows.length >= 8) {
      break;
    }
  }
  return rows;
}

function parseValidations(source: unknown): ApiValidationCheck[] {
  if (!Array.isArray(source)) {
    return [];
  }
  const rows: ApiValidationCheck[] = [];
  for (const row of source) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const label = compact((row as Record<string, unknown>).label || (row as Record<string, unknown>).name);
    if (!label) {
      continue;
    }
    const statusRaw = compact((row as Record<string, unknown>).status).toLowerCase();
    const status: ApiValidationCheck["status"] =
      statusRaw === "passed" || statusRaw === "failed" || statusRaw === "pending" ? statusRaw : "pending";
    const detail = compact((row as Record<string, unknown>).detail || (row as Record<string, unknown>).message);
    rows.push({ label, status, detail });
    if (rows.length >= 6) {
      break;
    }
  }
  return rows;
}

function parseApiSceneState(args: {
  activeSceneData: Record<string, unknown>;
  activeEventType: string;
  actionTargetLabel: string;
  actionStatus: string;
  sceneText: string;
  activeDetail: string;
}): ApiSceneState {
  const sceneData = args.activeSceneData || {};
  const sceneSurface = compact(sceneData["scene_surface"]).toLowerCase();
  const eventFamily = compact(sceneData["event_family"]).toLowerCase();
  const eventType = compact(args.activeEventType).toLowerCase();
  const isApiScene =
    sceneSurface === "api" ||
    eventFamily === "api" ||
    eventType.startsWith("api_") ||
    eventType.startsWith("api.");

  const connectorId = sanitizeComputerUseText(
    compact(sceneData["connector_id"] || sceneData["provider"] || sceneData["integration_id"]),
  );
  const connectorLabel = sanitizeComputerUseText(
    compact(sceneData["connector_label"] || sceneData["provider_label"] || connectorId),
  );
  const brandSlug = compact(sceneData["brand_slug"] || sceneData["plugin_brand_slug"] || connectorId);
  const sceneFamily = compact(sceneData["scene_family"] || sceneData["plugin_scene_family"]) || "api";
  const objectType = compact(sceneData["object_type"] || sceneData["resource_type"] || sceneData["entity_type"]);
  const objectId = compact(sceneData["object_id"] || sceneData["record_id"] || sceneData["resource_id"]);
  const operationLabel = sanitizeComputerUseText(
    compact(sceneData["operation_label"] || sceneData["action_label"] || sceneData["operation"]) ||
      compact(args.actionTargetLabel) ||
      "API operation",
  );
  const statusLabel = compact(sceneData["action_status"] || args.actionStatus || sceneData["status"]);
  const approvalRequired = Boolean(sceneData["approval_required"] || sceneData["request_approval"]);
  const approvalReason = compact(sceneData["approval_reason"] || sceneData["blocked_reason"]);
  const summaryText = sanitizeComputerUseText(compact(sceneData["summary"] || args.sceneText || args.activeDetail));

  // Extract tool_params for rich skin display
  const rawParams = sceneData["tool_params"] || sceneData["params"] || {};
  const toolParams: Record<string, unknown> =
    rawParams && typeof rawParams === "object" && !Array.isArray(rawParams)
      ? (rawParams as Record<string, unknown>)
      : {};

  return {
    isApiScene,
    connectorId,
    connectorLabel,
    brandSlug,
    sceneFamily,
    objectType,
    objectId,
    operationLabel,
    summaryText,
    statusLabel,
    approvalRequired,
    approvalReason,
    fieldDiffs: parseFieldDiffs(sceneData["field_diffs"] || sceneData["diffs"]),
    validations: parseValidations(sceneData["validations"] || sceneData["validation_checks"]),
    toolParams,
  };
}

export type { ApiFieldDiff, ApiSceneState, ApiValidationCheck };
export { parseApiSceneState };
