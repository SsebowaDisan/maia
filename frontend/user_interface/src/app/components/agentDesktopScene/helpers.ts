import type {
  BrowserFindState,
  DocumentHighlight,
  HighlightColor,
  HighlightPalette,
  HighlightRegion,
  PdfPlaybackState,
  ZoomHistoryEntry,
} from "./types";

function compactValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readStringList(value: unknown, limit = 12): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const cleaned = value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
  return Array.from(new Set(cleaned)).slice(0, Math.max(1, limit));
}

function toPercent(value: unknown, fallback: number) {
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(0, Math.min(100, Number(parsed)));
}

function normalizeHighlightColor(value: unknown): HighlightColor {
  return String(value || "yellow").trim().toLowerCase() === "green" ? "green" : "yellow";
}

function parseHighlightRegions(activeSceneData: Record<string, unknown>): HighlightRegion[] {
  if (!Array.isArray(activeSceneData["highlight_regions"])) {
    return [];
  }
  return activeSceneData["highlight_regions"]
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const keyword = String(row["keyword"] || "").trim();
      const color = normalizeHighlightColor(row["color"] || activeSceneData["highlight_color"]);
      const x = toPercent(row["x"], 0);
      const y = toPercent(row["y"], 0);
      const width = Math.max(1, toPercent(row["width"], 8));
      const height = Math.max(1, toPercent(row["height"], 3));
      return { keyword, color, x, y, width, height };
    })
    .filter((item): item is HighlightRegion => Boolean(item))
    .slice(0, 8);
}

function parseDocumentHighlights(activeSceneData: Record<string, unknown>): DocumentHighlight[] {
  if (!Array.isArray(activeSceneData["highlighted_words"])) {
    return [];
  }
  return activeSceneData["highlighted_words"]
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const word = String(row["word"] || "").trim();
      const snippet = String(row["snippet"] || "").trim();
      const color = normalizeHighlightColor(row["color"] || activeSceneData["highlight_color"]);
      if (!word && !snippet) {
        return null;
      }
      return { word, snippet, color };
    })
    .filter((item): item is DocumentHighlight => Boolean(item))
    .slice(0, 8);
}

function highlightPalette(color: HighlightColor): HighlightPalette {
  if (color === "green") {
    return {
      border: "rgba(112, 216, 123, 0.95)",
      fill: "rgba(112, 216, 123, 0.22)",
      labelBackground: "rgba(112, 216, 123, 0.95)",
      labelText: "#102915",
    };
  }
  return {
    border: "rgba(255, 213, 79, 0.95)",
    fill: "rgba(255, 213, 79, 0.22)",
    labelBackground: "rgba(255, 213, 79, 0.95)",
    labelText: "#2b2410",
  };
}

function asHttpUrl(value: string): string {
  return value.startsWith("http://") || value.startsWith("https://") ? value : "";
}

function parseBrowserFindState(
  activeSceneData: Record<string, unknown>,
  isBrowserScene: boolean,
  activeEventType: string,
  highlightRegions: HighlightRegion[],
): BrowserFindState {
  const semanticFindResults = parseSemanticFindResults(activeSceneData);
  const semanticTerms = semanticFindResults.map((item) => item.term);
  const browserKeywords = [
    ...semanticTerms,
    ...readStringList(activeSceneData["semantic_find_terms"], 10),
    ...readStringList(activeSceneData["highlighted_keywords"], 10),
    ...readStringList(activeSceneData["keywords"], 10),
  ];
  const dedupedBrowserKeywords = Array.from(new Set(browserKeywords)).slice(0, 10);
  const explicitFindQuery =
    compactValue(activeSceneData["semantic_find_query"]) || compactValue(activeSceneData["find_query"]);
  const findQuery = explicitFindQuery || dedupedBrowserKeywords.slice(0, 2).join(" ").trim();
  const matchCountRaw =
    typeof activeSceneData["semantic_find_match_count"] === "number"
      ? activeSceneData["semantic_find_match_count"]
      : typeof activeSceneData["match_count"] === "number"
        ? activeSceneData["match_count"]
        : Number(activeSceneData["semantic_find_match_count"] ?? activeSceneData["match_count"]);
  const findMatchCount = Number.isFinite(matchCountRaw)
    ? Math.max(0, Number(matchCountRaw))
    : Math.max(highlightRegions.length, semanticFindResults.length);
  const showFindOverlay =
    isBrowserScene &&
    Boolean(findQuery || dedupedBrowserKeywords.length || highlightRegions.length || semanticFindResults.length) &&
    (activeEventType === "browser_find_in_page" ||
      activeEventType === "browser_keyword_highlight" ||
      activeEventType === "browser_copy_selection" ||
      highlightRegions.length > 0 ||
      semanticFindResults.length > 0);

  return { dedupedBrowserKeywords, findMatchCount, findQuery, showFindOverlay, semanticFindResults };
}

