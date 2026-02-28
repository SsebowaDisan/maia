import type { AgentActivityEvent, ChatAttachment } from "../../types";

interface AgentActivityPanelProps {
  events: AgentActivityEvent[];
  streaming: boolean;
  stageAttachment?: ChatAttachment;
  needsHumanReview?: boolean;
  humanReviewNotes?: string | null;
  onJumpToEvent?: (event: AgentActivityEvent) => void;
}

export type { AgentActivityPanelProps };
