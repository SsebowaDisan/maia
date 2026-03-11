import type { AgentActivityEvent } from "../../types";
import { resolveEventSourceUrl } from "./helpers";

function maybeOpenEventSource(event: AgentActivityEvent): void {
  const shadowRaw = event.data?.shadow ?? event.metadata?.shadow;
  const isShadowEvent =
    typeof shadowRaw === "boolean"
      ? shadowRaw
      : ["true", "1", "yes"].includes(String(shadowRaw ?? "").trim().toLowerCase());
  if (isShadowEvent) {
    return;
  }

  const eventType = String(event.event_type || "");
  const isWorkspaceNavigationEvent =
    eventType === "drive.go_to_doc" ||
    eventType === "drive.go_to_sheet" ||
    eventType.startsWith("docs.") ||
    eventType.startsWith("sheets.");
  if (!isWorkspaceNavigationEvent) {
    return;
  }

  const sourceUrl = resolveEventSourceUrl(event);
  if (sourceUrl) {
    window.open(sourceUrl, "_blank", "noopener,noreferrer");
  }
}

export { maybeOpenEventSource };
