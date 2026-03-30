import { describe, expect, it } from "vitest";

import { initialReplayCursor } from "./ReplayControls";

describe("initialReplayCursor", () => {
  it("opens completed runs on the latest event", () => {
    expect(initialReplayCursor(0)).toBe(0);
    expect(initialReplayCursor(1)).toBe(0);
    expect(initialReplayCursor(5)).toBe(4);
  });
});
