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

function inferSourceTypeFromUrl(rawUrl: string): string {
  const candidate = String(rawUrl || "").toLowerCase();
  if (/\.(pdf)(?:[?#]|$)/i.test(candidate)) {
    return "pdf";
  }
  if (/\.(png|jpe?g|webp|gif|svg)(?:[?#]|$)/i.test(candidate)) {
    return "image";
  }
  return "web";
}

function inferSourceTypeFromName(rawName: string): string {
  const candidate = String(rawName || "").toLowerCase();
  if (candidate.endsWith(".pdf")) {
    return "pdf";
  }
  if (/\.(png|jpe?g|webp|gif|svg)$/i.test(candidate)) {
    return "image";
  }
  return "";
}

function sourceLabelFromUrl(rawUrl: string): string {
  const normalized = normalizeHttpUrl(rawUrl);
  if (!normalized) {
    return "";
  }
  try {
    const parsed = new URL(normalized);
    const host = parsed.hostname.replace(/^www\./i, "");
    const path = String(parsed.pathname || "").trim();
    if (!path || path === "/") {
      return host || normalized;
    }
    return `${host}${path}`;
  } catch {
    return normalized;
  }
}

function extractPromptUrls(rawPrompt: unknown): string[] {
  const text = String(rawPrompt || "");
  if (!text.trim()) {
    return [];
  }
  const matches = text.match(/https?:\/\/[^\s<>'")\]]+/gi) || [];
  if (!matches.length) {
    return [];
  }
  const output: string[] = [];
  const seen = new Set<string>();
  for (const candidate of matches) {
    const normalized = normalizeUrlToken(candidate);
    if (!normalized) {
      continue;
    }
    const dedupeKey = normalized.toLowerCase();
    if (seen.has(dedupeKey)) {
      continue;
    }
    seen.add(dedupeKey);
    output.push(normalized);
    if (output.length >= 12) {
      break;
    }
  }
  return output;
}

function parsePromptEvidence(options?: {
  userPrompt?: string;
  promptAttachments?: Array<{
    name?: string;
    fileId?: string;
    file_id?: string;
  }> | null;
}): EvidenceCard[] {
  const cards: EvidenceCard[] = [];

  const promptUrls = extractPromptUrls(options?.userPrompt || "");
  for (const sourceUrl of promptUrls) {
    cards.push({
      id: `prompt-url-${cards.length + 1}`,
      title: `Prompt source [${cards.length + 1}]`,
      source: sourceLabelFromUrl(sourceUrl) || sourceUrl,
      sourceType: inferSourceTypeFromUrl(sourceUrl),
      sourceUrl,
      extract: "User prompt references this source URL.",
    });
  }

  const rawAttachments = Array.isArray(options?.promptAttachments)
    ? options?.promptAttachments || []
    : [];
  const seenAttachments = new Set<string>();
  for (const rawAttachment of rawAttachments) {
    if (!rawAttachment || typeof rawAttachment !== "object") {
      continue;
    }
    const fileId = normalizeText(
      String(rawAttachment.fileId || rawAttachment.file_id || ""),
    ).trim();
    const name = normalizeText(String(rawAttachment.name || "")).trim();
    if (!fileId && !name) {
      continue;
    }
    const key = (fileId ? `file:${fileId}` : `name:${name}`).toLowerCase();
    if (seenAttachments.has(key)) {
      continue;
    }
    seenAttachments.add(key);
    cards.push({
      id: `prompt-file-${cards.length + 1}`,
      title: `Prompt file [${cards.length + 1}]`,
      source: name || "Prompt attachment",
      sourceType: inferSourceTypeFromName(name) || undefined,
      fileId: fileId || undefined,
      extract: "User prompt includes this file attachment.",
    });
    if (cards.length >= 16) {
      break;
    }
  }

  return cards;
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

function normalizeEvidenceUnits(rawValue: unknown): EvidenceCard["evidenceUnits"] {
  let rows: unknown[] = [];
  if (Array.isArray(rawValue)) {
    rows = rawValue;
  } else if (typeof rawValue === "string" && rawValue.trim()) {
    try {
      const parsed = JSON.parse(rawValue);
      rows = Array.isArray(parsed) ? parsed : [];
    } catch {
      rows = [];
    }
  }
  const output: NonNullable<EvidenceCard["evidenceUnits"]> = [];
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row || typeof row !== "object") {
      continue;
    }
    const entry = row as Record<string, unknown>;
    const text = normalizeText(String(entry.text || "")).trim().slice(0, 240);
    if (text.length < 8) {
      continue;
    }
    const boxesRaw = Array.isArray(entry.highlight_boxes)
      ? entry.highlight_boxes
      : Array.isArray(entry.highlightBoxes)
        ? entry.highlightBoxes
        : [];
    const highlightBoxes = boxesRaw
      .map((item) => normalizeHighlightBox(item))
      .filter((item): item is HighlightBox => Boolean(item));
    if (!highlightBoxes.length) {
      continue;
    }
    const charStart = toFiniteNumberOptional(entry.char_start ?? entry.charStart);
    const charEnd = toFiniteNumberOptional(entry.char_end ?? entry.charEnd);
    const key = `${charStart ?? 0}|${charEnd ?? 0}|${text.toLowerCase().slice(0, 120)}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push({
      text,
      highlightBoxes,
      charStart: typeof charStart === "number" ? charStart : undefined,
      charEnd: typeof charEnd === "number" ? charEnd : undefined,
    });
    if (output.length >= 12) {
      break;
    }
  }
  return output.length ? output : undefined;
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

function parseEvidenceUnitsFromDetails(details: Element) {
  const attrs = ["data-evidence-units", "data-evidenceUnits"];
  for (const attr of attrs) {
    const explicit = normalizeEvidenceUnits(details.getAttribute(attr));
    if (explicit.length) {
      return explicit;
    }
  }
  const candidate = details.querySelector("[data-evidence-units], [data-evidenceUnits]");
  if (!candidate) {
    return undefined;
  }
  for (const attr of attrs) {
    const nested = normalizeEvidenceUnits(candidate.getAttribute(attr));
    if (nested.length) {
      return nested;
    }
  }
  return undefined;
}

function toFiniteNumberOptional(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function normalizeId(rawValue: unknown, fallback: string): string {
  const normalized = String(rawValue || "").trim();
  if (!normalized) {
    return fallback;
  }
  return normalized.toLowerCase();
}

function normalizeStringList(
  value: unknown,
  {
    limit = 10,
    maxItemLength = 180,
  }: {
    limit?: number;
    maxItemLength?: number;
  } = {},
): string[] {
  const rows = Array.isArray(value) ? value : [value];
  const output: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const text = normalizeText(String(row || "")).slice(0, maxItemLength);
    if (!text) {
      continue;
    }
    const lowered = text.toLowerCase();
    if (seen.has(lowered)) {
      continue;
    }
    seen.add(lowered);
    output.push(text);
    if (output.length >= Math.max(1, limit)) {
      break;
    }
  }
  return output;
}

function parseStringListAttribute(details: Element, listAttr: string, singleAttr: string): string[] {
  const explicit = details.getAttribute(listAttr);
  if (explicit) {
    try {
      const parsed = JSON.parse(explicit);
      const normalized = normalizeStringList(parsed);
      if (normalized.length) {
        return normalized;
      }
    } catch {
      const normalized = normalizeStringList(explicit.split(","));
      if (normalized.length) {
        return normalized;
      }
    }
  }
  return normalizeStringList(details.getAttribute(singleAttr));
}

function parseEvidenceItemsFromInfoPanel(rawInfoPanel: unknown): EvidenceCard[] {
  if (!rawInfoPanel || typeof rawInfoPanel !== "object") {
    return [];
  }
  const infoPanel = rawInfoPanel as Record<string, unknown>;
  const rawItems = Array.isArray(infoPanel.evidence_items)
    ? infoPanel.evidence_items
    : Array.isArray(infoPanel.evidenceItems)
      ? infoPanel.evidenceItems
      : [];
  if (!rawItems.length) {
    return [];
  }
  const cards: EvidenceCard[] = [];
  for (let index = 0; index < rawItems.length && cards.length < 64; index += 1) {
    const row = rawItems[index];
    if (!row || typeof row !== "object") {
      continue;
    }
    const item = row as Record<string, unknown>;
    const sourceMap = item.source && typeof item.source === "object" ? (item.source as Record<string, unknown>) : {};
    const reviewLocation =
      item.review_location && typeof item.review_location === "object"
        ? (item.review_location as Record<string, unknown>)
        : item.reviewLocation && typeof item.reviewLocation === "object"
          ? (item.reviewLocation as Record<string, unknown>)
          : {};
    const highlightTarget =
      item.highlight_target && typeof item.highlight_target === "object"
        ? (item.highlight_target as Record<string, unknown>)
        : item.highlightTarget && typeof item.highlightTarget === "object"
          ? (item.highlightTarget as Record<string, unknown>)
          : {};
    const evidenceQuality =
      item.evidence_quality && typeof item.evidence_quality === "object"
        ? (item.evidence_quality as Record<string, unknown>)
        : item.evidenceQuality && typeof item.evidenceQuality === "object"
          ? (item.evidenceQuality as Record<string, unknown>)
          : {};
    const citationMap =
      item.citation && typeof item.citation === "object" ? (item.citation as Record<string, unknown>) : {};
    const highlightBoxesRaw = Array.isArray(item.highlight_boxes)
      ? item.highlight_boxes
      : Array.isArray(item.highlightBoxes)
        ? item.highlightBoxes
        : Array.isArray(highlightTarget.boxes)
          ? highlightTarget.boxes
          : highlightTarget.region && typeof highlightTarget.region === "object"
            ? [highlightTarget.region]
            : item.region && typeof item.region === "object"
              ? [item.region]
        : [];
    const highlightBoxes = highlightBoxesRaw
      .map((entry) => normalizeHighlightBox(entry))
      .filter((entry): entry is HighlightBox => Boolean(entry));
    const evidenceUnits = normalizeEvidenceUnits(
      item.evidence_units ??
        item.evidenceUnits ??
        highlightTarget.units ??
        highlightTarget.evidence_units,
    );
    const graphNodeIds = normalizeStringList(item.graph_node_ids ?? item.graphNodeIds);
    const sceneRefs = normalizeStringList(item.scene_refs ?? item.sceneRefs);
    const eventRefs = normalizeStringList(item.event_refs ?? item.eventRefs);
    const source = normalizeText(
      String(item.source_name || item.source || item.title || `Indexed source ${index + 1}`),
    );
    const extract = normalizeText(
      String(item.extract || item.snippet || citationMap.quote || highlightTarget.phrase || item.title || ""),
    ).trim();
    const score = toFiniteNumberOptional(item.strength_score ?? item.strengthScore ?? evidenceQuality.score);
    const tier = toFiniteNumberOptional(item.strength_tier ?? item.strengthTier ?? evidenceQuality.tier);
    const confidence = toFiniteNumberOptional(item.confidence ?? evidenceQuality.confidence);
    const charStart = toFiniteNumberOptional(item.char_start ?? item.charStart ?? highlightTarget.char_start ?? highlightTarget.charStart);
    const charEnd = toFiniteNumberOptional(item.char_end ?? item.charEnd ?? highlightTarget.char_end ?? highlightTarget.charEnd);
    const selector = normalizeText(
      String(
        item.selector ||
          highlightTarget.selector ||
          reviewLocation.selector ||
          "",
      ),
    ).trim();
    const reviewSurface = normalizeText(String(reviewLocation.surface || "")).trim().toLowerCase();
    const inferredSourceType =
      normalizeText(String(item.source_type || item.sourceType || sourceMap.type || "")).trim().toLowerCase() ||
      (reviewSurface === "web" ? "web" : reviewSurface === "pdf" ? "pdf" : "");
    cards.push({
      id: normalizeId(item.id ?? item.evidence_id ?? item.evidenceId, `evidence-${index + 1}`),
      title: normalizeText(String(item.title || `Evidence [${index + 1}]`)),
      source: source || "Indexed source",
      sourceType: inferredSourceType || undefined,
      sourceUrl: normalizeHttpUrl(item.source_url ?? item.sourceUrl ?? sourceMap.url ?? reviewLocation.source_url ?? reviewLocation.sourceUrl) || undefined,
      page: normalizeText(String(item.page ?? sourceMap.page ?? reviewLocation.page ?? "")).trim() || undefined,
      fileId: normalizeText(String(item.file_id ?? item.fileId ?? sourceMap.file_id ?? sourceMap.fileId ?? reviewLocation.file_id ?? reviewLocation.fileId ?? "")).trim() || undefined,
      extract: extract || "No extract available for this citation.",
      highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
      evidenceUnits,
      confidence: typeof confidence === "number" ? confidence : undefined,
      collectedBy: normalizeText(String(item.collected_by || item.collectedBy || "")).trim() || undefined,
      graphNodeIds: graphNodeIds.length ? graphNodeIds : undefined,
      sceneRefs: sceneRefs.length ? sceneRefs : undefined,
      eventRefs: eventRefs.length ? eventRefs : undefined,
      strengthScore: typeof score === "number" ? score : undefined,
      strengthTier: typeof tier === "number" ? tier : undefined,
      matchQuality: normalizeText(String(item.match_quality || item.matchQuality || evidenceQuality.match_quality || evidenceQuality.matchQuality || "")).trim() || undefined,
      unitId: normalizeText(String(item.unit_id || item.unitId || highlightTarget.unit_id || highlightTarget.unitId || "")).trim() || undefined,
      selector: selector || undefined,
      charStart: typeof charStart === "number" ? charStart : undefined,
      charEnd: typeof charEnd === "number" ? charEnd : undefined,
    });
  }
  return cards;
}

function parseEvidence(
  infoHtml: string,
  options?: {
    infoPanel?: Record<string, unknown> | null;
    userPrompt?: string;
    promptAttachments?: Array<{
      name?: string;
      fileId?: string;
      file_id?: string;
    }> | null;
  },
): EvidenceCard[] {
  const panelCards = parseEvidenceItemsFromInfoPanel(options?.infoPanel || null);
  if (panelCards.length) {
    return panelCards;
  }
  const promptCards = parsePromptEvidence({
    userPrompt: options?.userPrompt,
    promptAttachments: options?.promptAttachments,
  });
  if (!infoHtml.trim()) {
    return promptCards;
  }

  const doc = new DOMParser().parseFromString(infoHtml, "text/html");
  const detailsNodes = Array.from(doc.querySelectorAll("details.evidence"));
  if (!detailsNodes.length) {
    if (promptCards.length) {
      return promptCards;
    }
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
    const evidenceUnits = parseEvidenceUnitsFromDetails(details);
    const rawStrength = Number(details.getAttribute("data-strength") || "");
    const strengthScore = Number.isFinite(rawStrength) ? rawStrength : undefined;
    const rawStrengthTier = Number(details.getAttribute("data-strength-tier") || "");
    const strengthTier = Number.isFinite(rawStrengthTier) ? rawStrengthTier : undefined;
    const rawConfidence = Number(details.getAttribute("data-confidence") || "");
    const confidence = Number.isFinite(rawConfidence) ? rawConfidence : undefined;
    const collectedBy = normalizeText(details.getAttribute("data-collected-by") || "").trim() || undefined;
    const sourceType = normalizeText(details.getAttribute("data-source-type") || "").trim().toLowerCase() || undefined;
    const graphNodeIds = parseStringListAttribute(details, "data-graph-node-ids", "data-graph-node-id");
    const sceneRefs = parseStringListAttribute(details, "data-scene-refs", "data-scene-ref");
    const eventRefs = parseStringListAttribute(details, "data-event-refs", "data-event-ref");
    const matchQuality = (details.getAttribute("data-match-quality") || "").trim() || undefined;
    const unitId = (details.getAttribute("data-unit-id") || "").trim() || undefined;
    const selector = normalizeText(details.getAttribute("data-selector") || "").trim() || undefined;
    const rawCharStart = Number(details.getAttribute("data-char-start") || "");
    const rawCharEnd = Number(details.getAttribute("data-char-end") || "");
    const charStart = Number.isFinite(rawCharStart) ? rawCharStart : undefined;
    const charEnd = Number.isFinite(rawCharEnd) ? rawCharEnd : undefined;

    return {
      id: detailsId || `evidence-${index + 1}`,
      title: summary,
      source,
      sourceType,
      sourceUrl,
      page: pageAttr || pageMatch?.[1],
      fileId,
      extract,
      imageSrc,
      highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
      evidenceUnits,
      confidence,
      collectedBy,
      graphNodeIds: graphNodeIds.length ? graphNodeIds : undefined,
      sceneRefs: sceneRefs.length ? sceneRefs : undefined,
      eventRefs: eventRefs.length ? eventRefs : undefined,
      strengthScore,
      strengthTier,
      matchQuality,
      unitId,
      selector,
      charStart,
      charEnd,
    };
  });
}

export { parseEvidence };
