import { fetchApi, request } from "../core";
import type { WorkflowDefinitionInput, WorkflowRunEvent, WorkflowRunStreamOptions, WorkflowSummaryRecord } from "./types";

function createWorkflow(definition: WorkflowDefinitionInput) {
  return request<WorkflowSummaryRecord>("/api/agents/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

function listWorkflows() {
  return request<WorkflowSummaryRecord[]>("/api/agents/workflows");
}

function updateWorkflow(workflowId: string, definition: WorkflowDefinitionInput) {
  return request<WorkflowSummaryRecord>(`/api/agents/workflows/${encodeURIComponent(workflowId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
}

function parseWorkflowSseBlock(block: string): WorkflowRunEvent | null {
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
    return { event_type: "done" };
  }
  try {
    return JSON.parse(dataText) as WorkflowRunEvent;
  } catch {
    return { event_type: "message", detail: dataText };
  }
}

async function runWorkflow(workflowId: string, options?: WorkflowRunStreamOptions) {
  const response = await fetchApi(`/api/agents/workflows/${encodeURIComponent(workflowId)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    const detail = (await response.text()).trim();
    throw new Error(detail || `Workflow run failed: ${response.status}`);
  }
  if (!response.body) {
    throw new Error("No workflow stream body returned by backend.");
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
        const parsed = parseWorkflowSseBlock(block);
        if (!parsed) {
          continue;
        }
        if (parsed.event_type === "done") {
          options?.onDone?.();
          continue;
        }
        options?.onEvent?.(parsed);
      }
    }
    if (buffer.trim()) {
      const parsed = parseWorkflowSseBlock(buffer);
      if (parsed?.event_type === "done") {
        options?.onDone?.();
      } else if (parsed) {
        options?.onEvent?.(parsed);
      }
    }
  } catch (error) {
    options?.onError?.(error instanceof Error ? error : new Error(String(error)));
    throw error;
  }
}

export { createWorkflow, listWorkflows, parseWorkflowSseBlock, runWorkflow, updateWorkflow };
