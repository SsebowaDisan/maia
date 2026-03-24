import { marked } from "marked";
import katex from "katex";

const MATH_SENTINEL_PREFIX = "__MAIA_MATH_SENTINEL__";
const CITATION_HTML_ANCHOR_RE =
  /<a\b[^>]*class=['"][^'"]*\bcitation\b[^'"]*['"][^>]*>[\s\S]*?<\/a>/gi;

function escapeHtml(raw: string): string {
  return String(raw || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function mathSentinelToken(index: number): string {
  return `${MATH_SENTINEL_PREFIX}${index}__`;
}

function looksLikeLatexExpression(source: string): boolean {
  const text = String(source || "").trim();
  if (!text) {
    return false;
  }
  if (/\\[a-zA-Z]+/.test(text)) {
    return true;
  }
  if (/[{}_^]/.test(text)) {
    return true;
  }
  if (/[=<>]/.test(text) && /\d/.test(text)) {
    return true;
  }
  return false;
}

function normalizeEscapedDollarDelimiters(input: string): string {
  if (!input.includes("\\$")) {
    return input;
  }
  return input.replace(/\\\$\s*([\s\S]*?)\s*\\\$/g, (fullMatch, body) => {
    const latex = String(body || "").trim();
    if (!looksLikeLatexExpression(latex)) {
      return fullMatch;
    }
    const delimiter = latex.includes("\n") ? "$$" : "$";
    return `${delimiter}${latex}${delimiter}`;
  });
}

function normalizeStandaloneLatexLines(input: string): string {
  const text = String(input || "");
  if (!text || text.indexOf("\\") < 0) {
    return text;
  }
  const lines = text.split("\n");
  let insideEscapedDisplayBlock = false;
  const normalized = lines.map((line) => {
    const original = String(line || "");
    const trimmed = original.trim();
    if (!trimmed) {
      return original;
    }
    if (trimmed === "\\[") {
      insideEscapedDisplayBlock = true;
      return original;
    }
    if (trimmed === "\\]") {
      insideEscapedDisplayBlock = false;
      return original;
    }
    if (insideEscapedDisplayBlock) {
      return original;
    }
    if (trimmed.startsWith("$") || trimmed.startsWith("\\(") || trimmed.startsWith("\\[")) {
      return original;
    }
    if (trimmed.startsWith("#") || /^[-*+]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) {
      return original;
    }
    const startsAsLatex = /^\\[a-zA-Z]+/.test(trimmed);
    if (!startsAsLatex || !looksLikeLatexExpression(trimmed)) {
      return original;
    }
    return `$$${trimmed}$$`;
  });
  return normalized.join("\n");
}

function renderKatexMath(latex: string, displayMode: boolean): string {
  const normalizedLatex = sanitizeLatexSource(latex);
  if (!normalizedLatex) {
    const source = displayMode ? `$$${latex}$$` : `$${latex}$`;
    return `<code>${escapeHtml(source)}</code>`;
  }
  try {
    const rendered = katex.renderToString(normalizedLatex, {
      displayMode,
      throwOnError: true,
    });
    return `<span data-math-rendered="true" data-math-display="${displayMode ? "true" : "false"}">${rendered}</span>`;
  } catch {
    return `<span data-math-fallback="true" data-math-display="${displayMode ? "true" : "false"}">${escapeHtml(normalizedLatex)}</span>`;
  }
}

function sanitizeLatexSource(rawLatex: string): string {
  let latex = String(rawLatex || "");
  if (!latex) {
    return "";
  }
  latex = latex.replace(
    /<a\b[^>]*class=['"][^'"]*\bcitation\b[^'"]*['"][^>]*>([\s\S]*?)<\/a>/gi,
    (_full, inner) => {
      const visible = String(inner || "").replace(/<\/?[^>]+>/g, "").trim();
      if (!visible) {
        return "";
      }
      const numericOnly = visible.replace(/[^\d.+\-/*=]/g, "");
      if (numericOnly && /^[-+/*=.\d]+$/.test(numericOnly)) {
        return numericOnly;
      }
      return "";
    },
  );
  // LLM streams occasionally double-escape latex commands, e.g. "\\frac".
  latex = latex.replace(/\\\\(?=[a-zA-Z])/g, "\\");
  latex = latex.replace(/<\/?[^>]+>/g, "");
  latex = latex.replace(
    /(?:^|[\s(])(?:\[(\d{1,4})\]|【\d{1,4}】|\{\d{1,4}\})(?=\s|[).,;:!?]|$)/g,
    " ",
  );
  latex = normalizeLatexFractions(latex);
  latex = latex.replace(/\s+/g, " ").trim();
  return latex.trim();
}

function normalizeLatexFractions(input: string): string {
  let latex = String(input || "");
  if (!latex.includes("\\frac")) {
    return latex;
  }
  // \frac12 -> \frac{1}{2}
  latex = latex.replace(/\\frac\s*([0-9a-zA-Z])\s*([0-9a-zA-Z])/g, "\\frac{$1}{$2}");
  // \frac3 -> \frac{1}{3} (frequent shorthand from streamed model output)
  latex = latex.replace(
    /\\frac\s*{?([0-9a-zA-Z]+)}?(?=(?:\s*[=+\-*/,.;:)|\\]|$))/g,
    (_full, denominator) => `\\frac{1}{${denominator}}`,
  );
  return latex;
}

function replaceDisplayMathSegments(
  input: string,
  onSegment: (latex: string, displayMode: boolean) => string,
): string {
  if (!input.includes("$$")) {
    return input;
  }
  let result = "";
  let cursor = 0;
  while (cursor < input.length) {
    const opensDisplay =
      input[cursor] === "$" &&
      input[cursor + 1] === "$" &&
      (cursor === 0 || input[cursor - 1] !== "\\");
    if (!opensDisplay) {
      result += input[cursor];
      cursor += 1;
      continue;
    }

    let end = cursor + 2;
    let closingIndex = -1;
    while (end < input.length - 1) {
      const closesDisplay = input[end] === "$" && input[end + 1] === "$" && input[end - 1] !== "\\";
      if (closesDisplay) {
        closingIndex = end;
        break;
      }
      end += 1;
    }

    if (closingIndex < 0) {
      result += input[cursor];
      cursor += 1;
      continue;
    }

    const latex = input.slice(cursor + 2, closingIndex).trim();
    if (!latex) {
      result += input.slice(cursor, closingIndex + 2);
      cursor = closingIndex + 2;
      continue;
    }

    result += onSegment(latex, true);
    cursor = closingIndex + 2;
  }
  return result;
}

function replaceInlineMathSegments(
  input: string,
  onSegment: (latex: string, displayMode: boolean) => string,
): string {
  if (!input.includes("$")) {
    return input;
  }
  let result = "";
  let cursor = 0;
  while (cursor < input.length) {
    if (input[cursor] !== "$") {
      result += input[cursor];
      cursor += 1;
      continue;
    }

    const prev = cursor > 0 ? input[cursor - 1] : "";
    const next = input[cursor + 1] || "";
    const isEscaped = prev === "\\";
    const isCurrency = /\d/.test(next);
    const startsDisplay = next === "$";
    if (isEscaped || isCurrency || startsDisplay) {
      result += "$";
      cursor += 1;
      continue;
    }

    let end = cursor + 1;
    let closingIndex = -1;
    while (end < input.length) {
      const char = input[end];
      if (char === "\n") {
        break;
      }
      const closesInline = char === "$" && input[end - 1] !== "\\";
      if (closesInline) {
        closingIndex = end;
        break;
      }
      end += 1;
    }

    if (closingIndex < 0) {
      result += "$";
      cursor += 1;
      continue;
    }

    const latex = input.slice(cursor + 1, closingIndex).trim();
    if (!latex) {
      result += input.slice(cursor, closingIndex + 1);
      cursor = closingIndex + 1;
      continue;
    }

    result += onSegment(latex, false);
    cursor = closingIndex + 1;
  }
  return result;
}

function findUnescapedToken(input: string, token: string, fromIndex: number): number {
  if (!token) {
    return -1;
  }
  let cursor = fromIndex;
  while (cursor < input.length) {
    const index = input.indexOf(token, cursor);
    if (index < 0) {
      return -1;
    }
    let backslashes = 0;
    let check = index - 1;
    while (check >= 0 && input[check] === "\\") {
      backslashes += 1;
      check -= 1;
    }
    if (backslashes % 2 === 0) {
      return index;
    }
    cursor = index + token.length;
  }
  return -1;
}

function replaceEscapedDelimitedMathSegments(
  input: string,
  openToken: string,
  closeToken: string,
  displayMode: boolean,
  onSegment: (latex: string, displayMode: boolean) => string,
): string {
  if (!input.includes(openToken)) {
    return input;
  }
  let result = "";
  let cursor = 0;
  while (cursor < input.length) {
    const openIndex = findUnescapedToken(input, openToken, cursor);
    if (openIndex < 0) {
      result += input.slice(cursor);
      break;
    }
    result += input.slice(cursor, openIndex);
    const closeIndex = findUnescapedToken(input, closeToken, openIndex + openToken.length);
    if (closeIndex < 0) {
      result += input.slice(openIndex);
      break;
    }
    const latex = input.slice(openIndex + openToken.length, closeIndex).trim();
    if (!latex) {
      result += input.slice(openIndex, closeIndex + closeToken.length);
      cursor = closeIndex + closeToken.length;
      continue;
    }
    result += onSegment(latex, displayMode);
    cursor = closeIndex + closeToken.length;
  }
  return result;
}

function replaceBracketFenceMathSegments(
  input: string,
  onSegment: (latex: string, displayMode: boolean) => string,
): string {
  if (!input.includes("[") || !input.includes("]")) {
    return input;
  }
  return input.replace(
    /(^|\n)\[\s*\n([\s\S]*?)\n\](?=\n|$)/g,
    (match, leading, body) => {
      const latex = String(body || "").trim();
      if (!latex) {
        return match;
      }
      const likelyMath = /\\[a-zA-Z]+|[_^]|=|÷|×|∑|∫/.test(latex);
      if (!likelyMath) {
        return match;
      }
      return `${leading}${onSegment(latex, true)}`;
    },
  );
}

export function renderMathInMarkdown(markdown: string): string {
  const source = String(markdown ?? "");
  if (!source.trim()) {
    return source;
  }
  const normalizedSource = normalizeStandaloneLatexLines(
    normalizeEscapedDollarDelimiters(source),
  );

  const mathSegments: string[] = [];
  const renderWithSentinel = (latex: string, displayMode: boolean): string => {
    const token = mathSentinelToken(mathSegments.length);
    mathSegments.push(renderKatexMath(latex, displayMode));
    return token;
  };

  const withDisplayMath = replaceDisplayMathSegments(normalizedSource, renderWithSentinel);
  const withEscapedDisplayMath = replaceEscapedDelimitedMathSegments(
    withDisplayMath,
    "\\[",
    "\\]",
    true,
    renderWithSentinel,
  );
  const withBracketFenceDisplayMath = replaceBracketFenceMathSegments(
    withEscapedDisplayMath,
    renderWithSentinel,
  );
  const withInlineMath = replaceInlineMathSegments(withBracketFenceDisplayMath, renderWithSentinel);
  const withEscapedInlineMath = replaceEscapedDelimitedMathSegments(
    withInlineMath,
    "\\(",
    "\\)",
    false,
    renderWithSentinel,
  );

  return mathSegments.reduce(
    (next, renderedMath, index) => next.replaceAll(mathSentinelToken(index), renderedMath),
    withEscapedInlineMath,
  );
}

const ALLOWED_TAGS = new Set([
  "A",
  "ANNOTATION",
  "B",
  "BLOCKQUOTE",
  "BR",
  "CIRCLE",
  "CODE",
  "DEFS",
  "DEL",
  "DETAILS",
  "DIV",
  "EM",
  "FIGCAPTION",
  "FIGURE",
  "G",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HR",
  "I",
  "IMG",
  "LINE",
  "LI",
  "MATH",
  "MARK",
  "MI",
  "MN",
  "MO",
  "MROW",
  "OL",
  "PATH",
  "P",
  "PRE",
  "RECT",
  "SEMANTICS",
  "SVG",
  "SPAN",
  "STRONG",
  "SUMMARY",
  "TABLE",
  "TBODY",
  "TD",
  "TH",
  "THEAD",
  "TR",
  "TITLE",
  "UL",
  "USE",
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
  ANNOTATION: new Set(["encoding"]),
  DIV: new Set(["class", "id"]),
  EM: new Set(["class", "id"]),
  FIGCAPTION: new Set(["class", "id"]),
  FIGURE: new Set(["class", "id"]),
  CIRCLE: new Set(["class", "cx", "cy", "fill", "r", "stroke", "stroke-width"]),
  DEFS: new Set(["class", "id"]),
  G: new Set(["class", "fill", "opacity", "stroke", "stroke-width", "transform"]),
  H1: new Set(["class", "id"]),
  H2: new Set(["class", "id"]),
  H3: new Set(["class", "id"]),
  H4: new Set(["class", "id"]),
  H5: new Set(["class", "id"]),
  H6: new Set(["class", "id"]),
  I: new Set(["class", "id"]),
  IMG: new Set(["alt", "class", "id", "src"]),
  LINE: new Set(["class", "stroke", "stroke-width", "x1", "x2", "y1", "y2"]),
  LI: new Set(["class", "id"]),
  MATH: new Set(["class", "display", "xmlns"]),
  MARK: new Set(["class", "id"]),
  MI: new Set(["class"]),
  MN: new Set(["class"]),
  MO: new Set(["class"]),
  MROW: new Set(["class"]),
  OL: new Set(["class", "id"]),
  PATH: new Set([
    "class",
    "d",
    "fill",
    "opacity",
    "stroke",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-width",
    "transform",
  ]),
  P: new Set(["class", "id"]),
  PRE: new Set(["class", "id"]),
  RECT: new Set(["class", "fill", "height", "rx", "ry", "stroke", "stroke-width", "width", "x", "y"]),
  SEMANTICS: new Set(["class"]),
  SVG: new Set([
    "aria-hidden",
    "class",
    "focusable",
    "height",
    "preserveaspectratio",
    "role",
    "viewbox",
    "width",
    "xmlns",
  ]),
  SPAN: new Set([
    "aria-hidden",
    "class",
    "data-math-display",
    "data-math-fallback",
    "data-math-rendered",
    "id",
    "style",
  ]),
  STRONG: new Set(["class", "id"]),
  SUMMARY: new Set(["class", "id"]),
  TABLE: new Set(["class", "id"]),
  TBODY: new Set(["class", "id"]),
  TD: new Set(["class", "colspan", "id", "rowspan"]),
  TH: new Set(["class", "colspan", "id", "rowspan"]),
  THEAD: new Set(["class", "id"]),
  TITLE: new Set(["class", "id"]),
  TR: new Set(["class", "id"]),
  UL: new Set(["class", "id"]),
  USE: new Set(["class", "href", "xlink:href"]),
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

function splitDenseParagraphBlock(block: string): string {
  const text = String(block || "").trim();
  if (!text) {
    return block;
  }
  const looksStructured =
    /(^|\n)\s*(#{1,6}\s|[-*+]\s|\d+\.\s|>|```|\|)/.test(text) ||
    text.includes("$$") ||
    text.includes("\n");
  if (looksStructured || text.length < 520) {
    return text;
  }

  const sentenceMatches = text.match(/.+?(?:[.!?](?=\s+[A-Z(])|[.!?]$|$)/g) || [];
  const sentences = sentenceMatches.map((sentence) => sentence.trim()).filter(Boolean);
  if (sentences.length < 4) {
    return text;
  }

  const paragraphs: string[] = [];
  let current = "";
  let sentenceCount = 0;
  for (const sentence of sentences) {
    const next = current ? `${current} ${sentence}` : sentence;
    current = next;
    sentenceCount += 1;
    const shouldBreak =
      (sentenceCount >= 2 && current.length >= 280) ||
      sentenceCount >= 3;
    if (shouldBreak) {
      paragraphs.push(current.trim());
      current = "";
      sentenceCount = 0;
    }
  }
  if (current.trim()) {
    paragraphs.push(current.trim());
  }
  return paragraphs.length >= 2 ? paragraphs.join("\n\n") : text;
}

function splitDenseParagraphs(input: string): string {
  const raw = String(input || "");
  if (!raw.trim()) {
    return raw;
  }
  const blocks = raw.split(/\n{2,}/);
  return blocks.map((block) => splitDenseParagraphBlock(block)).join("\n\n");
}

export function splitDenseParagraphsForTest(input: string): string {
  return splitDenseParagraphs(input);
}

function normalizeMarkdownBlocks(input: string): string {
  let normalized = repairCitationBrokenLinks(input.replace(/\r\n/g, "\n"));
  normalized = splitDenseParagraphs(normalized);
  // Some streamed payloads may lose newline before headings or list markers.
  normalized = normalized.replace(/([^\n])\s(#{1,6}\s+)/g, "$1\n\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+(\d+\.\s+)/g, "$1\n$2");
  normalized = normalized.replace(/(#{1,6}[^\n]+)\s+([-*]\s+)/g, "$1\n$2");
  // Promote inline bold pseudo-headings into real markdown headings when the
  // model emits section titles inside prose instead of on their own lines.
  normalized = normalized.replace(
    /([.!?])\s+\*\*([^*\n]{4,90})\*\*\s+(?=[A-Z(])/g,
    "$1\n\n## $2\n\n",
  );
  normalized = normalized.replace(/^\s*\*\*([^*\n]{4,90})\*\*\s*$/gm, "## $1");
  normalized = normalized.replace(
    /^\s*\*\*([^*\n]{4,90})\*\*\s+(?=[A-Z(])/gm,
    "## $1\n\n",
  );
  normalized = normalized.replace(/([^\n])\n(##\s+)/g, "$1\n\n$2");
  normalized = normalized.replace(/(##[^\n]+)\n([^\n#*-])/g, "$1\n\n$2");
  normalized = normalized.replace(/(\$\$[\s\S]*?\$\$)([^\n])/g, "$1\n\n$2");
  normalized = normalized.replace(/([^\n])(\$\$[\s\S]*?\$\$)/g, "$1\n\n$2");
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
