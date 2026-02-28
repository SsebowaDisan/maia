import { Activity } from "lucide-react";
import type { AgentActivityEvent } from "../../types";
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
  return (
    eventStyles[event.event_type] || {
      label: event.event_type,
      icon: Activity,
      accent: "text-[#4c4c50]",
    }
  );
}

export { eventStyles, styleForEvent };
