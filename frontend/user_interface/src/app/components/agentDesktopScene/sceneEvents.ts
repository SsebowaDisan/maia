type SceneOverlayVariant = "center-pill" | "left-chip" | "human-alert";

type SceneOverlayState = {
  text: string;
  variant: SceneOverlayVariant;
  pulse?: boolean;
  detail?: string;
};

type SceneOverlayInput = {
  eventType: string;
  sceneSurface: string;
  activeDetail: string;
  scrollDirection: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
};

function clean(value: string): string {
  return String(value || "").trim();
}

function normalize(value: string): string {
  return clean(value).toLowerCase();
}

function normalizedAction(raw: string): string {
  const value = normalize(raw);
  if (
    value === "navigate" ||
    value === "hover" ||
    value === "click" ||
    value === "type" ||
    value === "scroll" ||
    value === "extract" ||
    value === "verify"
  ) {
    return value;
  }
  return "";
}

function surfaceLabel(surface: string): string {
  const normalizedSurface = normalize(surface);
  if (normalizedSurface === "website" || normalizedSurface === "browser") {
    return "page";
  }
  if (normalizedSurface === "document") {
    return "document";
  }
  if (normalizedSurface === "google_docs" || normalizedSurface === "docs") {
    return "doc";
  }
  if (normalizedSurface === "google_sheets" || normalizedSurface === "sheets") {
    return "sheet";
  }
  if (normalizedSurface === "email") {
    return "draft";
  }
  return "workspace";
}

function inferDefaultOverlayForAction({
  action,
  actionPhase,
  actionTargetLabel,
  sceneSurface,
  scrollDirection,
}: {
  action: string;
  actionPhase: string;
  actionTargetLabel: string;
  sceneSurface: string;
  scrollDirection: string;
}): SceneOverlayState | null {
  const normalized = normalizedAction(action);
  if (!normalized) {
    return null;
  }
  const label = clean(actionTargetLabel);
  const phase = normalize(actionPhase);
  const target = surfaceLabel(sceneSurface);

  if (normalized === "click") {
    return {
      text: label ? `Clicking ${label}` : `Clicking ${target}`,
      variant: "center-pill",
      pulse: true,
    };
  }
  if (normalized === "navigate") {
    return {
      text: label ? `Opening ${label}` : `Opening ${target}`,
      variant: "center-pill",
      pulse: phase === "start" || phase === "active",
    };
  }
  if (normalized === "hover") {
    return {
      text: label ? `Hovering ${label}` : `Hovering ${target}`,
      variant: "center-pill",
    };
  }
  if (normalized === "scroll") {
    const direction = normalize(scrollDirection) === "up" ? "up" : "down";
    return {
      text: `Scrolling ${direction}`,
      variant: "center-pill",
      pulse: true,
    };
  }
  if (normalized === "type") {
    return {
      text: label ? `Typing in ${label}` : `Typing in ${target}`,
      variant: "left-chip",
      pulse: phase === "active",
    };
  }
  if (normalized === "extract") {
    return {
      text: label ? `Extracting from ${label}` : `Extracting from ${target}`,
      variant: "left-chip",
      pulse: phase === "active",
    };
  }
  if (normalized === "verify") {
    return {
      text: label ? `Verifying ${label}` : `Verifying ${target}`,
      variant: "left-chip",
      pulse: phase === "active",
    };
  }
  return null;
}

function overlayForInteractionEvent({
  eventType,
  sceneSurface,
  activeDetail,
  scrollDirection,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
}: SceneOverlayInput): SceneOverlayState | null {
  const type = normalize(eventType);
  const status = normalize(actionStatus);
  if (
    type === "browser_human_verification_required" ||
    type === "approval_required" ||
    type === "policy_blocked"
  ) {
    return {
      text: "Human verification required",
      variant: "human-alert",
      detail: clean(activeDetail) || "Complete verification, then continue.",
    };
  }
  if (status === "failed" || type.endsWith("_failed")) {
    return {
      text: "Action failed",
      variant: "human-alert",
      detail: clean(activeDetail) || "The agent will retry or request help.",
    };
  }

  const byAction = inferDefaultOverlayForAction({
    action,
    actionPhase,
    actionTargetLabel,
    sceneSurface,
    scrollDirection,
  });
  if (byAction) {
    return byAction;
  }

  if (type.startsWith("role_")) {
    return {
      text: "Switching active role",
      variant: "left-chip",
      pulse: true,
    };
  }
  return null;
}

export type { SceneOverlayState };
export { overlayForInteractionEvent };
