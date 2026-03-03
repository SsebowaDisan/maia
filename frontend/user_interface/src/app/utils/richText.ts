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
    "data-page",
    "data-phrase",
    "data-strength",
    "data-strength-tier",
    "data-match-quality",
    "data-unit-id",
    "data-char-start",
    "data-char-end",
    "data-boxes",
    "data-search",
    "data-src",
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
    "data-page",
    "data-strength",
    "data-strength-tier",
    "data-match-quality",
    "data-unit-id",
    "data-char-start",
    "data-char-end",
    "data-boxes",
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

function normalizeMarkdownBlocks(input: string): string {
  let normalized = input.replace(/\r\n/g, "\n");
  // Some streamed payloads may lose newline before headings or list markers.
  normalized = normalized.replace(/([^\n])\s(#{1,6}\s+)/g, "$1\n\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+(\d+\.\s+)/g, "$1\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+([-*]\s+)/g, "$1\n$2");
  return normalized;
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

export function renderRichText(input: string): string {
  if (!input.trim()) {
    return "";
  }
  return sanitizeHtml(toHtml(input));
}
