import { describe, expect, it } from "vitest";

import { parseApiSceneState } from "./api_scene_state";

describe("parseApiSceneState", () => {
  it("detects API scene events and parses object cards with diffs", () => {
    const state = parseApiSceneState({
      activeSceneData: {
        scene_surface: "api",
        connector_id: "google_analytics",
        connector_label: "Google Analytics",
        object_type: "report",
        object_id: "rpt-2026-q1",
        operation_label: "Fetch quarterly report",
        action_status: "completed",
        field_diffs: [
          { field: "date_range", from: "Q4 2025", to: "Q1 2026" },
          { field: "metric", from: "sessions", to: "engaged_sessions" },
        ],
      },
      activeEventType: "api_call_completed",
      actionTargetLabel: "",
      actionStatus: "",
      sceneText: "",
      activeDetail: "",
    });
    expect(state.isApiScene).toBe(true);
    expect(state.connectorId).toBe("google_analytics");
    expect(state.fieldDiffs).toHaveLength(2);
    expect(state.operationLabel).toBe("Fetch quarterly report");
  });

  it("falls back gracefully for non-api events", () => {
    const state = parseApiSceneState({
      activeSceneData: {
        scene_surface: "browser",
      },
      activeEventType: "browser_navigate",
      actionTargetLabel: "",
      actionStatus: "",
      sceneText: "Working",
      activeDetail: "",
    });
    expect(state.isApiScene).toBe(false);
    expect(state.operationLabel).toBe("API operation");
    expect(state.summaryText).toBe("Working");
  });
});
