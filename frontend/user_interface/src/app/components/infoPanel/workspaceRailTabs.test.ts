import { describe, expect, it } from "vitest";

import { normalizeWorkspaceRailTab } from "./workspaceRailTabs";

describe("normalizeWorkspaceRailTab", () => {
  it("maps known tab ids and defaults unknown to evidence", () => {
    expect(normalizeWorkspaceRailTab("work_graph")).toBe("work_graph");
    expect(normalizeWorkspaceRailTab("theatre")).toBe("theatre");
    expect(normalizeWorkspaceRailTab("artifacts")).toBe("artifacts");
    expect(normalizeWorkspaceRailTab("logs")).toBe("evidence");
    expect(normalizeWorkspaceRailTab("unknown")).toBe("evidence");
    expect(normalizeWorkspaceRailTab(null)).toBe("evidence");
  });
});