function parseLiveCopiedWords(
  activeSceneData: Record<string, unknown>,
): { clipboardPreview: string; liveCopiedWords: string[]; liveCopiedWordsKey: string } {
  const clipboardPreview =
    typeof activeSceneData["clipboard_text"] === "string" ? activeSceneData["clipboard_text"] : "";
  const copiedWords = readStringList(activeSceneData["copied_words"], 8);
  const clipboardWords = clipboardPreview
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word.length > 0)
    .slice(0, 8);
  const liveCopiedWords = copiedWords.length ? copiedWords : clipboardWords;
  return {
    clipboardPreview,
    liveCopiedWords,
    liveCopiedWordsKey: liveCopiedWords.join("|"),
  };
}

function parseScrollPercent(value: unknown): number | null {
  const scrollPercentRaw = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(scrollPercentRaw)) {
    return null;
  }
  return Math.max(0, Math.min(100, Number(scrollPercentRaw)));
}

function parseSemanticFindResults(
  activeSceneData: Record<string, unknown>,
): Array<{ term: string; confidence: number }> {
  if (!Array.isArray(activeSceneData["semantic_find_results"])) {
    return [];
  }
  return activeSceneData["semantic_find_results"]
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const term = compactValue(row["term"] || row["query"] || row["text"]);
      const confidenceRaw = Number(row["confidence"] ?? row["score"]);
      if (!term || !Number.isFinite(confidenceRaw)) {
        return null;
      }
      return {
        term,
        confidence: Math.max(0, Math.min(1, Number(confidenceRaw.toFixed(3)))),
      };
    })
    .filter((item): item is { term: string; confidence: number } => Boolean(item))
    .slice(0, 8);
}

function parseZoomHistory(activeSceneData: Record<string, unknown>): ZoomHistoryEntry[] {
  if (!Array.isArray(activeSceneData["zoom_history"])) {
    return [];
  }
  return activeSceneData["zoom_history"]
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const row = item as Record<string, unknown>;
      const action = compactValue(row["action"]).toLowerCase();
      if (action !== "zoom_in" && action !== "zoom_out" && action !== "zoom_reset" && action !== "zoom_to_region") {
        return null;
      }
      const eventIndexRaw = Number(row["event_index"]);
      const eventIndex = Number.isFinite(eventIndexRaw) && eventIndexRaw > 0 ? Math.round(eventIndexRaw) : null;
      const zoomLevelRaw = Number(row["zoom_level"]);
      const zoomLevel = Number.isFinite(zoomLevelRaw) && zoomLevelRaw > 0 ? Number(zoomLevelRaw.toFixed(3)) : null;
      const zoomPolicyTriggers = readStringList(row["zoom_policy_triggers"], 8);
      return {
        eventRef: compactValue(row["event_ref"]),
        eventType: compactValue(row["event_type"]),
        eventIndex,
        timestamp: compactValue(row["timestamp"]),
        action: action as ZoomHistoryEntry["action"],
        sceneSurface: compactValue(row["scene_surface"]),
        sceneRef: compactValue(row["scene_ref"]),
        graphNodeId: compactValue(row["graph_node_id"]),
        zoomLevel,
        zoomReason: compactValue(row["zoom_reason"]),
        zoomPolicyTriggers,
      };
    })
    .filter((item): item is ZoomHistoryEntry => Boolean(item))
    .slice(-12);
}

function parseSheetState(sheetBodyPreview: string): { sheetPreviewRows: string[]; sheetStatusLine: string } {
  const rows = sheetBodyPreview
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return {
    sheetStatusLine: rows.slice(-1)[0] || "",
    sheetPreviewRows: rows.slice(-12),
  };
}

