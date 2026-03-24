// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";

import { tryFocusHighlight } from "./citationPdfPreviewFocus";

describe("citationPdfPreviewFocus", () => {
  it("prefers sentence-level evidence unit boxes over coarse external overlay rects", () => {
    const pageSurface = document.createElement("div");
    const applyOverlayRects = vi.fn();
    const scrollToOverlayRect = vi.fn();

    const result = tryFocusHighlight({
      targetPage: 126,
      appliedKey: "evidence-2",
      charStart: 60,
      charEnd: 100,
      evidenceUnits: [
        {
          text: "CAPEX for a gigafactory-scale solid-state line is ~35% higher.",
          charStart: 55,
          charEnd: 120,
          highlightBoxes: [{ x: 0.1, y: 0.28, width: 0.52, height: 0.05 }],
        },
      ],
      searchCandidates: ["CAPEX for a gigafactory-scale solid-state line is ~35% higher."],
      externalOverlayRects: [{ leftPct: 10, topPct: 5, widthPct: 40, heightPct: 8 }],
      pageSurfaceRefs: { current: { 126: pageSurface } },
      overlayRectsByPageRef: { current: {} },
      appliedHighlightKeyRef: { current: "" },
      clampPage: (value) => value,
      applyOverlayRects,
      scrollToOverlayRect,
    });

    expect(result).toBe(true);
    expect(applyOverlayRects).toHaveBeenCalledTimes(1);
    expect(applyOverlayRects).toHaveBeenCalledWith(
      126,
      expect.arrayContaining([expect.objectContaining({ topPct: 28 })]),
    );
    expect(scrollToOverlayRect).toHaveBeenCalledWith(
      expect.objectContaining({
        overlayRect: expect.objectContaining({ topPct: 28 }),
      }),
    );
  });
});
