import { describe, expect, it } from "vitest";

import { resolveApiScene } from "./api_scene_registry";
import type { ApiSceneState } from "./api_scene_state";

function createState(overrides: Partial<ApiSceneState>): ApiSceneState {
  return {
    isApiScene: true,
    connectorId: "",
    connectorLabel: "",
    brandSlug: "",
    sceneFamily: "api",
    objectType: "",
    objectId: "",
    operationLabel: "",
    summaryText: "",
    statusLabel: "",
    approvalRequired: false,
    approvalReason: "",
    fieldDiffs: [],
    validations: [],
    ...overrides,
  };
}

describe("resolveApiScene", () => {
  it("routes Gmail scenes", () => {
    const result = resolveApiScene(
      createState({
        connectorId: "gmail",
        brandSlug: "gmail",
        sceneFamily: "email",
      }),
    );
    expect(result).toEqual({ kind: "clone", variant: "gmail" });
  });

  it("routes Excel scenes", () => {
    const result = resolveApiScene(
      createState({
        connectorId: "m365",
        brandSlug: "excel",
        operationLabel: "excel.update_cells",
        sceneFamily: "sheet",
      }),
    );
    expect(result).toEqual({ kind: "clone", variant: "excel" });
  });

  it("falls back to generic for unknown connector", () => {
    const result = resolveApiScene(
      createState({
        connectorId: "unknown_vendor",
        brandSlug: "unknown_vendor",
      }),
    );
    expect(result).toEqual({ kind: "generic" });
  });
});
