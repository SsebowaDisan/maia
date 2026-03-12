import type { CitationFocus, CitationHighlightBox } from "../types";

type CitationDeepLinkPayload = {
  version: 1;
  conversationId?: string;
  fileId?: string;
  sourceUrl?: string;
  sourceType?: "file" | "website";
  sourceName: string;
  page?: string;
  extract: string;
  claimText?: string;
  evidenceId?: string;
  highlightBoxes?: CitationHighlightBox[];
  unitId?: string;
  charStart?: number;
  charEnd?: number;
  matchQuality?: string;
  strengthScore?: number;
  strengthTier?: number;
  graphNodeIds?: string[];
  sceneRefs?: string[];
  eventRefs?: string[];
};

const PARAM_KEY = "citation";
const MAX_EXTRACT_CHARS = 420;
const MAX_CLAIM_CHARS = 420;

function normalizeText(value: unknown, maxChars: number): string {
  const raw = String(value || "").replace(/\s+/g, " ").trim();
  if (!raw) {
    return "";
  }
  if (raw.length <= maxChars) {
    return raw;
  }
  return raw.slice(0, maxChars).trim();
}

function normalizePage(value: unknown): string | undefined {
  const raw = String(value || "").trim();
  if (!raw) {
    return undefined;
  }
  const match = raw.match(/(\d{1,4})/);
  return match?.[1] || undefined;
}

function normalizeHighlightBoxes(value: unknown): CitationHighlightBox[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const boxes: CitationHighlightBox[] = [];
  for (const row of value) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const x = Number((row as Record<string, unknown>).x);
    const y = Number((row as Record<string, unknown>).y);
    const width = Number((row as Record<string, unknown>).width);
    const height = Number((row as Record<string, unknown>).height);
    if (![x, y, width, height].every((item) => Number.isFinite(item))) {
      continue;
    }
    const left = Math.max(0, Math.min(1, x));
    const top = Math.max(0, Math.min(1, y));
    const normalizedWidth = Math.max(0, Math.min(1 - left, width));
    const normalizedHeight = Math.max(0, Math.min(1 - top, height));
    if (normalizedWidth < 0.002 || normalizedHeight < 0.002) {
      continue;
    }
    boxes.push({
      x: Number(left.toFixed(6)),
      y: Number(top.toFixed(6)),
      width: Number(normalizedWidth.toFixed(6)),
      height: Number(normalizedHeight.toFixed(6)),
    });
    if (boxes.length >= 24) {
      break;
    }
  }
  return boxes;
}

function normalizeTextList(value: unknown, maxItems: number, maxChars: number): string[] {
  const rows = Array.isArray(value) ? value : [value];
  const output: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const text = normalizeText(row, maxChars);
    if (!text) {
      continue;
    }
    const lowered = text.toLowerCase();
    if (seen.has(lowered)) {
      continue;
    }
    seen.add(lowered);
    output.push(text);
    if (output.length >= Math.max(1, maxItems)) {
      break;
    }
  }
  return output;
}

