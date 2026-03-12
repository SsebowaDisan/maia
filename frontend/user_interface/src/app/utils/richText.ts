import { marked } from "marked";

const ALLOWED_TAGS = new Set([
  "A",
  "B",
  "BLOCKQUOTE",
  "BR",
  "CODE",
  "DEL",
  "DETAILS",
  "DIV",
  "EM",
  "FIGCAPTION",
  "FIGURE",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HR",
  "I",
  "IMG",
  "LI",
  "MARK",
  "OL",
  "P",
  "PRE",
  "SPAN",
  "STRONG",
  "SUMMARY",
  "TABLE",
  "TBODY",
  "TD",
  "TH",
  "THEAD",
  "TR",
  "UL",
]);

const ALLOWED_ATTRIBUTES_BY_TAG: Record<string, Set<string>> = {
  A: new Set([
    "class",
    "href",
    "id",
    "rel",
    "target",
    "data-file-id",
    "data-source-url",
    "data-viewer-url",
    "data-page",
    "data-phrase",
    "data-strength",
    "data-strength-tier",
    "data-match-quality",
    "data-unit-id",
    "data-selector",
    "data-char-start",
    "data-char-end",
    "data-boxes",
    "data-bboxes",
    "data-search",
    "data-src",
    "data-evidence-id",
    "data-citation-number",
  ]),
  B: new Set(["class", "id"]),
  BLOCKQUOTE: new Set(["class", "id"]),
  CODE: new Set(["class", "id"]),
  DEL: new Set(["class", "id"]),
  DETAILS: new Set([
    "class",
    "id",
    "open",
    "data-file-id",
    "data-source-url",
    "data-viewer-url",
    "data-page",
    "data-strength",
    "data-strength-tier",
    "data-match-quality",
    "data-unit-id",
    "data-selector",
    "data-char-start",
    "data-char-end",
    "data-boxes",
    "data-bboxes",
  ]),
  DIV: new Set(["class", "id"]),
  EM: new Set(["class", "id"]),
  FIGCAPTION: new Set(["class", "id"]),
  FIGURE: new Set(["class", "id"]),
  H1: new Set(["class", "id"]),
  H2: new Set(["class", "id"]),
  H3: new Set(["class", "id"]),
  H4: new Set(["class", "id"]),
  H5: new Set(["class", "id"]),
  H6: new Set(["class", "id"]),
  I: new Set(["class", "id"]),
  IMG: new Set(["alt", "class", "id", "src"]),
  LI: new Set(["class", "id"]),
  MARK: new Set(["class", "id"]),
  OL: new Set(["class", "id"]),
  P: new Set(["class", "id"]),
  PRE: new Set(["class", "id"]),
  SPAN: new Set(["class", "id"]),
  STRONG: new Set(["class", "id"]),
  SUMMARY: new Set(["class", "id"]),
  TABLE: new Set(["class", "id"]),
  TBODY: new Set(["class", "id"]),
  TD: new Set(["class", "colspan", "id", "rowspan"]),
  TH: new Set(["class", "colspan", "id", "rowspan"]),
  THEAD: new Set(["class", "id"]),
  TR: new Set(["class", "id"]),
  UL: new Set(["class", "id"]),
  BR: new Set(),
  HR: new Set(),
};

function isSafeUrl(value: string, isImage: boolean): boolean {
  const lowered = value.trim().toLowerCase();
  if (!lowered) {
    return false;
  }
  if (lowered.startsWith("javascript:") || lowered.startsWith("data:text/html")) {
    return false;
  }
  if (isImage) {
    return (
      lowered.startsWith("https://") ||
      lowered.startsWith("http://") ||
      lowered.startsWith("data:image/")
    );
  }
  return (
    lowered.startsWith("https://") ||
    lowered.startsWith("http://") ||
    lowered.startsWith("#")
  );
}

function sanitizeHtml(html: string): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const elements = Array.from(doc.body.querySelectorAll("*"));

  for (const element of elements) {
    const tag = element.tagName.toUpperCase();
    if (!ALLOWED_TAGS.has(tag)) {
      element.replaceWith(doc.createTextNode(element.textContent || ""));
      continue;
    }

    const allowedAttrs = ALLOWED_ATTRIBUTES_BY_TAG[tag] || new Set<string>();
    for (const attr of Array.from(element.attributes)) {
      const attrName = attr.name.toLowerCase();
      const attrValue = attr.value;
      if (attrName.startsWith("on")) {
        element.removeAttribute(attr.name);
        continue;
      }

      if (!allowedAttrs.has(attr.name)) {
        element.removeAttribute(attr.name);
        continue;
      }

      if (tag === "A" && attrName === "href" && !isSafeUrl(attrValue, false)) {
        element.removeAttribute(attr.name);
      }
      if (tag === "IMG" && attrName === "src" && !isSafeUrl(attrValue, true)) {
        element.removeAttribute(attr.name);
      }
    }

    if (tag === "A") {
      const href = (element.getAttribute("href") || "").trim();
      if (href.startsWith("#")) {
        element.removeAttribute("target");
        element.removeAttribute("rel");
      } else {
        element.setAttribute("target", "_blank");
        element.setAttribute("rel", "noopener noreferrer");
      }
    }
  }

  return doc.body.innerHTML;
}

