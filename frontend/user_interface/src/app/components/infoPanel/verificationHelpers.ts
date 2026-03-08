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

function toCitationFromEvidence(card: EvidenceCard, index: number): CitationFocus {
  const sourceUrl = normalizeHttpUrl(card.sourceUrl);
  return {
    fileId: card.fileId,
    sourceUrl: sourceUrl || undefined,
    sourceType: sourceUrl && !sourceLooksImage(sourceUrl) ? "website" : "file",
    sourceName: card.source || "Indexed source",
    page: card.page,
    extract: String(card.extract || card.title || "No extract available for this citation.")
      .replace(/\s+/g, " ")
      .trim(),
    evidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
    highlightBoxes: card.highlightBoxes,
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
  const citationRawUrl =
    citation.fileId
      ? buildRawFileUrl(citation.fileId, {
          indexId: typeof params.indexId === "number" ? params.indexId : undefined,
        })
      : null;
  const citationUsesWebsite = citation.sourceType === "website" || (Boolean(citationWebsiteUrl) && !citationRawUrl);

  // Build a text-fragment URL so "Open" jumps the browser directly to the cited passage.
  // Text Fragments (#:~:text=) are supported in Chrome 80+, Edge 83+, Safari 16.1+.
  let citationOpenUrl = citationUsesWebsite ? citationWebsiteUrl : citationRawUrl || "";
  if (citationUsesWebsite && citationOpenUrl && citation.extract) {
    const extract = String(citation.extract || "").replace(/\s+/g, " ").trim();
    // Use up to first 120 chars of the extract, trimmed to a word boundary.
    const raw = extract.length > 120 ? extract.slice(0, 120).replace(/\s\S*$/, "") : extract;
    if (raw.length >= 16 && !citationOpenUrl.includes("#:~:text=")) {
      try {
        // Strip any existing fragment before appending text fragment.
        const urlObj = new URL(citationOpenUrl);
        urlObj.hash = "";
        citationOpenUrl = `${urlObj.toString()}#:~:text=${encodeURIComponent(raw)}`;
      } catch {
        // Leave URL unchanged if parsing fails.
      }
    }
  }
  const citationSourceLower = String(citation.sourceName || "").toLowerCase();
  const citationHasPageHint = Boolean(String(citation.page || "").trim());
  const citationIsImage =
    Boolean(citationRawUrl) && !citationUsesWebsite && (sourceLooksImage(citationSourceLower) || sourceLooksImage(citationRawUrl));
  const citationIsPdf =
    Boolean(citationRawUrl) &&
    !citationUsesWebsite &&
    !citationIsImage &&
    (citationSourceLower.endsWith(".pdf") || citationHasPageHint || !citationSourceLower);
  return {
    citationOpenUrl,
    citationRawUrl,
    citationWebsiteUrl,
    citationUsesWebsite,
    citationIsPdf,
    citationIsImage,
  };
}

export { resolveCitationOpenUrl, sourceIdForCitation, toCitationFromEvidence };