function toBase64Url(raw: string): string {
  const bytes = new TextEncoder().encode(raw);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(raw: string): string {
  const normalized = raw.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalized.length % 4 === 0 ? "" : "=".repeat(4 - (normalized.length % 4));
  const binary = atob(normalized + padding);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function toPayload(params: {
  citationFocus: CitationFocus;
  conversationId?: string | null;
}): CitationDeepLinkPayload {
  const { citationFocus, conversationId } = params;
  const strengthScore = Number(citationFocus.strengthScore);
  const strengthTier = Number(citationFocus.strengthTier);
  const charStart = Number(citationFocus.charStart);
  const charEnd = Number(citationFocus.charEnd);
  return {
    version: 1,
    conversationId: normalizeText(conversationId, 120) || undefined,
    fileId: normalizeText(citationFocus.fileId, 220) || undefined,
    sourceUrl: normalizeText(citationFocus.sourceUrl, 720) || undefined,
    sourceType: citationFocus.sourceType === "website" ? "website" : "file",
    sourceName: normalizeText(citationFocus.sourceName, 320) || "Indexed source",
    page: normalizePage(citationFocus.page),
    extract: normalizeText(citationFocus.extract, MAX_EXTRACT_CHARS),
    claimText: normalizeText(citationFocus.claimText, MAX_CLAIM_CHARS) || undefined,
    evidenceId: normalizeText(citationFocus.evidenceId, 80) || undefined,
    highlightBoxes: normalizeHighlightBoxes(citationFocus.highlightBoxes),
    unitId: normalizeText(citationFocus.unitId, 180) || undefined,
    matchQuality: normalizeText(citationFocus.matchQuality, 24) || undefined,
    graphNodeIds: normalizeTextList(citationFocus.graphNodeIds, 8, 180),
    sceneRefs: normalizeTextList(citationFocus.sceneRefs, 8, 180),
    eventRefs: normalizeTextList(citationFocus.eventRefs, 8, 180),
    charStart: Number.isFinite(charStart) && charStart > 0 ? charStart : undefined,
    charEnd: Number.isFinite(charEnd) && charEnd > 0 ? charEnd : undefined,
    strengthScore: Number.isFinite(strengthScore) ? Number(strengthScore.toFixed(6)) : undefined,
    strengthTier: Number.isFinite(strengthTier) ? Math.max(1, Math.min(3, Math.round(strengthTier))) : undefined,
  };
}

function payloadToFocus(payload: CitationDeepLinkPayload): CitationFocus {
  return {
    fileId: normalizeText(payload.fileId, 220) || undefined,
    sourceUrl: normalizeText(payload.sourceUrl, 720) || undefined,
    sourceType: payload.sourceType === "website" ? "website" : "file",
    sourceName: normalizeText(payload.sourceName, 320) || "Indexed source",
    page: normalizePage(payload.page),
    extract:
      normalizeText(payload.extract, MAX_EXTRACT_CHARS) ||
      "No extract available for this citation.",
    claimText: normalizeText(payload.claimText, MAX_CLAIM_CHARS) || undefined,
    evidenceId: normalizeText(payload.evidenceId, 80) || undefined,
    highlightBoxes: normalizeHighlightBoxes(payload.highlightBoxes),
    unitId: normalizeText(payload.unitId, 180) || undefined,
    matchQuality: normalizeText(payload.matchQuality, 24) || undefined,
    graphNodeIds: normalizeTextList(payload.graphNodeIds, 8, 180),
    sceneRefs: normalizeTextList(payload.sceneRefs, 8, 180),
    eventRefs: normalizeTextList(payload.eventRefs, 8, 180),
    charStart: Number.isFinite(Number(payload.charStart)) ? Number(payload.charStart) : undefined,
    charEnd: Number.isFinite(Number(payload.charEnd)) ? Number(payload.charEnd) : undefined,
    strengthScore: Number.isFinite(Number(payload.strengthScore))
      ? Number(Number(payload.strengthScore).toFixed(6))
      : undefined,
    strengthTier: Number.isFinite(Number(payload.strengthTier))
      ? Math.max(1, Math.min(3, Math.round(Number(payload.strengthTier))))
      : undefined,
  };
}

function encodeCitationPayload(params: {
  citationFocus: CitationFocus;
  conversationId?: string | null;
}): string {
  return toBase64Url(JSON.stringify(toPayload(params)));
}

function decodeCitationPayload(encoded: string): {
  citationFocus: CitationFocus;
  conversationId?: string;
} | null {
  const value = String(encoded || "").trim();
  if (!value) {
    return null;
  }
  try {
    const parsed = JSON.parse(fromBase64Url(value)) as Record<string, unknown>;
    if (!parsed || Number(parsed.version) !== 1) {
      return null;
    }
    const payload: CitationDeepLinkPayload = {
      version: 1,
      conversationId: normalizeText(parsed.conversationId, 120) || undefined,
      fileId: normalizeText(parsed.fileId, 220) || undefined,
      sourceUrl: normalizeText(parsed.sourceUrl, 720) || undefined,
      sourceType: parsed.sourceType === "website" ? "website" : "file",
      sourceName: normalizeText(parsed.sourceName, 320) || "Indexed source",
      page: normalizePage(parsed.page),
      extract: normalizeText(parsed.extract, MAX_EXTRACT_CHARS),
      claimText: normalizeText(parsed.claimText, MAX_CLAIM_CHARS) || undefined,
      evidenceId: normalizeText(parsed.evidenceId, 80) || undefined,
      highlightBoxes: normalizeHighlightBoxes(parsed.highlightBoxes),
      unitId: normalizeText(parsed.unitId, 180) || undefined,
      matchQuality: normalizeText(parsed.matchQuality, 24) || undefined,
      graphNodeIds: normalizeTextList(parsed.graphNodeIds, 8, 180),
      sceneRefs: normalizeTextList(parsed.sceneRefs, 8, 180),
      eventRefs: normalizeTextList(parsed.eventRefs, 8, 180),
      charStart: Number.isFinite(Number(parsed.charStart)) ? Number(parsed.charStart) : undefined,
      charEnd: Number.isFinite(Number(parsed.charEnd)) ? Number(parsed.charEnd) : undefined,
      strengthScore: Number.isFinite(Number(parsed.strengthScore))
        ? Number(Number(parsed.strengthScore).toFixed(6))
        : undefined,
      strengthTier: Number.isFinite(Number(parsed.strengthTier))
        ? Math.max(1, Math.min(3, Math.round(Number(parsed.strengthTier))))
        : undefined,
    };
    return {
      citationFocus: payloadToFocus(payload),
      conversationId: payload.conversationId,
    };
  } catch {
    return null;
  }
}

function buildCitationDeepLink(params: {
  citationFocus: CitationFocus;
  conversationId?: string | null;
}): string {
  const url = new URL(window.location.href);
  url.searchParams.set(PARAM_KEY, encodeCitationPayload(params));
  return url.toString();
}

function readCitationDeepLinkFromUrl(
  search: string = window.location.search,
): { citationFocus: CitationFocus; conversationId?: string } | null {
  const params = new URLSearchParams(search);
  const encoded = params.get(PARAM_KEY);
  if (!encoded) {
    return null;
  }
  return decodeCitationPayload(encoded);
}

function clearCitationDeepLinkInUrl(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(PARAM_KEY)) {
    return;
  }
  url.searchParams.delete(PARAM_KEY);
  window.history.replaceState({}, "", url.toString());
}

export {
  buildCitationDeepLink,
  clearCitationDeepLinkInUrl,
  readCitationDeepLinkFromUrl,
};
