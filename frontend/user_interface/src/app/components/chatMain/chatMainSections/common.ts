export type PendingGateView = {
  runId: string;
  gateId: string;
  toolId: string;
  paramsPreview: string;
  actionLabel?: string;
  preview?: Record<string, unknown> | null;
  costEstimateUsd: number | null;
};

export function toPreviewText(value: unknown): string {
  if (typeof value === "string") {
    return value.trim();
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
  return String(value || "").trim();
}
