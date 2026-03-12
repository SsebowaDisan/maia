import { describe, expect, it } from "vitest";

import { findRangeByCharOffsets } from "./citationPdfHighlight";

describe("citationPdfHighlight", () => {
  it("reconstructs a span range from char offsets before fuzzy matching", () => {
    const range = findRangeByCharOffsets(
      [
        { node: {} as HTMLSpanElement, start: 0, end: 9, text: "machine" },
        { node: {} as HTMLSpanElement, start: 10, end: 20, text: "learning" },
        { node: {} as HTMLSpanElement, start: 21, end: 33, text: "workflow" },
      ],
      10,
      20,
    );
    expect(range).toEqual({ startIndex: 1, endIndex: 1 });
  });
});