const CITATION_HTML_ANCHOR_RE =
  /<a\b[^>]*class=['"][^'"]*\bcitation\b[^'"]*['"][^>]*>[\s\S]*?<\/a>/gi;

function detachTrailingUrlPunctuation(rawUrl: string): { url: string; trailing: string } {
  let url = String(rawUrl || "").trim();
  let trailing = "";
  while (/[.,;:!?]$/.test(url)) {
    trailing = `${url.slice(-1)}${trailing}`;
    url = url.slice(0, -1);
  }
  return { url, trailing };
}

function repairCitationBrokenLinks(input: string): string {
  let text = String(input || "");
  if (!text || !/<a\b/i.test(text) || text.toLowerCase().indexOf("citation") < 0) {
    return text;
  }

  text = text.replace(/\[([^\]]+)\]\(([^)\n]+)\)/g, (fullMatch, label, rawUrl) => {
    const urlChunk = String(rawUrl || "");
    const citationAnchors = urlChunk.match(CITATION_HTML_ANCHOR_RE) || [];
    if (!citationAnchors.length) {
      return fullMatch;
    }
    const mergedUrl = urlChunk.replace(CITATION_HTML_ANCHOR_RE, "").replace(/\s+/g, "").trim();
    const normalized = detachTrailingUrlPunctuation(mergedUrl);
    if (!normalized.url || !/^https?:\/\//i.test(normalized.url)) {
      return fullMatch;
    }
    return `[${label}](${normalized.url})${citationAnchors.join("")}${normalized.trailing}`;
  });

  text = text.replace(
    /(https?:\/\/[^\s<>()]*?)((?:<a\b[^>]*class=['"][^'"]*\bcitation\b[^'"]*['"][^>]*>[\s\S]*?<\/a>)+)([^\s<>()]*)/gi,
    (fullMatch, leftUrl, anchors, rightUrlPart) => {
      const mergedUrl = `${String(leftUrl || "")}${String(rightUrlPart || "")}`
        .replace(/\s+/g, "")
        .trim();
      const normalized = detachTrailingUrlPunctuation(mergedUrl);
      if (!normalized.url || !/^https?:\/\//i.test(normalized.url)) {
        return fullMatch;
      }
      return `${normalized.url}${String(anchors || "")}${normalized.trailing}`;
    },
  );

  return text;
}

function normalizeMarkdownBlocks(input: string): string {
  let normalized = repairCitationBrokenLinks(input.replace(/\r\n/g, "\n"));
  // Some streamed payloads may lose newline before headings or list markers.
  normalized = normalized.replace(/([^\n])\s(#{1,6}\s+)/g, "$1\n\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+(\d+\.\s+)/g, "$1\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+([-*]\s+)/g, "$1\n$2");
  return normalized;
}

function countCitationAnchors(text: string): number {
  return (String(text || "").match(/<a\b[^>]*class=['"][^'"]*\bcitation\b[^'"]*['"][^>]*>/gi) || []).length;
}

function stripHtmlWithIndexMap(input: string): { plain: string; indexMap: number[] } {
  const raw = String(input || "");
  const plainChars: string[] = [];
  const indexMap: number[] = [];
  let inTag = false;
  for (let idx = 0; idx < raw.length; idx += 1) {
    const char = raw[idx];
    if (char === "<") {
      inTag = true;
      continue;
    }
    if (!inTag) {
      plainChars.push(char);
      indexMap.push(idx);
      continue;
    }
    if (char === ">") {
      inTag = false;
    }
  }
  return { plain: plainChars.join(""), indexMap };
}

function removeInlineMarkerTokensWithMap(
  plain: string,
  indexMap: number[],
): { plain: string; indexMap: number[] } {
  if (!plain || !indexMap.length || plain.length !== indexMap.length) {
    return { plain, indexMap };
  }
  const strippedChars: string[] = [];
  const strippedMap: number[] = [];
  let cursor = 0;
  while (cursor < plain.length) {
    const markerMatch = plain.slice(cursor).match(/^(?:\[|【|\{)\s*\d{1,4}\s*(?:\]|】|\})/);
    if (markerMatch?.[0]) {
      cursor += markerMatch[0].length;
      continue;
    }
    strippedChars.push(plain[cursor]);
    strippedMap.push(indexMap[cursor]);
    cursor += 1;
  }
  return { plain: strippedChars.join(""), indexMap: strippedMap };
}

function dedupeDuplicateCitationPasses(input: string): string {
  const raw = String(input || "");
  if (!raw.trim()) {
    return raw;
  }
  if (countCitationAnchors(raw) <= 0) {
    return raw;
  }

  const stripped = stripHtmlWithIndexMap(raw);
  const withoutMarkers = removeInlineMarkerTokensWithMap(stripped.plain, stripped.indexMap);
  const plain = withoutMarkers.plain;
  const indexMap = withoutMarkers.indexMap;
  if (!plain || !indexMap.length) {
    return raw;
  }

  const plainStart = plain.search(/\S/);
  if (plainStart < 0) {
    return raw;
  }
  const window = plain.slice(plainStart, plainStart + 320);
  if (window.length < 120) {
    return raw;
  }
  const sentenceMatch = window.match(/.{48,260}?[.!?]/);
  const signature = (sentenceMatch?.[0] || window.slice(0, 180))
    .trim()
    .replace(/[\s.,;:!?]+$/, "");
  if (signature.length < 48) {
    return raw;
  }

  const secondPlainIdx = plain.indexOf(signature, plainStart + signature.length);
  if (secondPlainIdx <= plainStart || secondPlainIdx >= indexMap.length) {
    return raw;
  }
  const secondRawIdx = indexMap[secondPlainIdx];
  if (!Number.isFinite(secondRawIdx) || secondRawIdx <= 0 || secondRawIdx >= raw.length) {
    return raw;
  }

  const prefix = raw.slice(0, secondRawIdx);
  const suffix = raw.slice(secondRawIdx);
  if (countCitationAnchors(suffix) <= countCitationAnchors(prefix)) {
    return raw;
  }

  const trimmed = suffix.trimStart();
  return trimmed || raw;
}

function toHtml(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) {
    return "";
  }
  const normalized = normalizeMarkdownBlocks(trimmed);

  const looksLikeMarkdown = /(^|\n)\s*(#{1,6}\s+|[-*+]\s+|\d+\.\s+)|```/.test(normalized);
  const hasHtmlTags = /<[a-z][\s\S]*>/i.test(normalized);
  if (hasHtmlTags && !looksLikeMarkdown) {
    return normalized;
  }

  return marked.parse(normalized, { gfm: true, breaks: true }) as string;
}

function normalizeHeadingText(value: string): string {
  return String(value || "")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
}

function extractEvidenceWrapperId(item: HTMLLIElement, fallbackIndex: number): string {
  const directId = String(item.getAttribute("id") || "").trim().match(/^(evidence-\d{1,4})$/i)?.[1];
  if (directId) {
    return directId.toLowerCase();
  }
  const annotated = item.querySelector<HTMLElement>("[data-evidence-id], [aria-controls], a[href^='#evidence-']");
  if (annotated) {
    const explicitEvidenceId = String(annotated.getAttribute("data-evidence-id") || "")
      .trim()
      .match(/(evidence-\d{1,4})/i)?.[1];
    if (explicitEvidenceId) {
      return explicitEvidenceId.toLowerCase();
    }
    const explicitHref = String(annotated.getAttribute("href") || "")
      .trim()
      .match(/#(evidence-\d{1,4})/i)?.[1];
    if (explicitHref) {
      return explicitHref.toLowerCase();
    }
    const explicitControls = String(annotated.getAttribute("aria-controls") || "")
      .trim()
      .match(/(evidence-\d{1,4})/i)?.[1];
    if (explicitControls) {
      return explicitControls.toLowerCase();
    }
  }
  const leadingRef = String(item.textContent || "").match(/^\s*(?:\[|【)?\s*(\d{1,4})\s*(?:\]|】|\))/);
  if (leadingRef?.[1]) {
    return `evidence-${leadingRef[1]}`;
  }
  return `evidence-${fallbackIndex}`;
}

function wrapEvidenceCitationTargets(html: string): string {
  if (!html || html.toLowerCase().indexOf("evidence citations") < 0) {
    return html;
  }

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const headings = Array.from(doc.body.querySelectorAll("h1, h2, h3, h4, h5, h6"));

  for (const heading of headings) {
    if (normalizeHeadingText(heading.textContent || "") !== "evidence citations") {
      continue;
    }
    let sibling = heading.nextElementSibling;
    while (sibling) {
      if (/^H[1-6]$/i.test(sibling.tagName)) {
        break;
      }
      if (sibling instanceof HTMLUListElement || sibling instanceof HTMLOListElement) {
        const items = Array.from(sibling.children).filter(
          (child): child is HTMLLIElement => child instanceof HTMLLIElement,
        );
        items.forEach((item, index) => {
          const evidenceId = extractEvidenceWrapperId(item, index + 1);
          const existingWrapper =
            item.children.length === 1 && item.firstElementChild instanceof HTMLDivElement
              ? item.firstElementChild
              : null;
          if (existingWrapper?.id === evidenceId) {
            return;
          }
          const wrapper = doc.createElement("div");
          wrapper.id = evidenceId;
          while (item.firstChild) {
            wrapper.appendChild(item.firstChild);
          }
          item.appendChild(wrapper);
        });
        break;
      }
      sibling = sibling.nextElementSibling;
    }
  }

  return doc.body.innerHTML;
}

export function renderRichText(input: string): string {
  if (!input.trim()) {
    return "";
  }
  const deduped = dedupeDuplicateCitationPasses(input);
  return sanitizeHtml(wrapEvidenceCitationTargets(toHtml(deduped)));
}
