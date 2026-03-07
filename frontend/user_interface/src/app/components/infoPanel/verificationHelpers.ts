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
  const citationOpenUrl = citationUsesWebsite ? citationWebsiteUrl : citationRawUrl || "";
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
