import {
  inferApiBase,
  inferUserId,
  request,
  withUserIdQuery,
} from "./core";
import type {
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
} from "./types";

function isNotFoundError(error: unknown): boolean {
  const message =
    error instanceof Error ? String(error.message || "") : String(error || "");
  const normalized = message.trim().toLowerCase();
  return normalized.includes("404") || normalized.includes("not found");
}

function createComputerUseClient(config: ComputerUseClientConfig = {}): ComputerUseClient {
  const resolvedBase = inferApiBase(config.apiBase);
  const resolvedUserId = inferUserId(config.userId);
  const baseConfig: ComputerUseClientConfig = {
    ...config,
    apiBase: resolvedBase,
    userId: resolvedUserId,
  };

  return {
    startSession(body: StartComputerUseSessionInput) {
      const requestId = String(body.requestId || "").trim();
      const query = requestId
        ? `?request_id=${encodeURIComponent(requestId)}`
        : "";
      return request<StartComputerUseSessionResponse>(
        baseConfig,
        `/api/computer-use/sessions${query}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: body.url }),
        },
      );
    },

    getSession(sessionId: string) {
      return request<ComputerUseSessionRecord>(
        baseConfig,
        `/api/computer-use/sessions/${encodeURIComponent(sessionId)}`,
      );
    },

    listSessions() {
      return request<ComputerUseSessionListRecord[]>(
        baseConfig,
        "/api/computer-use/sessions",
      );
    },

    navigateSession(sessionId: string, url: string) {
      return request<NavigateComputerUseSessionResponse>(
        baseConfig,
        `/api/computer-use/sessions/${encodeURIComponent(sessionId)}/navigate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url }),
        },
      );
    },

    cancelSession(sessionId: string) {
      return request<void>(
        baseConfig,
        `/api/computer-use/sessions/${encodeURIComponent(sessionId)}`,
        {
          method: "DELETE",
        },
      );
    },

    getActiveModel() {
      return request<ComputerUseActiveModelResponse>(
        baseConfig,
        "/api/computer-use/active-model",
      ).catch(async (error) => {
        if (!isNotFoundError(error)) {
          throw error;
        }
        const settings = await request<{ values?: Record<string, unknown> }>(
          baseConfig,
          "/api/settings",
        );
        const override = String(
          settings?.values?.["agent.computer_use_model"] || "",
        ).trim();
        if (override) {
          return {
            model: override,
            source: "settings:agent.computer_use_model",
          };
        }
        return {
          model: "qwen2.5vl:7b",
          source: "default:open_source",
        };
      });
    },

    getPolicy() {
      return request<ComputerUsePolicyResponse>(
        baseConfig,
        "/api/computer-use/policy",
      );
    },

    getSLOSummary(windowSeconds?: number) {
      const query =
        typeof windowSeconds === "number" && Number.isFinite(windowSeconds)
          ? `?window_seconds=${encodeURIComponent(String(Math.round(windowSeconds)))}`
          : "";
      return request<ComputerUseSLOSummaryResponse>(
        baseConfig,
        `/api/computer-use/slo/summary${query}`,
      );
    },

    streamSession(
      sessionId: string,
      { task, model, maxIterations, runId, onEvent, onDone, onError }: StreamComputerUseSessionOptions,
    ) {
      const query = new URLSearchParams();
      query.set("task", task);
      if (model) {
        query.set("model", model);
      }
      if (
        typeof maxIterations === "number" &&
        Number.isFinite(maxIterations) &&
        maxIterations > 0
      ) {
        query.set("max_iterations", String(Math.round(maxIterations)));
      }
      if (runId) {
        query.set("run_id", runId);
      }

      const EventSourceCtor = config.eventSource || globalThis.EventSource;
      if (typeof EventSourceCtor !== "function") {
        throw new Error("No EventSource implementation available for Maia computer-use stream.");
      }

      const basePath = `/api/computer-use/sessions/${encodeURIComponent(sessionId)}/stream?${query.toString()}`;
      const eventSource = new EventSourceCtor(
        `${resolvedBase}${withUserIdQuery(basePath, resolvedUserId)}`,
      );
      let closed = false;

      eventSource.onmessage = (message) => {
        if (closed) {
          return;
        }
        const chunk = String(message.data || "").trim();
        if (!chunk) {
          return;
        }
        if (chunk === "[DONE]") {
          closed = true;
          eventSource.close();
          onDone?.();
          return;
        }
        try {
          onEvent?.(JSON.parse(chunk) as ComputerUseStreamEvent);
        } catch {
          // Ignore malformed chunks and keep the stream alive.
        }
      };

      eventSource.onerror = () => {
        if (closed) {
          return;
        }
        closed = true;
        eventSource.close();
        onError?.(new Error("Maia computer-use stream disconnected."));
      };

      return () => {
        closed = true;
        eventSource.close();
      };
    },
  };
}

const defaultComputerUseClient = createComputerUseClient();

const startComputerUseSession = defaultComputerUseClient.startSession;
const getComputerUseSession = defaultComputerUseClient.getSession;
const listComputerUseSessions = defaultComputerUseClient.listSessions;
const navigateComputerUseSession = defaultComputerUseClient.navigateSession;
const cancelComputerUseSession = defaultComputerUseClient.cancelSession;
const getComputerUseActiveModel = defaultComputerUseClient.getActiveModel;
const getComputerUsePolicy = defaultComputerUseClient.getPolicy;
const getComputerUseSLOSummary = defaultComputerUseClient.getSLOSummary;
const streamComputerUseSession = defaultComputerUseClient.streamSession;

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
};
