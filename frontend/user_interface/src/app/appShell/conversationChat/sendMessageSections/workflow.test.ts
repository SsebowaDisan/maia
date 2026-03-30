import { describe, expect, it } from "vitest";
import { summarizeBrainRun, toActivityEventFromWorkflowEvent } from "./workflow";

describe("toActivityEventFromWorkflowEvent", () => {
  it("preserves snapshot and scene references from workflow stream rows", () => {
    const event = toActivityEventFromWorkflowEvent(
      {
        event_type: "browser_open",
        run_id: "run-1",
        event_id: "evt-1",
        title: "Open source",
        detail: "Opening page",
        timestamp: "2026-03-29T03:00:00Z",
        data: {
          scene_surface: "website",
          snapshot_ref: ".maia_agent/browser_captures/source.png",
          scene_ref: "scene.browser.main",
          graph_node_id: "node-browser-1",
        },
      },
      { fallbackRunId: "fallback-run", index: 1 },
    );

    expect(event).toMatchObject({
      run_id: "run-1",
      event_id: "evt-1",
      timestamp: "2026-03-29T03:00:00Z",
      snapshot_ref: ".maia_agent/browser_captures/source.png",
      scene_ref: "scene.browser.main",
      graph_node_id: "node-browser-1",
    });
  });

  it("hydrates snapshot references from metadata when data is sparse", () => {
    const event = toActivityEventFromWorkflowEvent(
      {
        event_type: "web_result_opened",
        run_id: "run-2",
        metadata: {
          snapshot_ref: ".maia_agent/browser_captures/result.png",
          scene_ref: "scene.browser.result",
          graph_node_id: "node-result-1",
          timestamp: "2026-03-29T03:05:00Z",
        },
      },
      { fallbackRunId: "fallback-run", index: 2 },
    );

    expect(event).toMatchObject({
      timestamp: "2026-03-29T03:05:00Z",
      snapshot_ref: ".maia_agent/browser_captures/result.png",
      scene_ref: "scene.browser.result",
      graph_node_id: "node-result-1",
    });
  });

  it("preserves workflow outputs so Brain can summarize the final response", () => {
    const workflowCompleted = toActivityEventFromWorkflowEvent(
      {
        event_type: "workflow_completed",
        run_id: "run-3",
        data: {
          outputs: {
            output_step_1:
              "## Executive Summary\n- Findings are grounded in source evidence.\n\n## Evidence Citations\n- [1] https://example.org",
          },
        },
      },
      { fallbackRunId: "fallback-run", index: 3 },
    );

    expect(workflowCompleted?.data?.outputs).toEqual({
      output_step_1:
        "## Executive Summary\n- Findings are grounded in source evidence.\n\n## Evidence Citations\n- [1] https://example.org",
    });
    expect(summarizeBrainRun(workflowCompleted ? [workflowCompleted] : [])).toContain("## Executive Summary");
  });
});
