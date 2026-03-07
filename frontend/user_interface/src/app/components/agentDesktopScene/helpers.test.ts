import { describe, expect, it } from "vitest";

import {
  parseBrowserFindState,
  parseHighlightRegions,
  parsePdfPlaybackState,
  parseZoomHistory,
} from "./helpers";

describe("agentDesktopScene helpers", () => {
  it("parses browser highlight regions and enables semantic find overlay", () => {
    const activeSceneData: Record<string, unknown> = {
      highlighted_keywords: ["totals", "growth"],
      find_query: "totals growth",
      match_count: 3,
      highlight_regions: [
        {
          keyword: "totals",
          color: "yellow",
          x: 20,
          y: 30,
          width: 16,
          height: 6,
        },
      ],
    };
    const regions = parseHighlightRegions(activeSceneData);
    const state = parseBrowserFindState(
      activeSceneData,
      true,
      "browser_find_in_page",
      regions,
    );
    expect(regions).toHaveLength(1);
    expect(state.findQuery).toBe("totals growth");
    expect(state.findMatchCount).toBe(3);
    expect(state.showFindOverlay).toBe(true);
    expect(state.semanticFindResults).toEqual([]);
  });

  it("parses semantic find rankings for browser overlays", () => {
    const state = parseBrowserFindState(
      {
        semantic_find_query: "machine learning trends",
        semantic_find_match_count: 7,
        semantic_find_results: [
          { term: "machine learning trends", confidence: 0.94, rank: 1 },
          { term: "federated learning", confidence: 0.79, rank: 2 },
        ],
      },
      true,
      "browser_find_in_page",
      [],
    );
    expect(state.findQuery).toBe("machine learning trends");
    expect(state.findMatchCount).toBe(7);
    expect(state.semanticFindResults).toHaveLength(2);
    expect(state.semanticFindResults[0]?.term).toBe("machine learning trends");
    expect(state.showFindOverlay).toBe(true);
  });

  it("parses pdf zoom, region compare, and find metadata", () => {
    const state = parsePdfPlaybackState(
      {
        pdf_page: 3,
        pdf_total_pages: 12,
        scroll_percent: 42,
        scan_region: "Totals table",
        zoom_level: 1.45,
        zoom_reason: "Small text",
        target_region: { x: 24, y: 32, width: 20, height: 9, label: "totals block" },
        compare_left: "Q3 operating margin 18%",
        compare_right: "Q4 operating margin 22%",
        pdf_find_query: "operating margin",
        pdf_find_match_count: 4,
      },
      "pdf.compare_regions",
    );

    expect(state.pdfPage).toBe(3);
    expect(state.pdfPageTotal).toBe(12);
    expect(state.pdfScrollPercent).toBe(42);
    expect(state.pdfScanRegion).toBe("Totals table");
    expect(state.pdfZoomLevel).toBe(1.45);
    expect(state.pdfZoomReason).toBe("Small text");
    expect(state.pdfTargetRegion?.keyword).toBe("totals block");
    expect(state.pdfCompareLeft).toContain("Q3");
    expect(state.pdfCompareRight).toContain("Q4");
    expect(state.pdfFindQuery).toBe("operating margin");
    expect(state.pdfFindMatchCount).toBe(4);
    expect(state.pdfSemanticFindResults).toEqual([]);
    expect(state.zoomHistory).toHaveLength(0);
  });

  it("parses zoom history and links latest zoom reason into pdf playback", () => {
    const activeSceneData: Record<string, unknown> = {
      zoom_history: [
        {
          event_ref: "evt-4",
          event_type: "sheet.zoom_in",
          event_index: 4,
          action: "zoom_in",
          scene_surface: "google_sheets",
          scene_ref: "scene.sheet.main",
          graph_node_id: "node-sheet-4",
          zoom_level: 1.3,
          zoom_reason: "small target region",
          zoom_policy_triggers: ["target_region_small"],
        },
        {
          event_ref: "evt-8",
          event_type: "pdf_zoom_to_region",
          event_index: 8,
          action: "zoom_to_region",
          scene_surface: "document",
          scene_ref: "scene.pdf.reader",
          graph_node_id: "node-pdf-8",
          zoom_level: 2.1,
          zoom_reason: "verifier escalation",
          zoom_policy_triggers: ["verifier_escalation"],
        },
      ],
    };

    const zoomHistory = parseZoomHistory(activeSceneData);
    const state = parsePdfPlaybackState(activeSceneData, "pdf_zoom_to_region");
    expect(zoomHistory).toHaveLength(2);
    expect(zoomHistory[1]?.sceneRef).toBe("scene.pdf.reader");
    expect(zoomHistory[1]?.graphNodeId).toBe("node-pdf-8");
    expect(state.pdfZoomLevel).toBe(2.1);
    expect(state.pdfZoomReason).toBe("verifier escalation");
    expect(state.zoomHistory).toHaveLength(2);
  });
});
