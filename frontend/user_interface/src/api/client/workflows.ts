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

type LegacyWorkflowSummary = {
  workflow_id?: string;
  name?: string;
  description?: string;
  step_count?: number;
  edge_count?: number;
  definition?: WorkflowDefinition;
  date_created?: string | number | null;
  date_updated?: string | number | null;
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

function isNotFoundError(error: unknown): boolean {
  const message =
    error instanceof Error ? String(error.message || "") : String(error || "");
  const normalized = message.trim().toLowerCase();
  return normalized.includes("404") || normalized.includes("not found");
}

function toWorkflowRecordFromLegacy(
  row: LegacyWorkflowSummary,
  fallbackDefinition?: WorkflowDefinition,
): WorkflowRecord {
  const workflowId = String(
    row.workflow_id || row.definition?.workflow_id || fallbackDefinition?.workflow_id || "",
  ).trim();
  const workflowName = String(
    row.name || row.definition?.name || fallbackDefinition?.name || "Untitled workflow",
  ).trim() || "Untitled workflow";
  const definition: WorkflowDefinition =
    row.definition ||
    fallbackDefinition || {
      workflow_id: workflowId || `workflow_${Date.now()}`,
      name: workflowName,
      description: String(row.description || "").trim(),
      steps: [],
      edges: [],
    };
  return {
    id: workflowId || String(definition.workflow_id || "").trim() || workflowName,
    name: workflowName,
    description: String(row.description || definition.description || "").trim(),
    definition,
    created_at:
      typeof row.date_created === "number"
        ? row.date_created
        : Number.isFinite(Number(row.date_created))
          ? Number(row.date_created)
          : undefined,
    updated_at:
      typeof row.date_updated === "number"
        ? row.date_updated
        : Number.isFinite(Number(row.date_updated))
          ? Number(row.date_updated)
          : undefined,
  };
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
  return request<WorkflowRecord[]>("/api/workflows").catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyRows = await request<LegacyWorkflowSummary[]>("/api/agents/workflows");
    return (legacyRows || []).map((row) => toWorkflowRecordFromLegacy(row));
  });
}

function getWorkflowRecord(workflowId: string) {
  return request<WorkflowRecord>(`/api/workflows/${encodeURIComponent(workflowId)}`).catch(
    async (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      const legacyRow = await request<LegacyWorkflowSummary>(
        `/api/agents/workflows/${encodeURIComponent(workflowId)}`,
      );
      return toWorkflowRecordFromLegacy(legacyRow);
    },
  );
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
  }).catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyRow = await request<LegacyWorkflowSummary>("/api/agents/workflows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload.definition),
    });
    return toWorkflowRecordFromLegacy(legacyRow, payload.definition);
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
  }).catch(async (error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    const legacyRow = await request<LegacyWorkflowSummary>(
      `/api/agents/workflows/${encodeURIComponent(workflowId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload.definition),
      },
    );
    return toWorkflowRecordFromLegacy(legacyRow, payload.definition);
  });
}

async function removeWorkflowRecord(workflowId: string) {
  const response = await fetchApi(`/api/workflows/${encodeURIComponent(workflowId)}`, {
    method: "DELETE",
  });
  if (response.status === 404) {
    const legacy = await fetchApi(`/api/agents/workflows/${encodeURIComponent(workflowId)}`, {
      method: "DELETE",
    });
    if (legacy.ok || legacy.status === 204) {
      return;
    }
    const legacyDetail = normalizeErrorDetail(await legacy.text(), legacy.status, "Delete failed");
    throw new Error(legacyDetail);
  }
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
  return request<WorkflowTemplate[]>("/api/workflows/templates").catch((error) => {
    if (!isNotFoundError(error)) {
      throw error;
    }
    return [] as WorkflowTemplate[];
  });
}

async function runWorkflowWithStream(workflowId: string, options?: RunWorkflowStreamOptions) {
  let response = await fetchApi(`/api/workflows/${encodeURIComponent(workflowId)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      initial_inputs: options?.initialInputs || {},
    }),
  });
  if (response.status === 404) {
    response = await fetchApi(`/api/agents/workflows/${encodeURIComponent(workflowId)}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  }
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

function listWorkflowRunHistory(
  workflowId: string,
  options?: { limit?: number; offset?: number },
) {
  const query = new URLSearchParams();
  if (Number.isFinite(Number(options?.limit)) && Number(options?.limit) > 0) {
    query.set("limit", String(Math.max(1, Number(options?.limit))));
  }
  if (Number.isFinite(Number(options?.offset)) && Number(options?.offset) >= 0) {
    query.set("offset", String(Math.max(0, Number(options?.offset))));
  }
  const queryString = query.toString();
  const path = `/api/workflows/${encodeURIComponent(workflowId)}/runs${queryString ? `?${queryString}` : ""}`;
  return request<WorkflowRunRecord[]>(path).catch(
    (error) => {
      if (!isNotFoundError(error)) {
        throw error;
      }
      return [] as WorkflowRunRecord[];
    },
  );
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
