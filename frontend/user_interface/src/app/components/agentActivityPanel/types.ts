import type { AgentActivityEvent, ChatAttachment } from "../../types";

interface AgentActivityPanelProps {
  events: AgentActivityEvent[];
  streaming: boolean;
  stageAttachment?: ChatAttachment;
  onJumpToEvent?: (event: AgentActivityEvent) => void;
}

export type { AgentActivityPanelProps };
