import type { WorkflowRunEvent } from "../../api/client/types";
import { useWorkflowStore } from "../stores/workflowStore";

function applyWorkflowRunEvent(event: WorkflowRunEvent) {
  const eventType = String(event.event_type || "").trim().toLowerCase();
  if (!eventType) {
    return;
  }

  const store = useWorkflowStore.getState();
  const stepId = String((event as { step_id?: string }).step_id || "").trim();

  if (eventType === "run_started") {
    const runId = String((event as { run_id?: string }).run_id || "").trim();
    if (runId) {
      store.startRun(runId);
    }
    return;
  }

  if (eventType === "workflow_started") {
    store.setRunStatus("running");
    return;
  }

  if (eventType === "workflow_step_started" && stepId) {
    store.setActiveStep(stepId);
    store.setNodeRunState(stepId, "running");
    return;
  }

  if (eventType === "workflow_step_progress" && stepId) {
    const delta = String((event as { delta?: string }).delta || "");
    store.appendStepOutput(stepId, delta);
    return;
  }

  if (eventType === "workflow_step_completed" && stepId) {
    const preview = String((event as { result_preview?: string }).result_preview || "");
    const durationMs = Math.max(0, Number((event as { duration_ms?: number }).duration_ms || 0));
    store.setNodeRunState(stepId, "completed");
    store.setStepResult(stepId, preview, durationMs);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_step_failed" && stepId) {
    const errorText = String((event as { error?: string }).error || "Step failed");
    store.setNodeRunState(stepId, "failed");
    store.setStepResult(stepId, errorText, 0);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_step_skipped" && stepId) {
    store.setNodeRunState(stepId, "skipped");
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_completed") {
    store.setRunStatus("completed");
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_failed") {
    store.setRunStatus("failed");
    store.setActiveStep(null);
  }
}

export { applyWorkflowRunEvent };
