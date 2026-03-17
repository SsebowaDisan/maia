import { API_BASE, request, withUserIdQuery } from "./core";

type StartComputerUseSessionInput = {
  url: string;
  requestId?: string;
};

type StartComputerUseSessionResponse = {
  session_id: string;
  url: string;
};

type ComputerUseSessionRecord = {
  session_id: string;
  url: string;
  viewport?: Record<string, unknown>;
};

type ComputerUseSessionListRecord = {
  session_id: string;
  user_id: string;
  start_url: string;
  status: "active" | "closed" | "stale";
  live: boolean;
  date_created: string;
  date_closed: string | null;
};

type NavigateComputerUseSessionResponse = {
  session_id: string;
  url: string;
  title: string;
};

type ComputerUseActiveModelResponse = {
  model: string;
  source: string;
};

type ComputerUseStreamEvent =
  | {
      event_type: "screenshot";
      iteration?: number;
      url?: string;
      screenshot_b64?: string;
    }
  | {
      event_type: "text";
      iteration?: number;
      text?: string;
    }
  | {
      event_type: "action";
      iteration?: number;
      action?: string;
      input?: Record<string, unknown>;
      tool_id?: string;
    }
  | {
      event_type: "done" | "max_iterations";
      iteration?: number;
      url?: string;
    }
  | {
      event_type: "error";
      iteration?: number;
      detail?: string;
    };

type StreamComputerUseSessionOptions = {
  task: string;
  model?: string;
  maxIterations?: number;
  runId?: string;
  onEvent?: (event: ComputerUseStreamEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
};

function isNotFoundError(error: unknown): boolean {
  const message =
    error instanceof Error ? String(error.message || "") : String(error || "");
  const normalized = message.trim().toLowerCase();
  return normalized.includes("404") || normalized.includes("not found");
}

function startComputerUseSession(body: StartComputerUseSessionInput) {
  const requestId = String(body.requestId || "").trim();
  const query = requestId
    ? `?request_id=${encodeURIComponent(requestId)}`
    : "";
  return request<StartComputerUseSessionResponse>(`/api/computer-use/sessions${query}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: body.url }),
  });
}

function getComputerUseSession(sessionId: string) {
  return request<ComputerUseSessionRecord>(
    `/api/computer-use/sessions/${encodeURIComponent(sessionId)}`,
  );
}

function listComputerUseSessions() {
  return request<ComputerUseSessionListRecord[]>("/api/computer-use/sessions");
}

function navigateComputerUseSession(sessionId: string, url: string) {
  return request<NavigateComputerUseSessionResponse>(
    `/api/computer-use/sessions/${encodeURIComponent(sessionId)}/navigate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    },
  );
}

function cancelComputerUseSession(sessionId: string) {
  return request<void>(`/api/computer-use/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

function getComputerUseActiveModel() {
  return request<ComputerUseActiveModelResponse>("/api/computer-use/active-model").catch(
    async (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      const settings = await request<{ values?: Record<string, unknown> }>("/api/settings");
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
    },
  );
}

function streamComputerUseSession(
  sessionId: string,
  { task, model, maxIterations, runId, onEvent, onDone, onError }: StreamComputerUseSessionOptions,
) {
  const query = new URLSearchParams();
  query.set("task", task);
  if (model) {
    query.set("model", model);
  }
  if (typeof maxIterations === "number" && Number.isFinite(maxIterations) && maxIterations > 0) {
    query.set("max_iterations", String(Math.round(maxIterations)));
  }
  if (runId) {
    query.set("run_id", runId);
  }
  const basePath = `/api/computer-use/sessions/${encodeURIComponent(sessionId)}/stream?${query.toString()}`;
  const eventSource = new EventSource(`${API_BASE}${withUserIdQuery(basePath)}`);
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
      const parsed = JSON.parse(chunk) as ComputerUseStreamEvent;
      onEvent?.(parsed);
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
    onError?.(new Error("Computer Use SSE stream disconnected."));
  };

  return () => {
    closed = true;
    eventSource.close();
  };
}

export {
  cancelComputerUseSession,
  getComputerUseActiveModel,
  getComputerUseSession,
  listComputerUseSessions,
  navigateComputerUseSession,
  startComputerUseSession,
  streamComputerUseSession,
};
export type {
  ComputerUseActiveModelResponse,
  ComputerUseSessionListRecord,
  ComputerUseSessionRecord,
  ComputerUseStreamEvent,
  NavigateComputerUseSessionResponse,
  StartComputerUseSessionInput,
  StartComputerUseSessionResponse,
  StreamComputerUseSessionOptions,
};
