import type { WorkflowDefinition, WorkflowRunEvent } from "../../../api/client/types";
import type { WorkflowCanvasNodeRunState } from "../../stores/workflowStore";

type RunStoreStreamActions = {
  startRun: (runId: string) => void;
  setRunStatus: (status: "idle" | "running" | "completed" | "failed") => void;
  setRunDetail: (detail: string) => void;
  setActiveStep: (stepId: string | null) => void;
  setNodeRunState: (nodeId: string, runState: WorkflowCanvasNodeRunState, detail?: string) => void;
  appendStepOutput: (stepId: string, outputChunk: string) => void;
  setStepResult: (stepId: string, output: string, durationMs?: number) => void;
};

function toRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function toText(value: unknown): string {
  return String(value || "").trim();
}

function readEventData(event: WorkflowRunEvent): Record<string, unknown> {
  return toRecord((event as Record<string, unknown>).data);
}

function readEventType(event: WorkflowRunEvent): string {
  return toText((event as Record<string, unknown>).event_type).toLowerCase();
}

function readRunId(event: WorkflowRunEvent): string {
  const eventMap = event as Record<string, unknown>;
  const data = readEventData(event);
  return toText(eventMap.run_id || data.run_id);
}

function readWorkflowId(event: WorkflowRunEvent): string {
  const eventMap = event as Record<string, unknown>;
  const data = readEventData(event);
  return toText(eventMap.workflow_id || data.workflow_id);
}

function readStepId(event: WorkflowRunEvent): string {
  const eventMap = event as Record<string, unknown>;
  const data = readEventData(event);
  return toText(eventMap.step_id || data.step_id);
}

function readDetail(event: WorkflowRunEvent): string {
  const eventMap = event as Record<string, unknown>;
  const data = readEventData(event);
  return toText(eventMap.detail || eventMap.error || data.detail || data.error || eventMap.message);
}

function readDefinition(event: WorkflowRunEvent): WorkflowDefinition | null {
  const data = readEventData(event);
  const raw = data.definition;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const parsed = raw as Record<string, unknown>;
  if (!Array.isArray(parsed.steps) || !Array.isArray(parsed.edges)) {
    return null;
  }
  return raw as WorkflowDefinition;
}

function formatAssembleRunLogLine(event: WorkflowRunEvent): string {
  const eventMap = event as Record<string, unknown>;
  const eventType = readEventType(event);
  const title = toText(eventMap.title);
  const detail = readDetail(event);
  if (title && detail) {
    return `[${eventType}] ${title}: ${detail}`;
  }
  if (title) {
    return `[${eventType}] ${title}`;
  }
  if (detail) {
    return `[${eventType}] ${detail}`;
  }
  return `[${eventType}]`;
}

function applyAssembleRunEventToStore(event: WorkflowRunEvent, actions: RunStoreStreamActions): void {
  const eventType = readEventType(event);
  const eventMap = event as Record<string, unknown>;
  const runId = readRunId(event);
  const stepId = readStepId(event);
  const detail = readDetail(event);

  if (eventType === "run_started" || eventType === "workflow_started") {
    if (runId) {
      actions.startRun(runId);
    }
    actions.setRunStatus("running");
    return;
  }

  if (eventType === "execution_starting") {
    if (runId) {
      actions.startRun(runId);
    }
    actions.setRunStatus("running");
    return;
  }

  if (eventType === "workflow_step_started") {
    if (stepId) {
      actions.setActiveStep(stepId);
      actions.setNodeRunState(stepId, "running");
    }
    return;
  }

  if (eventType === "workflow_step_progress") {
    const delta = toText(eventMap.delta || readEventData(event).delta);
    if (stepId && delta) {
      actions.appendStepOutput(stepId, delta);
    }
    return;
  }

  if (eventType === "workflow_step_completed") {
    const duration = Number(eventMap.duration_ms || readEventData(event).duration_ms || 0);
    const preview = toText(eventMap.result_preview || readEventData(event).result_preview);
    if (stepId) {
      actions.setNodeRunState(stepId, "completed", preview);
      actions.setStepResult(stepId, preview, Number.isFinite(duration) ? duration : 0);
    }
    actions.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_step_failed") {
    if (stepId) {
      actions.setNodeRunState(stepId, "failed", detail);
    }
    if (detail) {
      actions.setRunDetail(detail);
    }
    return;
  }

  if (eventType === "workflow_step_skipped") {
    if (stepId) {
      actions.setNodeRunState(stepId, "skipped", detail);
    }
    return;
  }

  if (eventType === "workflow_completed" || eventType === "execution_complete") {
    actions.setRunStatus("completed");
    actions.setActiveStep(null);
    return;
  }

  if (
    eventType === "workflow_failed" ||
    eventType === "execution_error" ||
    eventType === "assembly_error" ||
    eventType === "error" ||
    eventType === "budget_exceeded"
  ) {
    actions.setRunStatus("failed");
    if (detail) {
      actions.setRunDetail(detail);
    }
  }
}

function readWorkflowIdFromAssembleRunEvent(event: WorkflowRunEvent): string {
  return readWorkflowId(event);
}

function readDefinitionFromAssembleRunEvent(event: WorkflowRunEvent): WorkflowDefinition | null {
  return readDefinition(event);
}

export {
  applyAssembleRunEventToStore,
  formatAssembleRunLogLine,
  readDefinitionFromAssembleRunEvent,
  readRunId,
  readWorkflowIdFromAssembleRunEvent,
};
export type { RunStoreStreamActions };
