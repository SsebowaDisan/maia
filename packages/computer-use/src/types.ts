export type RequestLike = typeof fetch;
export type EventSourceLike = typeof EventSource;

export interface ComputerUseClientConfig {
  apiBase?: string;
  userId?: string | null;
  headers?: HeadersInit;
  fetch?: RequestLike;
  eventSource?: EventSourceLike;
}

export interface StartComputerUseSessionInput {
  url: string;
  requestId?: string;
}

export interface StartComputerUseSessionResponse {
  session_id: string;
  url: string;
}

export interface ComputerUseSessionRecord {
  session_id: string;
  url: string;
  viewport?: Record<string, unknown>;
}

export interface ComputerUseSessionListRecord {
  session_id: string;
  user_id: string;
  start_url: string;
  status: "active" | "closed" | "stale";
  live: boolean;
  date_created: string;
  date_closed: string | null;
}

export interface NavigateComputerUseSessionResponse {
  session_id: string;
  url: string;
  title: string;
}

export interface ComputerUseActiveModelResponse {
  model: string;
  source: string;
}

export interface ComputerUsePolicyResponse {
  mode: string;
  max_task_chars: number;
  blocked_terms_count: number;
  blocked_terms_preview: string[];
}

export interface ComputerUseSLOSummaryResponse {
  window_seconds: number;
  run_count: number;
  success_rate: number;
  error_rate: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  avg_latency_ms: number;
  avg_event_count: number;
  avg_action_count: number;
  status_counts: Record<string, number>;
}

export type ComputerUseStreamEvent =
  | {
      event_type: "started";
      iteration?: number;
      detail?: string;
      url?: string;
    }
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

export interface StreamComputerUseSessionOptions {
  task: string;
  model?: string;
  maxIterations?: number;
  runId?: string;
  onEvent?: (event: ComputerUseStreamEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
}

export interface ComputerUseClient {
  startSession: (body: StartComputerUseSessionInput) => Promise<StartComputerUseSessionResponse>;
  getSession: (sessionId: string) => Promise<ComputerUseSessionRecord>;
  listSessions: () => Promise<ComputerUseSessionListRecord[]>;
  navigateSession: (
    sessionId: string,
    url: string,
  ) => Promise<NavigateComputerUseSessionResponse>;
  cancelSession: (sessionId: string) => Promise<void>;
  getActiveModel: () => Promise<ComputerUseActiveModelResponse>;
  getPolicy: () => Promise<ComputerUsePolicyResponse>;
  getSLOSummary: (windowSeconds?: number) => Promise<ComputerUseSLOSummaryResponse>;
  streamSession: (
    sessionId: string,
    options: StreamComputerUseSessionOptions,
  ) => () => void;
}
