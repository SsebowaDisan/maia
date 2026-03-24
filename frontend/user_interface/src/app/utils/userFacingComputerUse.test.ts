import { describe, expect, it } from "vitest";
import { sanitizeComputerUseText } from "./userFacingComputerUse";

describe("sanitizeComputerUseText", () => {
  it("removes leaked citation policy scaffolds from visible text", () => {
    expect(
      sanitizeComputerUseText(
        "Verify all [n] cite distinct sentences and domains before finalizing.",
      ),
    ).toBe("Verify citations before finalizing.");
  });

  it("replaces raw [n] placeholders in normal text", () => {
    expect(sanitizeComputerUseText("Use [n] citations inline.")).toBe(
      "Use citations inline.",
    );
  });
});
