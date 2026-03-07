import type { WorkGraphNode } from "./work_graph_types";

function readString(value: unknown): string {
  return String(value || "").trim();
}

function readRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

function extractNodeRiskReason(node: WorkGraphNode): string {
  const metadata = readRecord(node.metadata);
  const candidates = [
    metadata["risk_reason"],
    metadata["verification_reason"],
    metadata["confidence_reason"],
    metadata["verifier_conflict_reason"],
    metadata["warning_reason"],
  ];
  for (const candidate of candidates) {
    const text = readString(candidate);
    if (text) {
      return text;
    }
  }
  return "";
}

function shouldShowVerifierAction(node: WorkGraphNode): boolean {
  const status = readString(node.status).toLowerCase();
  const confidence = Number(node.confidence);
  if (status === "failed" || status === "blocked") {
    return true;
  }
  if (Number.isFinite(confidence) && confidence >= 0 && confidence < 0.6) {
    return true;
  }
  return Boolean(extractNodeRiskReason(node));
}

export { extractNodeRiskReason, shouldShowVerifierAction };
