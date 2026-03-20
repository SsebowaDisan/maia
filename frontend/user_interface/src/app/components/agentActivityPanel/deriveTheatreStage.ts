import type { PreviewTab } from "../agentActivityMeta";
import type { SurfaceCommit } from "./surfaceCommitDerivation";

type TheatreStage =
  | "idle"
  | "understand"
  | "breakdown"
  | "analyze"
  | "surface"
  | "execute"
  | "review"
  | "confirm"
  | "done"
  | "blocked"
  | "needs_input"
  | "error";

function deriveTheatreStage({
  streaming,
  hasEvents,
  activeStageSignal,
  activeEventType,
  activeEventStatus,
  activeEventTitle,
  surfaceCommit,
  needsHumanReview,
  hasApprovalGate,
  isBlocked,
  needsInput,
  hasError,
}: {
  streaming: boolean;
  hasEvents: boolean;
  activeStageSignal: string | null;
  activeEventType: string | null;
  activeEventStatus: string | null;
  activeEventTitle: string | null;
  surfaceCommit: SurfaceCommit | null;
  needsHumanReview: boolean;
  hasApprovalGate: boolean;
  isBlocked: boolean;
  needsInput: boolean;
  hasError: boolean;
}): TheatreStage {
  if (!hasEvents) {
    return "idle";
  }
  if (hasError) {
    return "error";
  }
  if (isBlocked) {
    return "blocked";
  }
  if (needsInput) {
    return "needs_input";
  }
  if (hasApprovalGate) {
    return "confirm";
  }
  if (needsHumanReview && !streaming) {
    return "review";
  }

  const signal = [
    String(activeStageSignal || "").trim().toLowerCase(),
    String(activeEventType || "").trim().toLowerCase(),
    String(activeEventStatus || "").trim().toLowerCase(),
    String(activeEventTitle || "").trim().toLowerCase(),
  ]
    .filter(Boolean)
    .join(" ");

  if (
    signal.includes("understand") ||
    signal.includes("contract") ||
    signal.includes("clarif") ||
    signal.includes("preflight") ||
    signal.includes("intake")
  ) {
    return "understand";
  }
  if (
    signal.includes("plan") ||
    signal.includes("assembly") ||
    signal.includes("decompose") ||
    signal.includes("breakdown")
  ) {
    return "breakdown";
  }
  if (
    signal.includes("review") ||
    signal.includes("verify") ||
    signal.includes("verif") ||
    signal.includes("approval") ||
    signal.includes("qa")
  ) {
    return "review";
  }
  if (
    signal.includes("execute") ||
    signal.includes("tool_") ||
    signal.includes("dialogue") ||
    signal.includes("handoff") ||
    signal.includes("workflow") ||
    signal.includes("run")
  ) {
    return surfaceCommit ? "execute" : "analyze";
  }
  if (
    signal.includes("deliver") ||
    signal.includes("publish") ||
    signal.includes("final") ||
    signal.includes("email_sent") ||
    signal.includes("workflow_completed") ||
    signal.includes("execution_complete")
  ) {
    if (streaming) {
      return hasApprovalGate ? "confirm" : (surfaceCommit ? "execute" : "analyze");
    }
    return "done";
  }
  if (!streaming) {
    return surfaceCommit ? "done" : "idle";
  }
  return surfaceCommit ? "execute" : "analyze";
}

function desiredPreviewTabForStage({
  stage,
  sceneTab,
  surfaceCommit,
  fallbackPreviewTab,
  manualOverride,
}: {
  stage: TheatreStage;
  sceneTab: PreviewTab;
  surfaceCommit: SurfaceCommit | null;
  fallbackPreviewTab: PreviewTab;
  manualOverride: boolean;
}): PreviewTab {
  if (manualOverride) {
    return fallbackPreviewTab;
  }
  if (stage === "analyze" && sceneTab !== "system") {
    return sceneTab;
  }
  if (stage === "surface" || stage === "execute" || stage === "done") {
    if (surfaceCommit?.tab) {
      return surfaceCommit.tab;
    }
    if (sceneTab !== "system") {
      return sceneTab;
    }
    return fallbackPreviewTab;
  }
  return "system";
}

export { deriveTheatreStage, desiredPreviewTabForStage };
export type { TheatreStage };

