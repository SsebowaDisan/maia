/**
 * @maia/brain — orchestration runtime for AI agent teams.
 *
 * Usage:
 *   import { Brain } from '@maia/brain';
 *
 *   const brain = new Brain({
 *     agents: [researcher, analyst, writer],
 *     llm: { apiKey: "sk-..." },
 *   });
 *
 *   const result = await brain.run("Analyze SaaS pricing trends");
 */

// Core
export { Brain } from "./brain";

// Types
export type {
  AgentDefinition,
  BrainOptions,
  BrainResult,
  BrainStep,
  LLMConfig,
  ConversationThread,
  ConversationTurn,
  SharedContext,
  StepSummary,
} from "./types";

// LLM
export { callLLM, callLLMJson, safeParseJson, setLLMCache, setLLMTelemetry } from "./llm";
export type { LLMCallResult } from "./llm";

// Coverage
export { checkCoverage } from "./coverage";
export type { CoverageItem, CoverageResult } from "./coverage";

// Revision
export { buildRevisionSteps } from "./reviser";
export type { RevisionResult } from "./reviser";

// Dialogue
export { detectDialogueNeeds, proposeSeedDialogue, evaluateFollowUp } from "./dialogue";
export type { DialogueNeed, DialogueSeed, DialogueFollowUp } from "./dialogue";

// Collaboration
export {
  suggestConversationMove,
  draftConversationMessage,
  summarizeConversationThread,
} from "./collaboration";
export type {
  CollaborationParticipant,
  CollaborationContext,
  ConversationMove,
  MessageDraft,
  ThreadDigest,
} from "./collaboration";

// Roles (27 roles, each in its own file under ./roles/)
export {
  ROLE_CATALOG, getRole, getAllRoles, inferRole,
  formatRoleCatalogForPrompt, personalityPrompt,
} from "./roles/index";
export type { RoleDefinition, PersonalityProfile, AgentRole } from "./roles/types";

// Chat Guidance
export {
  CHAT_INTENTS,
  CONVERSATION_RULES,
  antiRepetitionPrompt,
  recentMessageOpenings,
  moodInstruction,
  isConversationRepetitive,
  suggestPivot,
} from "./guidance";
export type { ChatIntent } from "./guidance";

// State & Signals
export {
  createBrainState,
  recordStepOutcome,
  updateCoverage,
  raiseSignal,
  consumeRevisionBudget,
} from "./state";
export type {
  BrainState,
  TaskContract,
  CoverageState,
  StepOutcome,
  StepVerdict,
  BrainSignal,
  BrainDirective,
} from "./state";

// Memory
export {
  createMemoryStore,
  recordMemory,
  recallMemories,
  memoryContextPrompt,
  extractDecisions,
  serializeMemoryStore,
  deserializeMemoryStore,
} from "./memory";
export type { MemoryEntry, MemoryStore } from "./memory";

// Narration
export { narrateStepStart, narrateToolUse, narrateToolDone, narrateReply, narrateReview, narrateVerdict, narrateRevision, narrateHandoff } from "./narration";

// Cache
export { createCache, cacheKey } from "./cache";
export type { LLMCache, CacheEntry, CacheOptions, CacheStats } from "./cache";

// Providers
export { openai, anthropic, qwen, custom, callWithProviderChain } from "./providers";
export type { LLMProvider, ProviderChain } from "./providers";

// Structured Output
export { schema, schemaToPrompt, validateOutput } from "./structured";
export type { OutputSchema, FieldDef } from "./structured";

// Guardrails
export { createGuardrails, runGuards, injectionGuard, piiGuard, toxicityGuard, lengthGuard, customGuard } from "./guardrails";
export type { GuardrailConfig, GuardrailResult, GuardFn } from "./guardrails";

// Evaluation
export { evaluate, exactMatch, fuzzyMatch, containsKeywords, lengthRange, noHallucination } from "./eval";
export type { EvalDataset, EvalExample, EvalResult, EvalSummary, Scorer, ScorerResult } from "./eval";

// Telemetry
export { createTelemetry } from "./telemetry";
export type { Telemetry, TelemetryConfig, LLMSpan, TelemetrySummary } from "./telemetry";
