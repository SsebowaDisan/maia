import { Activity, CheckCircle2, TriangleAlert } from "lucide-react";
import type { AgentActivityEvent } from "../../types";
import { EVT_VERIFICATION_CHECK } from "../../constants/eventTypes";
import type { EventStyle } from "./types";
import { coreEventStyles } from "./styleMaps/core";
import { integrationEventStyles } from "./styleMaps/integrations";

const eventStyles: Record<string, EventStyle> = {
  ...coreEventStyles,
  ...integrationEventStyles,
};

function styleForEvent(event: AgentActivityEvent | null): EventStyle {
  if (!event) {
    return {
      label: "Activity",
      icon: Activity,
      accent: "text-[#4c4c50]",
    };
  }
  if (String(event.event_type || "").trim().toLowerCase() === EVT_VERIFICATION_CHECK) {
    const status = String(event.metadata?.["status"] ?? event.data?.["status"] ?? "")
      .trim()
      .toLowerCase();
    if (status === "pass") {
      return {
        label: "Check Passed",
        icon: CheckCircle2,
        accent: "text-[#2f6a3f]",
      };
    }
    if (status === "warning") {
      return {
        label: "Check Warning",
        icon: TriangleAlert,
        accent: "text-[#b45309]",
      };
    }
    if (status === "fail") {
      return {
        label: "Check Failed",
        icon: TriangleAlert,
        accent: "text-[#9b1c1c]",
      };
    }
    if (status === "info") {
      return {
        label: "Check Info",
        icon: Activity,
        accent: "text-[#1d4ed8]",
      };
    }
  }
  return (
    eventStyles[event.event_type] || {
      label: event.event_type,
      icon: Activity,
      accent: "text-[#4c4c50]",
    }
  );
}

export { eventStyles, styleForEvent };
