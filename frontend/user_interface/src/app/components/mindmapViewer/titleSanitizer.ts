import type { MindmapNode } from "./types";
import { looksNoisyTitle } from "./viewerHelpers";

const MACHINE_SEGMENT_RE =
  /\b(?:src|sec|page|leaf|doc|node|cat|topic|chunk|item)[_:-][a-z0-9]{4,}\b/gi;
const UNDERSCORE_HEAVY_RE = /\b[a-z0-9]+_[a-z0-9_]{4,}\b/gi;
const HEX_TOKEN_RE = /\b[a-f0-9]{10,}\b/gi;
const STRIP_EDGE_RE = /^[\s\-_:|.,;]+|[\s\-_:|.,;]+$/g;

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
    .replace(MACHINE_SEGMENT_RE, " ")
    .replace(UNDERSCORE_HEAVY_RE, " ")
    .replace(HEX_TOKEN_RE, " ")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .replace(STRIP_EDGE_RE, "")
    .trim();
  if (!sanitized) {
    return "";
  }
  return sanitized.length > maxLen ? `${sanitized.slice(0, maxLen - 1).trimEnd()}…` : sanitized;
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
  if (nodeType === "source" || nodeType === "web_source") {
    return sourceIndex ? `Source ${sourceIndex}` : "Source";
  }
  if (nodeType === "page") {
    return pageValue ? `Page ${pageValue}` : "Page";
  }
  if (nodeType === "section") {
    return "Section";
  }
  if (nodeType === "topic") {
    return "Topic";
  }
  if (nodeType === "excerpt" || nodeType === "bullet") {
    return "Detail";
  }
  if (nodeType === "claim") {
    return "Claim";
  }
  if (nodeType === "evidence") {
    return "Evidence";
  }
  return "Branch";
}

export function resolveProfessionalNodeTitle(
  node: MindmapNode,
  options?: { sourceIndex?: number },
): string {
  const directTitle = sanitizeMindmapTitle(String(node.title || ""));
  if (directTitle && !looksNoisyTitle(directTitle) && !isMachineLikeTitle(directTitle)) {
    return directTitle;
  }
  const sourceName = sanitizeMindmapTitle(String(node.source_name || ""));
  if (sourceName && !looksNoisyTitle(sourceName) && !isMachineLikeTitle(sourceName)) {
    return sourceName;
  }
  const domainLabel = cleanDomainLabel(String((node as Record<string, unknown>).url || ""));
  if (domainLabel) {
    return `${domainLabel} source`;
  }
  return professionalFallbackLabel(node, options?.sourceIndex);
}

