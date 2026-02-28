import type {
  BrowserFindState,
  DocumentHighlight,
  HighlightColor,
  HighlightPalette,
  HighlightRegion,
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
  const browserKeywords = [
    ...readStringList(activeSceneData["highlighted_keywords"], 10),
    ...readStringList(activeSceneData["keywords"], 10),
  ];
  const dedupedBrowserKeywords = Array.from(new Set(browserKeywords)).slice(0, 10);
  const explicitFindQuery = compactValue(activeSceneData["find_query"]);
  const findQuery = explicitFindQuery || dedupedBrowserKeywords.slice(0, 2).join(" ").trim();
  const matchCountRaw =
    typeof activeSceneData["match_count"] === "number"
      ? activeSceneData["match_count"]
      : Number(activeSceneData["match_count"]);
  const findMatchCount = Number.isFinite(matchCountRaw)
    ? Math.max(0, Number(matchCountRaw))
    : highlightRegions.length;
  const showFindOverlay =
    isBrowserScene &&
    Boolean(findQuery || dedupedBrowserKeywords.length || highlightRegions.length) &&
    (activeEventType === "browser_find_in_page" ||
      activeEventType === "browser_keyword_highlight" ||
      activeEventType === "browser_copy_selection" ||
      highlightRegions.length > 0);

  return { dedupedBrowserKeywords, findMatchCount, findQuery, showFindOverlay };
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

export {
  asHttpUrl,
  compactValue,
  highlightPalette,
  parseBrowserFindState,
  parseDocumentHighlights,
  parseHighlightRegions,
  parseLiveCopiedWords,
  parseScrollPercent,
  parseSheetState,
};
