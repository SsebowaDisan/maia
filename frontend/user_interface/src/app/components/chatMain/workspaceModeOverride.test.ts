import { describe, expect, it } from "vitest";

import { normalizeRuntimeWorkspaceMode } from "./workspaceModeOverride";

describe("normalizeRuntimeWorkspaceMode", () => {
  it("maps UI mode tokens into runtime mode tokens", () => {
    expect(normalizeRuntimeWorkspaceMode("fast")).toBe("fast");
    expect(normalizeRuntimeWorkspaceMode("balanced")).toBe("balanced");
    expect(normalizeRuntimeWorkspaceMode("full")).toBe("full_theatre");
    expect(normalizeRuntimeWorkspaceMode("full_theatre")).toBe("full_theatre");
    expect(normalizeRuntimeWorkspaceMode("unknown")).toBe("balanced");
  });
});
