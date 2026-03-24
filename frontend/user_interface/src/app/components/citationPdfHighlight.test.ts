import { describe, expect, it } from "vitest";

import {
  buildSearchCandidates,
  findApproximateHighlightRange,
  normalizeSearchText,
  selectEvidenceUnitOverlayRects,
  type SpanSegment,
} from "./citationPdfHighlight";

function makeSegments(words: string[]): SpanSegment[] {
  let cursor = 0;
  return words.map((word) => {
    const start = cursor;
    cursor += word.length;
    const end = cursor;
    cursor += 1;
    return {
      node: {} as HTMLSpanElement,
      start,
      end,
      text: word,
    };
  });
}

describe("citationPdfHighlight", () => {
  it("finds an approximate range when exact text does not match", () => {
    const segments = makeSegments([
      "experimental",
      "procedure",
      "1",
      "5",
      "g",
      "of",
      "each",
      "crystalline",
      "sulfate",
      "hydrates",
      "of",
      "manganese",
      "ii",
      "to",
      "zinc",
      "ii",
      "were",
      "dissolved",
      "in",
      "10",
      "ml",
      "of",
      "water",
    ]);

    const range = findApproximateHighlightRange({
      segments,
      candidates: [
        "47Color Effects in Aqueous Systems Containing Divalent Metal Ions... 115 ExperimentalProcedure 1.5 g of each of the crystalline sulfate hydrates of manganese(II) to zinc(II) are dissolved in 10 mL of water",
      ],
    });

    expect(range).not.toBeNull();
    expect(range?.startIndex).toBeGreaterThanOrEqual(0);
    expect(range?.startIndex).toBeLessThan(12);
    expect((range?.endIndex || 0) - (range?.startIndex || 0)).toBeGreaterThanOrEqual(3);
  });

  it("prefers evidence unit boxes that overlap the cited sentence span", () => {
    const rects = selectEvidenceUnitOverlayRects({
      evidenceUnits: [
        {
          text: "Manufacturing readiness remains the largest bottleneck.",
          charStart: 0,
          charEnd: 54,
          highlightBoxes: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.05 }],
        },
        {
          text: "CAPEX for a gigafactory-scale solid-state line is ~35% higher.",
          charStart: 55,
          charEnd: 120,
          highlightBoxes: [{ x: 0.1, y: 0.28, width: 0.52, height: 0.05 }],
        },
      ],
      charStart: 60,
      charEnd: 100,
      candidates: ["CAPEX for a gigafactory-scale solid-state line is ~35% higher"],
    });

    expect(rects).toHaveLength(1);
    expect(rects[0]?.topPct).toBeCloseTo(28, 3);
  });

  it("prioritizes cited evidence text ahead of long prompt text", () => {
    const candidates = [
      ...buildSearchCandidates("CAPEX for a gigafactory-scale solid-state line is ~35% higher."),
      ...buildSearchCandidates(
        "Compare the alternatives, use only selected PDFs, explain manufacturing readiness and lifecycle economics in detail with citations and implications for commercialization.",
      ),
    ];

    expect(candidates[0]).toContain(
      normalizeSearchText("CAPEX for a gigafactory-scale solid-state line is ~35% higher."),
    );
  });

  it("finds an approximate range from a clause-sized scientific citation", () => {
    const segments = makeSegments([
      "capex",
      "for",
      "a",
      "gigafactory",
      "scale",
      "solid",
      "state",
      "line",
      "is",
      "35",
      "higher",
      "than",
      "for",
      "conventional",
      "li",
      "ion",
      "manufacturing",
    ]);

    const range = findApproximateHighlightRange({
      segments,
      candidates: ["CAPEX for a gigafactory-scale solid-state line is ~35% higher."],
    });

    expect(range).not.toBeNull();
    expect(range?.startIndex).toBe(0);
    expect(range?.endIndex).toBeGreaterThanOrEqual(7);
  });
});
