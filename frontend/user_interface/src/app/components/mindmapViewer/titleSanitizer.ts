import type { MindmapNode } from "./types";
import { looksNoisyTitle } from "./viewerHelpers";

const MACHINE_SEGMENT_RE =
  /\b(?:src|sec|page|leaf|doc|node|cat|topic|chunk|item)[_:-][a-z0-9]{4,}\b/i;
const UNDERSCORE_HEAVY_RE = /\b[a-z0-9]+_[a-z0-9_]{4,}\b/i;
const HEX_TOKEN_RE = /\b[a-f0-9]{10,}\b/i;
const STRIP_EDGE_RE = /^[\s\-_:|.,;]+|[\s\-_:|.,;]+$/g;
const GENERIC_TITLE_RE = /^(?:page|detail|section|topic|node|leaf|item|chunk|branch)\s*$/i;

function clipAtWordBoundary(value: string, maxLen: number): string {
  const text = String(value || "").trim();
  if (text.length <= maxLen) {
    return text;
  }
  const windowed = text.slice(0, maxLen + 1);
  const sentenceCut = Math.max(windowed.lastIndexOf("."), windowed.lastIndexOf("!"), windowed.lastIndexOf("?"));
  if (sentenceCut >= Math.floor(maxLen * 0.6)) {
    return windowed.slice(0, sentenceCut + 1).trim();
  }
  const wordCut = windowed.lastIndexOf(" ");
  if (wordCut >= Math.floor(maxLen * 0.5)) {
    return windowed.slice(0, wordCut).trim();
  }
  return windowed.slice(0, maxLen).trim();
}

function toSingleLine(value: string): string {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function isMeaningfulLabel(value: string): boolean {
  const text = toSingleLine(value);
  if (!text) {
    return false;
  }
  if (GENERIC_TITLE_RE.test(text)) {
    return false;
  }
  if (looksNoisyTitle(text)) {
    return false;
  }
  return !isMachineLikeTitle(text);
}

function summaryAsTitle(node: MindmapNode): string {
  const raw = toSingleLine(String(node.summary || node.text || ""));
  if (!raw) {
    return "";
  }
  const sentence = raw.match(/^[^.!?]+[.!?]?/)?.[0] || raw;
  const cleaned = sanitizeMindmapTitle(sentence, 72);
  if (cleaned.length < 8) {
    return "";
  }
  return isMeaningfulLabel(cleaned) ? cleaned : "";
}

function sourceBasedLabel(node: MindmapNode): string {
  const sourceName = sanitizeMindmapTitle(String(node.source_name || ""), 56);
  if (isMeaningfulLabel(sourceName)) {
    return sourceName;
  }
  const sourceId = sanitizeMindmapTitle(String(node.source_id || ""), 56);
  if (isMeaningfulLabel(sourceId)) {
    return sourceId;
  }
  const domainLabel = cleanDomainLabel(String((node as Record<string, unknown>).url || ""));
  if (isMeaningfulLabel(domainLabel)) {
    return domainLabel;
  }
  return "";
}

export function isMachineLikeTitle(value: string): boolean {
  const text = String(value || "").trim();
  if (!text) {
    return true;
  }
  return (
    MACHINE_SEGMENT_RE.test(text) ||
    UNDERSCORE_HEAVY_RE.test(text) ||
    HEX_TOKEN_RE.test(text)
  );
}

export function sanitizeMindmapTitle(value: string, maxLen = 88): string {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const sanitized = text
    .replace(new RegExp(MACHINE_SEGMENT_RE.source, "ig"), " ")
    .replace(new RegExp(UNDERSCORE_HEAVY_RE.source, "ig"), " ")
    .replace(new RegExp(HEX_TOKEN_RE.source, "ig"), " ")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .replace(STRIP_EDGE_RE, "")
    .trim();
  if (!sanitized) {
    return "";
  }
  return clipAtWordBoundary(sanitized, maxLen);
}

export function cleanDomainLabel(url: string): string {
  try {
    const host = new URL(String(url || "").trim()).hostname.replace(/^www\./i, "").trim();
    if (!host) {
      return "";
    }
    return host
      .split(".")
      .slice(0, 2)
      .join(" ")
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (match) => match.toUpperCase());
  } catch {
    return "";
  }
}

export function professionalFallbackLabel(node: MindmapNode, sourceIndex?: number): string {
  const nodeType = String(node.node_type || node.type || "").trim().toLowerCase();
  const pageValue = String(node.page_ref || node.page || "").trim();
  const sourceLabel = sourceBasedLabel(node);
  if (nodeType === "source" || nodeType === "web_source") {
    return sourceIndex ? `Source ${sourceIndex}` : "Source";
  }
  if (nodeType === "page" || nodeType === "excerpt" || nodeType === "bullet" || nodeType === "leaf") {
    if (sourceLabel) {
      return pageValue ? `${sourceLabel} p.${pageValue}` : `${sourceLabel} excerpt`;
    }
    if (sourceIndex) {
      return pageValue ? `Source ${sourceIndex} p.${pageValue}` : `Source ${sourceIndex} excerpt`;
    }
    return pageValue ? `Reference p.${pageValue}` : "Reference excerpt";
  }
  if (nodeType === "section") {
    return sourceLabel ? `${sourceLabel} section` : "Topic section";
  }
  if (nodeType === "topic") {
    return sourceLabel ? `${sourceLabel} topic` : "Topic branch";
  }
  if (nodeType === "claim") {
    return "Claim";
  }
  if (nodeType === "evidence") {
    return "Evidence";
  }
  return sourceLabel ? `${sourceLabel} branch` : "Reference branch";
}

export function resolveProfessionalNodeTitle(
  node: MindmapNode,
  options?: { sourceIndex?: number },
): string {
  const directTitle = sanitizeMindmapTitle(String(node.title || ""));
  if (isMeaningfulLabel(directTitle)) {
    return directTitle;
  }
  const sourceName = sanitizeMindmapTitle(String(node.source_name || ""));
  if (isMeaningfulLabel(sourceName)) {
    return sourceName;
  }
  const summaryTitle = summaryAsTitle(node);
  if (summaryTitle) {
    return summaryTitle;
  }
  const domainLabel = cleanDomainLabel(String((node as Record<string, unknown>).url || ""));
  if (isMeaningfulLabel(domainLabel)) {
    return `${domainLabel} source`;
  }
  return professionalFallbackLabel(node, options?.sourceIndex);
}
