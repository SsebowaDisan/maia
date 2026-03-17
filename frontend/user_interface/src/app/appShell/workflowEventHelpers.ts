import type { WorkflowRunEvent } from "../../api/client/types";
import { toast } from "sonner";
import { useWorkflowStore } from "../stores/workflowStore";

function resolveTargetStepId(preferredStepId: string): string | null {
  if (preferredStepId) {
    return preferredStepId;
  }
  const snapshot = useWorkflowStore.getState();
  if (snapshot.run.activeStepId) {
    return snapshot.run.activeStepId;
  }
  const runningNode = snapshot.nodes.find((node) => node.runState === "running");
  return runningNode?.id || null;
}

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
    store.setRunDetail(null);
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
    store.setNodeRunState(stepId, "failed", errorText);
    store.setStepResult(stepId, errorText, 0);
    store.setRunDetail(errorText);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_step_skipped" && stepId) {
    const reason = String((event as { reason?: string }).reason || "").trim();
    const detail = reason || "Step skipped";
    store.setNodeRunState(stepId, "skipped", detail);
    store.setStepResult(stepId, detail, 0);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_completed") {
    store.setRunStatus("completed");
    store.setRunDetail(null);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "workflow_failed") {
    const errorText = String((event as { error?: string }).error || "Workflow failed");
    const failedStepId = resolveTargetStepId(
      String((event as { failed_step_id?: string | null }).failed_step_id || "").trim(),
    );
    if (failedStepId) {
      store.setNodeRunState(failedStepId, "failed", errorText);
      store.setStepResult(failedStepId, errorText, 0);
    }
    store.setRunStatus("failed");
    store.setRunDetail(errorText);
    store.setActiveStep(null);
    return;
  }

  if (eventType === "budget_exceeded") {
    const detail = String(
      (event as { detail?: string }).detail || "Budget exceeded. Workflow run stopped.",
    ).trim();
    const targetStepId = resolveTargetStepId(stepId);
    if (targetStepId) {
      store.setNodeRunState(targetStepId, "blocked", detail);
      store.setStepResult(targetStepId, detail, 0);
    }
    store.setRunStatus("failed");
    store.setRunDetail(detail);
    store.setActiveStep(null);
    toast.warning(detail);
    return;
  }

  if (eventType === "error") {
    const detail = String((event as { detail?: string }).detail || "Workflow run failed.").trim();
    const targetStepId = resolveTargetStepId(stepId);
    if (targetStepId) {
      store.setNodeRunState(targetStepId, "blocked", detail);
      store.setStepResult(targetStepId, detail, 0);
    }
    store.setRunStatus("failed");
    store.setRunDetail(detail);
    store.setActiveStep(null);
    toast.error(detail);
  }
}

export { applyWorkflowRunEvent };
