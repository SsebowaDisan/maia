import type { PreviewTab } from "../agentActivityMeta";
import type { SurfaceCommit } from "./surfaceCommitDerivation";

type ActivityPhase =
  | "understanding"
  | "contract"
  | "clarification"
  | "planning"
  | "execution"
  | "verification"
  | "delivery";

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
  activePhase,
  surfaceCommit,
  needsHumanReview,
  hasApprovalGate,
  isBlocked,
  needsInput,
  hasError,
}: {
  streaming: boolean;
  hasEvents: boolean;
  activePhase: ActivityPhase | null;
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

  const phase = activePhase;
  if (!phase) {
    if (!streaming) {
      return surfaceCommit ? "done" : "idle";
    }
    return surfaceCommit ? "surface" : "understand";
  }

  if (phase === "understanding" || phase === "contract" || phase === "clarification") {
    return "understand";
  }
  if (phase === "planning") {
    return "breakdown";
  }
  if (phase === "execution") {
    return surfaceCommit ? "execute" : "analyze";
  }
  if (phase === "verification") {
    return "review";
  }
  if (phase === "delivery") {
    if (streaming) {
      return hasApprovalGate ? "confirm" : (surfaceCommit ? "execute" : "analyze");
    }
    return "done";
  }
  return "idle";
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

