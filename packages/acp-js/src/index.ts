// ─── @maia/acp ──────────────────────────────────────────────────────────────
// Agent Collaboration Protocol — TypeScript/JavaScript client
//
// Quick start:
//   import { ACPClient, message } from '@maia/acp';
//
//   const client = new ACPClient({ agentId: 'agent://my-agent' });
//   client.connect('http://localhost:3000/acp/events');
//   client.on('message', (e) => console.log(e.payload.content));

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
} from "./types";
export type {
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
} from "./execution-types";

// Client
export { ACPClient } from "./client";
export { ACPAgentRegistry } from "./registry";

// Builders
export {
  envelope,
  message,
  handoff,
  review,
  artifact,
  activity,
  capabilities,
} from "./builders";
export { executionActivity, executionEnvelope } from "./execution-builders";

// Stream utilities
export { parseSSELine, streamToACPEvents, connectToSSE } from "./stream";
