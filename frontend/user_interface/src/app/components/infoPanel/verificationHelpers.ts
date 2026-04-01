import { buildRawFileUrl } from "../../../api/client";
import type { CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import {
  choosePreferredSourceUrl,
  extractExplicitSourceUrl,
  normalizeEvidenceId,
  normalizeHttpUrl,
  sourceLooksImage,
} from "./urlHelpers";

function normalizeFileId(rawValue: unknown): string {
  const value = String(rawValue || "").trim();
  if (!value) {
    return "";
  }
  if (/^(?:none|null|undefined|n\/a|unknown)$/i.test(value)) {
    return "";
  }
  // Keep the check permissive enough for existing ids while rejecting obvious garbage.
  if (!/^[a-z0-9][a-z0-9._:-]{1,255}$/i.test(value)) {
    return "";
  }
  return value;
}

function toCitationFromEvidence(card: EvidenceCard, index: number): CitationFocus {
  const sourceUrl = normalizeHttpUrl(card.sourceUrl);
  // Prefer "file" when a fileId is present — the backend clears fileId for web-only sources,
  // so if both fileId and sourceUrl exist the source is a stored document (PDF, etc.).
  const sourceType = !card.fileId && sourceUrl && !sourceLooksImage(sourceUrl) ? "website" : "file";
  return {
    fileId: card.fileId,
    chunkId: card.chunkId,
    sourceUrl: sourceUrl || undefined,
    sourceType,
    sourceName: card.source || "Indexed source",
    page: card.page,
    extract: String(card.extract || card.title || "No extract available for this citation.")
      .replace(/\s+/g, " ")
      .trim(),
    evidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
    highlightBoxes: card.highlightBoxes,
    evidenceUnits: card.evidenceUnits,
    strengthScore: card.strengthScore,
    strengthTier: card.strengthTier,
    matchQuality: card.matchQuality,
    unitId: card.unitId,
    selector: card.selector,
    charStart: card.charStart,
    charEnd: card.charEnd,
    graphNodeIds: card.graphNodeIds,
    sceneRefs: card.sceneRefs,
    eventRefs: card.eventRefs,
  };
}

function sourceIdForCitation(citation: CitationFocus | null): string {
  if (!citation) {
    return "";
  }
  const fileId = String(citation.fileId || "").trim();
  if (fileId) {
    return `file:${fileId}`.toLowerCase();
  }
  const sourceUrl = normalizeHttpUrl(citation.sourceUrl);
  if (sourceUrl) {
    return `url:${sourceUrl}`.toLowerCase();
  }
  return `label:${String(citation.sourceName || "").trim()}`.toLowerCase();
}

/**
 * If `url` is a Google Docs viewer URL (gview?embedded=1&url=...), return the
 * inner PDF URL. Otherwise return null.
 */
function _extractGviewPdfUrl(url: string): string | null {
  try {
    const u = new URL(url);
    if (
      (u.hostname === "docs.google.com" || u.hostname === "drive.google.com") &&
      u.pathname === "/gview"
    ) {
      const inner = u.searchParams.get("url");
      return inner || null;
    }
  } catch {
    // ignore malformed URLs
  }
  return null;
}

/** Return true if the URL path ends with .pdf (external, not an uploaded file). */
function _isExternalPdfUrl(url: string): boolean {
  try {
    return new URL(url).pathname.toLowerCase().endsWith(".pdf");
  } catch {
    return false;
  }
}

function resolveCitationOpenUrl(params: {
  citation: CitationFocus | null;
  evidenceCards: EvidenceCard[];
  indexId: number | null;
}) {
  const citation = params.citation;
  if (!citation) {
    return {
      citationOpenUrl: "",
      citationRawUrl: null as string | null,
      citationWebsiteUrl: "",
      citationUsesWebsite: false,
      citationIsPdf: false,
      citationIsImage: false,
    };
  }
  const evidenceId = normalizeEvidenceId(citation.evidenceId);
  const matchedCard = evidenceId
    ? params.evidenceCards.find((card) => normalizeEvidenceId(card.id) === evidenceId)
    : null;
  const directUrl = normalizeHttpUrl(citation.sourceUrl);
  const extractUrl = extractExplicitSourceUrl(citation.extract || "");
  const matchedUrl = normalizeHttpUrl(matchedCard?.sourceUrl);
  const sourceNameUrl = normalizeHttpUrl(citation.sourceName);
  const citationWebsiteUrl = choosePreferredSourceUrl([extractUrl, matchedUrl, directUrl, sourceNameUrl]) || "";

  // Resolve uploaded-file raw URL (if any).
  const normalizedFileId = normalizeFileId(citation.fileId);
  const citationRawUrl =
    normalizedFileId
      ? buildRawFileUrl(normalizedFileId)
      : null;

  // Detect external PDFs hidden behind a Google Docs viewer wrapper, or bare .pdf URLs.
  // These should be rendered by CitationPdfPreview (react-pdf) rather than WebReviewViewer.
  const gviewPdfUrl = _extractGviewPdfUrl(citationWebsiteUrl);
  const externalPdfUrl: string | null =
    !citationRawUrl && (gviewPdfUrl || _isExternalPdfUrl(citationWebsiteUrl))
      ? (gviewPdfUrl ?? citationWebsiteUrl)
      : null;

  // For external PDFs, route through the backend proxy so react-pdf can load them
  // without CORS / X-Frame-Options blocks.
  const effectiveCitationRawUrl: string | null =
    citationRawUrl ?? (externalPdfUrl ? `/api/web/pdf-proxy?url=${encodeURIComponent(externalPdfUrl)}` : null);

  // External PDFs bypass the WebReviewViewer — they use CitationPdfPreview instead.
  const citationUsesWebsite =
    !externalPdfUrl && (citation.sourceType === "website" || (Boolean(citationWebsiteUrl) && !effectiveCitationRawUrl));

  // Build the "Open" URL.
  // For gview citations use the real PDF URL; for website citations prefer the source page
  // with a Text Fragment deep link (Chrome 80+, Edge 83+, Safari 16.1+).
  const openBaseUrl = externalPdfUrl || (citationUsesWebsite || citationWebsiteUrl ? citationWebsiteUrl : effectiveCitationRawUrl || "");
  let citationOpenUrl = openBaseUrl;
  if (citationUsesWebsite && citationOpenUrl && citation.extract) {
    const extract = String(citation.extract || "").replace(/\s+/g, " ").trim();
    const raw = extract.length > 120 ? extract.slice(0, 120).replace(/\s\S*$/, "") : extract;
    if (raw.length >= 16 && !citationOpenUrl.includes("#:~:text=")) {
      try {
        const urlObj = new URL(citationOpenUrl);
        urlObj.hash = "";
        citationOpenUrl = `${urlObj.toString()}#:~:text=${encodeURIComponent(raw)}`;
      } catch {
        // Leave URL unchanged if parsing fails.
      }
    }
  }

  const citationSourceLower = String(citation.sourceName || "").toLowerCase();
  const citationIsImage =
    Boolean(effectiveCitationRawUrl) &&
    !citationUsesWebsite &&
    (sourceLooksImage(citationSourceLower) || sourceLooksImage(effectiveCitationRawUrl ?? ""));
  // Any file raw URL (uploaded or proxied external PDF) that isn't an image is treated as PDF.
  const citationIsPdf = Boolean(effectiveCitationRawUrl) && !citationUsesWebsite && !citationIsImage;

  return {
    citationOpenUrl,
    citationRawUrl: effectiveCitationRawUrl,
    citationWebsiteUrl,
    citationUsesWebsite,
    citationIsPdf,
    citationIsImage,
  };
}

export { resolveCitationOpenUrl, sourceIdForCitation, toCitationFromEvidence };