function parsePdfPlaybackState(
  activeSceneData: Record<string, unknown>,
  activeEventType: string,
): PdfPlaybackState {
  const parsePercent = (value: unknown): number | null => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    return Math.max(0, Math.min(100, parsed));
  };

  const parsePositiveInt = (value: unknown, fallback: number) => {
    const parsed = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(parsed)) {
      return fallback;
    }
    return Math.max(1, Math.round(parsed));
  };

  const fallbackPageFromLabel = () => {
    const pageLabel = compactValue(activeSceneData["page_label"]);
    const match = pageLabel.match(/\d+/);
    if (!match) {
      return 1;
    }
    const parsed = Number(match[0]);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return 1;
    }
    return Math.round(parsed);
  };

  const pdfPage = parsePositiveInt(
    activeSceneData["pdf_page"] ?? activeSceneData["page_index"],
    fallbackPageFromLabel(),
  );
  const pdfPageTotal = parsePositiveInt(
    activeSceneData["pdf_total_pages"] ?? activeSceneData["page_total"],
    pdfPage,
  );
  const scrollPercent = parseScrollPercent(
    activeSceneData["scroll_percent"] ?? activeSceneData["pdf_scroll_percent"],
  );
  const inferredPdfScrollPercent =
    pdfPageTotal <= 1 ? 0 : Math.max(0, Math.min(100, ((pdfPage - 1) / Math.max(1, pdfPageTotal - 1)) * 100));
  const normalizedDirection = String(activeSceneData["scroll_direction"] || "")
    .trim()
    .toLowerCase();
  const pdfScrollDirection: "up" | "down" | "" =
    normalizedDirection === "up" || normalizedDirection === "down"
      ? (normalizedDirection as "up" | "down")
      : "";
  const pdfScanRegion = compactValue(activeSceneData["scan_region"]);
  const zoomHistory = parseZoomHistory(activeSceneData);
  const latestZoom = zoomHistory.length ? zoomHistory[zoomHistory.length - 1] : null;
  const pdfZoomLevelRaw = Number(activeSceneData["pdf_zoom_level"] ?? activeSceneData["zoom_level"]);
  const pdfZoomLevel =
    Number.isFinite(pdfZoomLevelRaw) && pdfZoomLevelRaw > 0
      ? pdfZoomLevelRaw
      : latestZoom?.zoomLevel ?? null;
  const pdfZoomReason =
    compactValue(activeSceneData["zoom_reason"]) ||
    compactValue(latestZoom?.zoomReason) ||
    compactValue(activeSceneData["scan_reason"]) ||
    compactValue(activeSceneData["reason"]);

  const targetRegion =
    activeSceneData["target_region"] && typeof activeSceneData["target_region"] === "object"
      ? (activeSceneData["target_region"] as Record<string, unknown>)
      : {};
  const regionX = parsePercent(targetRegion["x"] ?? activeSceneData["region_x"]);
  const regionY = parsePercent(targetRegion["y"] ?? activeSceneData["region_y"]);
  const regionWidth = parsePercent(targetRegion["width"] ?? activeSceneData["region_width"]);
  const regionHeight = parsePercent(targetRegion["height"] ?? activeSceneData["region_height"]);
  const pdfTargetRegion =
    regionX !== null &&
    regionY !== null &&
    regionWidth !== null &&
    regionHeight !== null &&
    regionWidth > 0 &&
    regionHeight > 0
      ? {
          keyword: compactValue(targetRegion["label"]) || "focus region",
          color: "yellow" as const,
          x: regionX,
          y: regionY,
          width: regionWidth,
          height: regionHeight,
        }
      : null;

  const normalizedEventType = String(activeEventType || "").trim().toLowerCase();
  const compareMode =
    activeSceneData["compare_mode"] && typeof activeSceneData["compare_mode"] === "object"
      ? (activeSceneData["compare_mode"] as Record<string, unknown>)
      : {};
  const compareLeft =
    compactValue(activeSceneData["compare_left"]) ||
    compactValue(activeSceneData["compare_region_a"]) ||
    compactValue(activeSceneData["compare_a"]) ||
    compactValue(compareMode["left"]) ||
    compactValue(compareMode["region_a"]);
  const compareRight =
    compactValue(activeSceneData["compare_right"]) ||
    compactValue(activeSceneData["compare_region_b"]) ||
    compactValue(activeSceneData["compare_b"]) ||
    compactValue(compareMode["right"]) ||
    compactValue(compareMode["region_b"]);
  const hasCompareEvent =
    normalizedEventType === "pdf_compare_regions" || normalizedEventType === "pdf.compare_regions";
  const pdfCompareLeft = hasCompareEvent ? compareLeft || "Region A" : compareLeft;
  const pdfCompareRight = hasCompareEvent ? compareRight || "Region B" : compareRight;
  const pdfCompareVerdict =
    compactValue(activeSceneData["compare_verdict"]) || compactValue(compareMode["verdict"]);

  const pdfFindQuery =
    compactValue(activeSceneData["semantic_find_query"]) ||
    compactValue(activeSceneData["pdf_find_query"]) ||
    compactValue(activeSceneData["find_query"]);
  const pdfSemanticFindResults = parseSemanticFindResults(activeSceneData);
  const pdfFindMatchCountRaw = Number(
    activeSceneData["pdf_find_match_count"] ??
      activeSceneData["semantic_find_match_count"] ??
      activeSceneData["match_count"],
  );
  const pdfFindMatchCount = Number.isFinite(pdfFindMatchCountRaw)
    ? Math.max(0, Math.round(pdfFindMatchCountRaw))
    : pdfSemanticFindResults.length;

  return {
    pdfPage,
    pdfPageTotal: Math.max(pdfPage, pdfPageTotal),
    pdfScrollPercent: scrollPercent ?? inferredPdfScrollPercent,
    pdfScrollDirection,
    pdfScanRegion,
    pdfZoomLevel,
    pdfZoomReason,
    pdfTargetRegion,
    pdfCompareLeft,
    pdfCompareRight,
    pdfCompareVerdict,
    pdfFindQuery,
    pdfFindMatchCount,
    pdfSemanticFindResults,
    zoomHistory,
  };
}

export {
  asHttpUrl,
  compactValue,
  highlightPalette,
  parseBrowserFindState,
  parseDocumentHighlights,
  parseHighlightRegions,
  parseLiveCopiedWords,
  parsePdfPlaybackState,
  parseSemanticFindResults,
  parseScrollPercent,
  parseSheetState,
  parseZoomHistory,
};
