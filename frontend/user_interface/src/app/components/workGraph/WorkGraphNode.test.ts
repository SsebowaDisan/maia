import { describe, expect, it } from "vitest";

import { isLowConfidence, nodeTypeLabel, statusColor } from "./WorkGraphNode";

describe("WorkGraphNode helpers", () => {
  it("maps node types to readable labels", () => {
    expect(nodeTypeLabel("browser_action")).toBe("Browser");
    expect(nodeTypeLabel("verification")).toBe("Verification");
    expect(nodeTypeLabel("unknown_type")).toBe("Step");
  });

  it("returns low-confidence warnings under 0.6", () => {
    expect(isLowConfidence(0.55)).toBe(true);
    expect(isLowConfidence(0.6)).toBe(false);
    expect(isLowConfidence(null)).toBe(false);
  });

  it("uses deterministic status color mapping", () => {
    expect(statusColor("completed")).toBe("#16a34a");
    expect(statusColor("failed")).toBe("#dc2626");
    expect(statusColor("queued")).toBe("#6b7280");
  });
});

