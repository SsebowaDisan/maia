// ─── @maia/sdk ──────────────────────────────────────────────────────────────
//
// The collaboration and observability layer for AI agents.
// One import, everything you need.
//
// Usage:
//
//   // Protocol — agent-to-agent communication
//   import { ACPClient, message, handoff, review } from '@maia/sdk';
//
//   // Visualization — watch agents work live
//   import { Theatre, useACPStream } from '@maia/sdk/theatre';
//
// ─────────────────────────────────────────────────────────────────────────────

// ── ACP Protocol ─────────────────────────────────────────────────────────────
// Everything for agent-to-agent communication.

// Types
export type {
  ACPVersion,
  MessageIntent,
  AgentMood,
  ActivityType,
  ReviewVerdict,
  ArtifactKind,
  EventType,
  DeliveryStatus,
  AgentAvailability,
  TaskLifecycleStatus,
  ACPEvent,
  ACPMessage,
  ACPHandoff,
  ACPReview,
  ACPArtifact,
  ACPActivity,
  ACPCapabilities,
  ACPClientOptions,
  ACPEventMap,
  MessageContext,
  HandoffTask,
  PriorStep,
  ReviewIssue,
  ToolActivity,
  BrowserActivity,
  ProgressInfo,
  CostInfo,
  AgentPresence,
  DeliveryReceipt,
  ACPTransport,
  ACPRegistryLike,
  AgentPersonality,
  AgentSkill,
  ExecutionStage,
  ExecutionStatus,
  ExecutionSurface,
  ExecutionSceneFamily,
  ExecutionMetadata,
  ExecutionBrowserState,
  ExecutionEmailState,
  ExecutionDocumentState,
  ExecutionExtension,
  ACPExecutionActivity,
  ACPExecutionEvent,
} from "@maia/acp";

// Client
export { ACPClient } from "@maia/acp";

// Builders
export {
  envelope,
  message,
  handoff,
  review,
  artifact,
  activity,
  capabilities,
  executionActivity,
  executionEnvelope,
} from "@maia/acp";

// Stream utilities
export { parseSSELine, streamToACPEvents, connectToSSE } from "@maia/acp";

// Brain-native collaboration helpers
export {
  suggestConversationMove,
  draftConversationMessage,
  summarizeConversationThread,
} from "@maia/brain";
export type {
  LLMConfig,
  CollaborationParticipant,
  CollaborationContext,
  ConversationMove,
  MessageDraft,
  ThreadDigest,
} from "@maia/brain";

// Theatre theming
export { maiaTheme, resolveTheatreTheme } from "@maia/theatre";
export type { TheatreTheme, TheatreThemeOverride } from "@maia/theatre";
// Maia computer-use runtime client
export {
  cancelComputerUseSession,
  createComputerUseClient,
  defaultComputerUseClient,
  getComputerUseActiveModel,
  getComputerUsePolicy,
  getComputerUseSession,
  getComputerUseSLOSummary,
  listComputerUseSessions,
  navigateComputerUseSession,
  startComputerUseSession,
  streamComputerUseSession,
} from "@maia/computer-use";
export type {
  ComputerUseActiveModelResponse,
  ComputerUseClient,
  ComputerUseClientConfig,
  ComputerUsePolicyResponse,
  ComputerUseSessionListRecord,
  ComputerUseSessionRecord,
  ComputerUseSLOSummaryResponse,
  ComputerUseStreamEvent,
  NavigateComputerUseSessionResponse,
  StartComputerUseSessionInput,
  StartComputerUseSessionResponse,
  StreamComputerUseSessionOptions,
} from "@maia/computer-use";
