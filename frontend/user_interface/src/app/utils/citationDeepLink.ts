import type { CitationFocus, CitationHighlightBox } from "../types";

type CitationDeepLinkPayload = {
  version: 1;
  conversationId?: string;
  fileId?: string;
  sourceName: string;
  page?: string;
  extract: string;
  evidenceId?: string;
  highlightBoxes?: CitationHighlightBox[];
};

const PARAM_KEY = "citation";
const MAX_EXTRACT_CHARS = 260;

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
  return {
    version: 1,
    conversationId: normalizeText(conversationId, 120) || undefined,
    fileId: normalizeText(citationFocus.fileId, 220) || undefined,
    sourceName: normalizeText(citationFocus.sourceName, 320) || "Indexed source",
    page: normalizePage(citationFocus.page),
    extract: normalizeText(citationFocus.extract, MAX_EXTRACT_CHARS),
    evidenceId: normalizeText(citationFocus.evidenceId, 80) || undefined,
    highlightBoxes: normalizeHighlightBoxes(citationFocus.highlightBoxes),
  };
}

function payloadToFocus(payload: CitationDeepLinkPayload): CitationFocus {
  return {
    fileId: normalizeText(payload.fileId, 220) || undefined,
    sourceName: normalizeText(payload.sourceName, 320) || "Indexed source",
    page: normalizePage(payload.page),
    extract:
      normalizeText(payload.extract, MAX_EXTRACT_CHARS) ||
      "No extract available for this citation.",
    evidenceId: normalizeText(payload.evidenceId, 80) || undefined,
    highlightBoxes: normalizeHighlightBoxes(payload.highlightBoxes),
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
      sourceName: normalizeText(parsed.sourceName, 320) || "Indexed source",
      page: normalizePage(parsed.page),
      extract: normalizeText(parsed.extract, MAX_EXTRACT_CHARS),
      evidenceId: normalizeText(parsed.evidenceId, 80) || undefined,
      highlightBoxes: normalizeHighlightBoxes(parsed.highlightBoxes),
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
