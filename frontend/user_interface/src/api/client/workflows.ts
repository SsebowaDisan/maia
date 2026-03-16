import { fetchApi, request } from "./core";
import type {
  WorkflowDefinition,
  WorkflowGenerateStreamEvent,
  WorkflowRecord,
  WorkflowRunEvent,
  WorkflowRunRecord,
  WorkflowTemplate,
  WorkflowValidationResponse,
} from "./types";

type SaveWorkflowPayload = {
  name: string;
  description?: string;
  definition: WorkflowDefinition;
};

type RunWorkflowStreamOptions = {
  initialInputs?: Record<string, unknown>;
  onEvent?: (event: WorkflowRunEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
};

type GenerateWorkflowStreamOptions = {
  maxSteps?: number;
  onEvent?: (event: WorkflowGenerateStreamEvent) => void;
  onDone?: () => void;
  onError?: (error: Error) => void;
};

function parseSseBlock<TEvent extends { event_type: string }>(block: string): TEvent | null {
  const lines = block
    .split("\n")
    .map((line) => line.trimEnd())
    .filter(Boolean);
  if (!lines.length) {
    return null;
  }
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  const dataText = dataLines.join("\n");
  if (!dataText || dataText === "[DONE]") {
    return { event_type: "done" } as TEvent;
  }
  try {
    return JSON.parse(dataText) as TEvent;
  } catch {
    return { event_type: "message", detail: dataText } as TEvent;
  }
}

function normalizeErrorDetail(text: string, status: number, fallbackLabel: string): string {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return `${fallbackLabel}: ${status}`;
  }
  try {
    const parsed = JSON.parse(trimmed) as { detail?: string };
    const detail = String(parsed.detail || "").trim();
    if (detail) {
      return detail;
    }
  } catch {
    // Keep raw body text.
  }
  return trimmed;
}

async function consumeSseStream<TEvent extends { event_type: string }>(
  response: Response,
  options: {
    onEvent?: (event: TEvent) => void;
    onDone?: () => void;
    onError?: (error: Error) => void;
  },
) {
  if (!response.body) {
    throw new Error("No stream body returned by backend.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const read = await reader.read();
      if (read.done) {
        break;
      }
      buffer += decoder.decode(read.value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const parsed = parseSseBlock<TEvent>(block);
        if (!parsed) {
          continue;
        }
        if (parsed.event_type === "done") {
          options.onDone?.();
          continue;
        }
        options.onEvent?.(parsed);
      }
    }
    if (buffer.trim()) {
      const parsed = parseSseBlock<TEvent>(buffer);
      if (parsed?.event_type === "done") {
        options.onDone?.();
      } else if (parsed) {
        options.onEvent?.(parsed);
      }
    }
  } catch (error) {
    const normalized = error instanceof Error ? error : new Error(String(error));
    options.onError?.(normalized);
    throw normalized;
  }
}

function listWorkflowRecords() {
  return request<WorkflowRecord[]>("/api/workflows");
}

function getWorkflowRecord(workflowId: string) {
  return request<WorkflowRecord>(`/api/workflows/${encodeURIComponent(workflowId)}`);
}

function createWorkflowRecord(payload: SaveWorkflowPayload) {
  return request<WorkflowRecord>("/api/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: payload.name,
      description: payload.description || "",
      definition: payload.definition,
    }),
  });
}

function updateWorkflowRecord(workflowId: string, payload: SaveWorkflowPayload) {
  return request<WorkflowRecord>(`/api/workflows/${encodeURIComponent(workflowId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: payload.name,
      description: payload.description || "",
      definition: payload.definition,
    }),
  });
}

async function removeWorkflowRecord(workflowId: string) {
  const response = await fetchApi(`/api/workflows/${encodeURIComponent(workflowId)}`, {
    method: "DELETE",
  });
  if (response.ok || response.status === 204) {
    return;
  }
  const detail = normalizeErrorDetail(await response.text(), response.status, "Delete failed");
  throw new Error(detail);
}

function validateWorkflowDefinition(definition: WorkflowDefinition) {
  return request<WorkflowValidationResponse>("/api/workflows/validate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ definition }),
  });
}

function generateWorkflowFromDescription(description: string, maxSteps = 8) {
  return request<{ definition: WorkflowDefinition }>("/api/workflows/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      description,
      max_steps: maxSteps,
    }),
  });
}

function listWorkflowTemplates() {
  return request<WorkflowTemplate[]>("/api/workflows/templates");
}

async function runWorkflowWithStream(workflowId: string, options?: RunWorkflowStreamOptions) {
  const response = await fetchApi(`/api/workflows/${encodeURIComponent(workflowId)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      initial_inputs: options?.initialInputs || {},
    }),
  });
  if (!response.ok) {
    const detail = normalizeErrorDetail(await response.text(), response.status, "Workflow run failed");
    throw new Error(detail);
  }
  return consumeSseStream<WorkflowRunEvent>(response, {
    onEvent: options?.onEvent,
    onDone: options?.onDone,
    onError: options?.onError,
  });
}

function listWorkflowRunHistory(workflowId: string) {
  return request<WorkflowRunRecord[]>(`/api/workflows/${encodeURIComponent(workflowId)}/runs`);
}

function getWorkflowRunRecord(workflowId: string, runId: string) {
  return request<WorkflowRunRecord>(
    `/api/workflows/${encodeURIComponent(workflowId)}/runs/${encodeURIComponent(runId)}`,
  );
}

async function streamGenerateWorkflowFromDescription(
  description: string,
  options?: GenerateWorkflowStreamOptions,
) {
  const response = await fetchApi("/api/workflows/generate/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      description,
      max_steps: options?.maxSteps ?? 8,
    }),
  });
  if (!response.ok) {
    const detail = normalizeErrorDetail(await response.text(), response.status, "Workflow generation failed");
    throw new Error(detail);
  }
  return consumeSseStream<WorkflowGenerateStreamEvent>(response, {
    onEvent: options?.onEvent,
    onDone: options?.onDone,
    onError: options?.onError,
  });
}

export {
  createWorkflowRecord,
  generateWorkflowFromDescription,
  getWorkflowRecord,
  getWorkflowRunRecord,
  listWorkflowRecords,
  listWorkflowRunHistory,
  listWorkflowTemplates,
  removeWorkflowRecord,
  runWorkflowWithStream,
  streamGenerateWorkflowFromDescription,
  updateWorkflowRecord,
  validateWorkflowDefinition,
};

export type { GenerateWorkflowStreamOptions, RunWorkflowStreamOptions, SaveWorkflowPayload };
