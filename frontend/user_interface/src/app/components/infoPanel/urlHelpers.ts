import type { EvidenceCard } from "../../utils/infoInsights";

const ARTIFACT_URL_PATH_SEGMENTS = new Set([
  "extract",
  "source",
  "link",
  "evidence",
  "citation",
  "title",
  "markdown",
  "content",
  "published",
  "time",
  "url",
]);

function normalizeHttpUrl(rawValue: unknown): string {
  const value = String(rawValue || "").split(/\s+/).join(" ").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "";
    }
    return parsed.toString();
  } catch {
    return "";
  }
}

function normalizeUrlToken(rawValue: unknown): string {
  const value = String(rawValue || "")
    .trim()
    .replace(/^[("'`<\[]+/, "")
    .replace(/[>"'`)\],.;:!?]+$/, "");
  return normalizeHttpUrl(value);
}

function isLikelyLabelArtifactUrl(rawValue: unknown): boolean {
  const candidate = normalizeHttpUrl(rawValue);
  if (!candidate) {
    return false;
  }
  try {
    const parsed = new URL(candidate);
    const segments = String(parsed.pathname || "")
      .split("/")
      .filter(Boolean)
      .map((segment) => segment.trim().toLowerCase());
    if (segments.length !== 1) {
      return false;
    }
    const token = segments[0].replace(/[:]+$/, "");
    return ARTIFACT_URL_PATH_SEGMENTS.has(token);
  } catch {
    return false;
  }
}

function extractExplicitSourceUrl(rawText: unknown): string {
  const text = String(rawText || "");
  const patterns = [
    /\bURL\s*Source\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bsource_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bpage_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bsource\s*url\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    const candidate = normalizeUrlToken(match?.[1] || "");
    if (candidate) {
      return candidate;
    }
  }
  return "";
}

function choosePreferredSourceUrl(candidates: Array<string | null | undefined>): string {
  for (const rawCandidate of candidates) {
    const normalized = normalizeHttpUrl(rawCandidate);
    if (!normalized || isLikelyLabelArtifactUrl(normalized)) {
      continue;
    }
    return normalized;
  }
  return "";
}

function normalizeEvidenceId(rawValue: unknown): string {
  return String(rawValue || "").trim().toLowerCase();
}

function sourceLooksImage(nameOrUrl: string): boolean {
  return /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(String(nameOrUrl || "").toLowerCase());
}

function evidenceSourceLabel(card: EvidenceCard): string {
  return String(card.source || card.sourceUrl || card.fileId || "Indexed source").trim() || "Indexed source";
}

export {
  choosePreferredSourceUrl,
  evidenceSourceLabel,
  extractExplicitSourceUrl,
  normalizeEvidenceId,
  normalizeHttpUrl,
  normalizeUrlToken,
  sourceLooksImage,
};
