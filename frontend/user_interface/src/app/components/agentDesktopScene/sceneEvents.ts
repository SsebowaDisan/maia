type SceneOverlayVariant = "center-pill" | "left-chip" | "human-alert";

type SceneOverlayState = {
  text: string;
  variant: SceneOverlayVariant;
  pulse?: boolean;
  detail?: string;
};

type SceneOverlayInput = {
  eventType: string;
  activeDetail: string;
  scrollDirection: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
};

function _clean(value: string): string {
  return String(value || "").trim();
}

function _normalizedAction(raw: string): string {
  const value = _clean(raw).toLowerCase();
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

function browserOverlayForEvent({
  eventType,
  activeDetail,
  scrollDirection,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
}: SceneOverlayInput): SceneOverlayState | null {
  const type = _clean(eventType).toLowerCase();
  if (!type.startsWith("browser_") && type !== "web_result_opened") {
    return null;
  }

  if (type === "browser_human_verification_required") {
    return {
      text: "Human verification required",
      variant: "human-alert",
      detail: _clean(activeDetail) || "Complete verification, then continue.",
    };
  }

  if (_clean(actionStatus).toLowerCase() === "failed") {
    return {
      text: "Action failed",
      variant: "human-alert",
      detail: _clean(activeDetail) || "The agent will retry or request help.",
    };
  }

  const normalizedAction = _normalizedAction(action);
  const targetLabel = _clean(actionTargetLabel);
  const phase = _clean(actionPhase).toLowerCase();

  if (normalizedAction === "click") {
    return {
      text: targetLabel ? `Clicking ${targetLabel}` : "Clicking page element",
      variant: "center-pill",
      pulse: true,
    };
  }

  if (normalizedAction === "navigate") {
    return {
      text: targetLabel ? `Opening ${targetLabel}` : "Opening page",
      variant: "center-pill",
      pulse: phase === "start" || phase === "active",
    };
  }

  if (normalizedAction === "hover") {
    return {
      text: targetLabel ? `Hovering ${targetLabel}` : "Hovering target",
      variant: "center-pill",
    };
  }

  if (normalizedAction === "scroll") {
    const direction = _clean(scrollDirection).toLowerCase() === "up" ? "up" : "down";
    return {
      text: `Scrolling ${direction}`,
      variant: "center-pill",
      pulse: true,
    };
  }

  if (normalizedAction === "type") {
    return {
      text: targetLabel ? `Typing in ${targetLabel}` : "Typing input",
      variant: "left-chip",
      pulse: phase === "active",
    };
  }

  if (normalizedAction === "extract") {
    return {
      text: targetLabel ? `Extracting from ${targetLabel}` : "Extracting source evidence",
      variant: "left-chip",
    };
  }

  if (normalizedAction === "verify") {
    return {
      text: targetLabel ? `Verifying ${targetLabel}` : "Verifying results",
      variant: "left-chip",
      pulse: phase === "active",
    };
  }

  if (type === "browser_cookie_accept" || type === "browser_cookie_check") {
    return {
      text: type === "browser_cookie_accept" ? "Cookie banner accepted" : "Checking cookie banner",
      variant: "left-chip",
    };
  }
  if (type === "browser_trusted_site_mode") {
    return {
      text: "Trusted-site policy active",
      variant: "left-chip",
    };
  }
  return null;
}

export type { SceneOverlayState };
export { browserOverlayForEvent };
