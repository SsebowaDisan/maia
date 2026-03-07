import type { AgentActivityEvent, ChatAttachment } from "../../types";

interface AgentActivityPanelProps {
  events: AgentActivityEvent[];
  streaming: boolean;
  stageAttachment?: ChatAttachment;
  needsHumanReview?: boolean;
  humanReviewNotes?: string | null;
  jumpTarget?: {
    graphNodeIds?: string[];
    sceneRefs?: string[];
    eventRefs?: string[];
    nonce?: string;
  } | null;
  onJumpToEvent?: (event: AgentActivityEvent) => void;
}

export type { AgentActivityPanelProps };
