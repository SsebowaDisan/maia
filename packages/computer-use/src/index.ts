/**
 * @maia/computer-use
 *
 * Maia computer session client for browser-side SDK consumers.
 * This package talks to the Maia computer-use runtime and streams
 * live session events instead of embedding a local automation engine.
 */

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
} from "./client";
export {
  buildRequestUrl,
  fetchApi,
  inferApiBase,
  inferUserId,
  normalizeApiBase,
  request,
  sanitizeUserId,
  withUserIdQuery,
} from "./core";
export type {
  ComputerUseActiveModelResponse,
  ComputerUseClient,
  ComputerUseClientConfig,
  ComputerUsePolicyResponse,
  ComputerUseSessionListRecord,
  ComputerUseSessionRecord,
  ComputerUseSLOSummaryResponse,
  ComputerUseStreamEvent,
  EventSourceLike,
  NavigateComputerUseSessionResponse,
  RequestLike,
  StartComputerUseSessionInput,
  StartComputerUseSessionResponse,
  StreamComputerUseSessionOptions,
} from "./types";
