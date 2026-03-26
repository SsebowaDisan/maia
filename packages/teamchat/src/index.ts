/**
 * @maia/teamchat — live agent conversation UI.
 *
 * Usage:
 *   import { TeamChat } from '@maia/teamchat';
 *   <TeamChat streamUrl="/acp/events" />
 */

export { TeamChat } from "./components/TeamChat";
export type { TeamChatProps } from "./components/TeamChat";

export { AgentBubble } from "./components/AgentBubble";
export type { AgentBubbleProps } from "./components/AgentBubble";

export { ReviewBadge } from "./components/ReviewBadge";
export type { ReviewBadgeProps } from "./components/ReviewBadge";

export { TypingIndicator } from "./components/TypingIndicator";
export type { TypingIndicatorProps } from "./components/TypingIndicator";

export { useConversationStream } from "./hooks/useConversationStream";
export type { UseConversationStreamOptions, ConversationStreamState } from "./hooks/useConversationStream";