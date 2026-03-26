import { activity, envelope } from "./builders";
import type {
  ACPActivity,
} from "./types";
import type {
  ACPExecutionActivity,
  ACPExecutionEvent,
  ExecutionExtension,
} from "./execution-types";

function executionActivity(opts: {
  agentId: string;
  activity: ACPActivity["activity"];
  detail?: string;
  tool?: ACPActivity["tool"];
  browser?: ACPActivity["browser"];
  progress?: ACPActivity["progress"];
  cost?: ACPActivity["cost"];
  execution?: ExecutionExtension;
}): ACPExecutionActivity {
  const base = activity({
    agentId: opts.agentId,
    activity: opts.activity,
    detail: opts.detail,
    tool: opts.tool,
    browser: opts.browser,
    progress: opts.progress,
    cost: opts.cost,
  });
  return {
    ...base,
    execution: opts.execution,
  };
}

function executionEnvelope(
  agentId: string,
  runId: string,
  payload: ACPExecutionActivity,
  parentEventId?: string,
): ACPExecutionEvent {
  return envelope(agentId, runId, "event", payload, parentEventId) as ACPExecutionEvent;
}

export { executionActivity, executionEnvelope };
