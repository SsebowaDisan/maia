import type { EvidenceCard } from "../../../utils/infoInsights";

type WebReviewSource = {
  sourceId: string;
  sourceUrl: string;
  title: string;
  domain: string;
  readableText: string;
  readableHtml: string;
  evidenceIds: string[];
  snippetCount: number;
};

function cleanText(value: unknown, maxLength = 2400): string {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, Math.max(1, maxLength));
}

function normalizeHttpUrl(rawValue: unknown): string {
  const value = cleanText(rawValue, 2048).replace(/^[<'"`\[]+/, "").replace(/[>'"`\],.;:!?]+$/, "");
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

function normalizeSourceId(value: unknown): string {
  return cleanText(value, 220).toLowerCase();
}

function domainFromUrl(urlValue: string): string {
  if (!urlValue) {
    return "";
  }
  try {
    const parsed = new URL(urlValue);
    return String(parsed.hostname || "").replace(/^www\./i, "").toLowerCase();
  } catch {
    return "";
  }
}

function sanitizeReadableHtmlToParagraphs(rawHtml: string): string[] {
  const htmlText = String(rawHtml || "").trim();
  if (!htmlText) {
    return [];
  }
  if (typeof DOMParser === "undefined") {
    const stripped = htmlText
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<(iframe|object|embed|form|svg|canvas)[\s\S]*?<\/\1>/gi, " ")
      .replace(/<\/?(h1|h2|h3|h4|p|li|blockquote|pre|div|section|article|br)[^>]*>/gi, "\n")
      .replace(/<[^>]+>/g, " ");
    return stripped
      .split(/\n+/)
      .map((row) => cleanText(row, 1200))
      .filter(Boolean)
      .slice(0, 80);
  }
  const doc = new DOMParser().parseFromString(htmlText, "text/html");
  const blockedNodes = doc.querySelectorAll("script,style,iframe,object,embed,link,meta,svg,canvas,form");
  for (const node of blockedNodes) {
    node.remove();
  }
  const candidates = Array.from(doc.querySelectorAll("h1,h2,h3,h4,p,li,blockquote,pre"));
  const rows: string[] = [];
  const seen = new Set<string>();
  for (const candidate of candidates) {
    const text = cleanText(candidate.textContent || "", 1200);
    if (!text) {
      continue;
    }
    const key = text.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    rows.push(text);
    if (rows.length >= 80) {
      break;
    }
  }
  if (rows.length) {
    return rows;
  }
  const fallback = cleanText(doc.body.textContent || "", 6000);
  return fallback ? [fallback] : [];
}

function normalizeEvidenceIds(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const rows: string[] = [];
  const seen = new Set<string>();
  for (const row of value) {
    const text = cleanText(row, 80).toLowerCase();
    if (!text || seen.has(text)) {
      continue;
    }
    seen.add(text);
    rows.push(text);
    if (rows.length >= 24) {
      break;
    }
  }
  return rows;
}

function parseWebReviewSourceMap(rawInfoPanel: unknown): Record<string, WebReviewSource> {
  if (!rawInfoPanel || typeof rawInfoPanel !== "object") {
    return {};
  }
  const infoPanel = rawInfoPanel as Record<string, unknown>;
  const rawReview = infoPanel.web_review_content;
  if (!rawReview || typeof rawReview !== "object") {
    return {};
  }
  const review = rawReview as Record<string, unknown>;
  const rawSources = Array.isArray(review.sources) ? review.sources : [];
  const output: Record<string, WebReviewSource> = {};
  for (const row of rawSources) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const item = row as Record<string, unknown>;
    const sourceUrl = normalizeHttpUrl(item.source_url || item.sourceUrl);
    const sourceId = normalizeSourceId(item.source_id || item.sourceId || (sourceUrl ? `url:${sourceUrl}` : ""));
    if (!sourceId) {
      continue;
    }
    const readableText = cleanText(item.readable_text || item.readableText || "", 32000);
    const readableHtml = cleanText(item.readable_html || item.readableHtml || "", 32000);
    const title = cleanText(item.title || item.source_name || "Website source", 220) || "Website source";
    const domain = cleanText(item.domain || domainFromUrl(sourceUrl), 120);
    const parsed: WebReviewSource = {
      sourceId,
      sourceUrl,
      title,
      domain,
      readableText,
      readableHtml,
      evidenceIds: normalizeEvidenceIds(item.evidence_ids || item.evidenceIds),
      snippetCount: Math.max(
        0,
        Number.isFinite(Number(item.snippet_count))
          ? Number(item.snippet_count)
          : Number.isFinite(Number(item.snippetCount))
            ? Number(item.snippetCount)
            : 0,
      ),
    };
    output[sourceId] = parsed;
    if (sourceUrl) {
      output[normalizeSourceId(`url:${sourceUrl}`)] = parsed;
    }
  }
  return output;
}

function buildFallbackWebReview(sourceId: string, sourceUrl: string, sourceTitle: string, evidenceCards: EvidenceCard[]): WebReviewSource | null {
  const snippets: string[] = [];
  const seen = new Set<string>();
  for (const card of evidenceCards) {
    const text = cleanText(card.extract || card.title || "", 1200);
    if (!text) {
      continue;
    }
    const key = text.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    snippets.push(text);
    if (snippets.length >= 24) {
      break;
    }
  }
  if (!snippets.length) {
    return null;
  }
  return {
    sourceId: normalizeSourceId(sourceId || (sourceUrl ? `url:${sourceUrl}` : sourceTitle)),
    sourceUrl,
    title: cleanText(sourceTitle || "Website source", 220) || "Website source",
    domain: domainFromUrl(sourceUrl),
    readableText: snippets.join("\n\n").slice(0, 32000),
    readableHtml: "",
    evidenceIds: [],
    snippetCount: snippets.length,
  };
}

function resolveWebReviewSource(params: {
  sourceMap: Record<string, WebReviewSource>;
  sourceId: string;
  sourceUrl: string;
  sourceTitle: string;
  evidenceCards: EvidenceCard[];
}): WebReviewSource | null {
  const normalizedSourceId = normalizeSourceId(params.sourceId);
  const normalizedSourceUrl = normalizeHttpUrl(params.sourceUrl);
  if (normalizedSourceId && params.sourceMap[normalizedSourceId]) {
    return params.sourceMap[normalizedSourceId];
  }
  if (normalizedSourceUrl) {
    const urlKey = normalizeSourceId(`url:${normalizedSourceUrl}`);
    if (params.sourceMap[urlKey]) {
      return params.sourceMap[urlKey];
    }
  }
  return buildFallbackWebReview(
    normalizedSourceId,
    normalizedSourceUrl,
    params.sourceTitle,
    params.evidenceCards,
  );
}

function resolveWebReviewParagraphs(reviewSource: WebReviewSource | null, maxParagraphs = 40): string[] {
  if (!reviewSource) {
    return [];
  }
  const fromHtml = sanitizeReadableHtmlToParagraphs(reviewSource.readableHtml);
  if (fromHtml.length) {
    return fromHtml.slice(0, Math.max(1, maxParagraphs));
  }
  const fromText = String(reviewSource.readableText || "")
    .split(/\n{2,}|(?<=[.!?])\s+(?=[A-Z0-9])/)
    .map((row) => cleanText(row, 1400))
    .filter(Boolean);
  if (fromText.length) {
    return fromText.slice(0, Math.max(1, maxParagraphs));
  }
  return [];
}

function tokenizeForMatch(value: string): string[] {
  return String(value || "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .map((row) => row.trim())
    .filter((row) => row.length >= 3)
    .slice(0, 64);
}

function findBestParagraphIndex(paragraphs: string[], focusText: string): number {
  if (!Array.isArray(paragraphs) || !paragraphs.length) {
    return -1;
  }
  const focus = cleanText(focusText, 1000).toLowerCase();
  if (!focus) {
    return 0;
  }
  const direct = paragraphs.findIndex((paragraph) => paragraph.toLowerCase().includes(focus));
  if (direct >= 0) {
    return direct;
  }
  const focusTokens = tokenizeForMatch(focus);
  if (!focusTokens.length) {
    return 0;
  }
  let bestIndex = 0;
  let bestScore = -1;
  for (let index = 0; index < paragraphs.length; index += 1) {
    const paragraphTokens = new Set(tokenizeForMatch(paragraphs[index]));
    if (!paragraphTokens.size) {
      continue;
    }
    let overlap = 0;
    for (const token of focusTokens) {
      if (paragraphTokens.has(token)) {
        overlap += 1;
      }
    }
    const score = overlap / focusTokens.length;
    if (score > bestScore) {
      bestScore = score;
      bestIndex = index;
    }
  }
  return bestIndex;
}

export type { WebReviewSource };
export {
  findBestParagraphIndex,
  parseWebReviewSourceMap,
  resolveWebReviewParagraphs,
  resolveWebReviewSource,
  sanitizeReadableHtmlToParagraphs,
};
