import { normalizeText, plainText } from "./text";
import type { EvidenceCard, HighlightBox } from "./types";

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

function extractExplicitSourceUrl(detailText: string): string {
  const normalizedText = String(detailText || "");
  const patterns = [
    /\bURL\s*Source\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bsource_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bpage_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
    /\bsource\s*url\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
  ];
  for (const pattern of patterns) {
    const match = normalizedText.match(pattern);
    const candidate = normalizeUrlToken(match?.[1] || "");
    if (candidate) {
      return candidate;
    }
  }
  return "";
}

function extractFirstHttpUrl(detailText: string): string {
  const matches = String(detailText || "").match(/https?:\/\/[^\s<>'")\]]+/gi) || [];
  for (const candidate of matches) {
    const normalized = normalizeUrlToken(candidate);
    if (normalized) {
      return normalized;
    }
  }
  return "";
}

function choosePreferredUrl(candidates: Array<string | null | undefined>): string {
  for (const rawCandidate of candidates) {
    const normalized = normalizeHttpUrl(rawCandidate);
    if (!normalized) {
      continue;
    }
    if (isLikelyLabelArtifactUrl(normalized)) {
      continue;
    }
    return normalized;
  }
  return "";
}

function extractSourceUrl(details: Element): string {
  const detailText = normalizeText(details.textContent || "");
  const explicitTextUrl = extractExplicitSourceUrl(detailText);
  const attrUrl = normalizeHttpUrl(details.getAttribute("data-source-url"));
  const linkNode = details.querySelector("a[href^='http://'], a[href^='https://']");
  const href = normalizeHttpUrl(linkNode?.getAttribute("href"));
  const firstHttpUrl = extractFirstHttpUrl(detailText);
  return choosePreferredUrl([explicitTextUrl, attrUrl, href, firstHttpUrl]);
}

function toFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return parsed;
}

function clamp01(value: number): number {
  if (value < 0) {
    return 0;
  }
  if (value > 1) {
    return 1;
  }
  return value;
}

function normalizeHighlightBox(raw: unknown): HighlightBox | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const x = toFiniteNumber(record.x);
  const y = toFiniteNumber(record.y);
  const width = toFiniteNumber(record.width);
  const height = toFiniteNumber(record.height);
  if (x === null || y === null || width === null || height === null) {
    return null;
  }
  const nx = clamp01(x);
  const ny = clamp01(y);
  const nw = Math.max(0, Math.min(1 - nx, width));
  const nh = Math.max(0, Math.min(1 - ny, height));
  if (nw < 0.002 || nh < 0.002) {
    return null;
  }
  return {
    x: Number(nx.toFixed(6)),
    y: Number(ny.toFixed(6)),
    width: Number(nw.toFixed(6)),
    height: Number(nh.toFixed(6)),
  };
}

function parseHighlightBoxes(raw: string | null): HighlightBox[] {
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    const boxes: HighlightBox[] = [];
    for (const row of parsed) {
      const normalized = normalizeHighlightBox(row);
      if (!normalized) {
        continue;
      }
      boxes.push(normalized);
      if (boxes.length >= 24) {
        break;
      }
    }
    return boxes;
  } catch {
    return [];
  }
}

function parseHighlightBoxesFromDetails(details: Element): HighlightBox[] {
  const fromBoxes = parseHighlightBoxes(details.getAttribute("data-boxes"));
  if (fromBoxes.length) {
    return fromBoxes;
  }
  const fromBboxes = parseHighlightBoxes(details.getAttribute("data-bboxes"));
  if (fromBboxes.length) {
    return fromBboxes;
  }
  const candidate = details.querySelector("[data-boxes], [data-bboxes]");
  if (!candidate) {
    return [];
  }
  const nestedBoxes = parseHighlightBoxes(candidate.getAttribute("data-boxes"));
  if (nestedBoxes.length) {
    return nestedBoxes;
  }
  return parseHighlightBoxes(candidate.getAttribute("data-bboxes"));
}

function parseEvidence(infoHtml: string): EvidenceCard[] {
  if (!infoHtml.trim()) {
    return [];
  }

  const doc = new DOMParser().parseFromString(infoHtml, "text/html");
  const detailsNodes = Array.from(doc.querySelectorAll("details.evidence"));
  if (!detailsNodes.length) {
    const fallback = plainText(infoHtml);
    return fallback
      ? [
          {
            id: "evidence-1",
            title: "Evidence",
            source: "Indexed context",
            extract: fallback,
          },
        ]
      : [];
  }

  return detailsNodes.map((details, index) => {
    const detailsId = (details.getAttribute("id") || "").trim();
    const summary = normalizeText(
      details.querySelector("summary")?.textContent || `Evidence ${index + 1}`,
    );

    let source = "";
    let extract = "";
    const divs = Array.from(details.querySelectorAll("div"));
    for (const div of divs) {
      const text = normalizeText(div.textContent || "");
      if (!source && /^source\s*:/i.test(text)) {
        source = text.replace(/^source\s*:/i, "").trim();
      }
      if (!extract && /^extract\s*:/i.test(text)) {
        extract = text.replace(/^extract\s*:/i, "").trim();
      }
    }

    if (!extract) {
      const evidenceContent = details.querySelector(".evidence-content");
      extract = normalizeText(evidenceContent?.textContent || "");
    }
    if (!extract) {
      extract = normalizeText(details.textContent || "");
    }
    if (!source) {
      source = "Indexed source";
    }

    const imageSrc = details.querySelector("img")?.getAttribute("src") || undefined;
    const sourceUrl = extractSourceUrl(details) || undefined;
    const pageAttr = (details.getAttribute("data-page") || "").trim();
    const pageMatch = summary.match(/page\s+(\d+)/i);
    const fileId = (details.getAttribute("data-file-id") || "").trim() || undefined;
    const highlightBoxes = parseHighlightBoxesFromDetails(details);
    const rawStrength = Number(details.getAttribute("data-strength") || "");
    const strengthScore = Number.isFinite(rawStrength) ? rawStrength : undefined;
    const rawStrengthTier = Number(details.getAttribute("data-strength-tier") || "");
    const strengthTier = Number.isFinite(rawStrengthTier) ? rawStrengthTier : undefined;
    const matchQuality = (details.getAttribute("data-match-quality") || "").trim() || undefined;
    const unitId = (details.getAttribute("data-unit-id") || "").trim() || undefined;
    const rawCharStart = Number(details.getAttribute("data-char-start") || "");
    const rawCharEnd = Number(details.getAttribute("data-char-end") || "");
    const charStart = Number.isFinite(rawCharStart) ? rawCharStart : undefined;
    const charEnd = Number.isFinite(rawCharEnd) ? rawCharEnd : undefined;

    return {
      id: detailsId || `evidence-${index + 1}`,
      title: summary,
      source,
      sourceUrl,
      page: pageAttr || pageMatch?.[1],
      fileId,
      extract,
      imageSrc,
      highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
      strengthScore,
      strengthTier,
      matchQuality,
      unitId,
      charStart,
      charEnd,
    };
  });
}

export { parseEvidence };
