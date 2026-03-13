import { describe, expect, it } from "vitest";

import { buildSearchCandidates, findRangeByCharOffsets } from "./citationPdfHighlight";

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

  it("prioritizes the first complete sentence as the first search candidate", () => {
    const rawText =
      "First sentence has unique evidence signal. Second sentence is much longer and contains many extra descriptive words to dominate by length.";
    const candidates = buildSearchCandidates(rawText);
    expect(candidates[0]).toBe("first sentence has unique evidence signal");
  });
});
