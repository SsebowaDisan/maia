import type { CitationHighlightBox } from "../types";

export type SpanSegment = {
  node: HTMLSpanElement;
  start: number;
  end: number;
  text: string;
};

type SpanRange = {
  startIndex: number;
  endIndex: number;
};

export type OverlayRect = {
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
};

type PixelRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

export function normalizeWhitespace(input: string): string {
  return String(input || "").replace(/\s+/g, " ").trim();
}

export function normalizeSearchText(input: string): string {
  return normalizeWhitespace(input)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function parsePageNumber(pageLabel?: string): number {
  const raw = normalizeWhitespace(pageLabel || "");
  const match = raw.match(/(\d{1,4})/);
  if (!match?.[1]) {
    return 1;
  }
  const parsed = Number.parseInt(match[1], 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

export function buildSearchCandidates(rawText: string): string[] {
  const normalized = normalizeSearchText(rawText);
  if (!normalized || normalized.length < 8) {
    return [];
  }
  const sentenceChunks = String(rawText || "")
    .split(/[.!?;\n\r]+/)
    .map((chunk) => normalizeSearchText(chunk))
    .filter((chunk) => chunk.length >= 10)
    .slice(0, 8);
  const firstSentence = sentenceChunks[0] || "";

  const ngrams: string[] = [];
  const seededChunks = [normalized, ...sentenceChunks];
  for (const chunk of seededChunks) {
    const words = chunk.split(" ").filter(Boolean);
    if (words.length < 3) {
      continue;
    }
    const maxWidth = Math.min(12, words.length);
    const minWidth = Math.min(3, maxWidth);
    for (let width = maxWidth; width >= minWidth; width -= 1) {
      for (let idx = 0; idx <= words.length - width; idx += 1) {
        const phrase = words.slice(idx, idx + width).join(" ").trim();
        if (phrase.length >= 12) {
          ngrams.push(phrase);
        }
        if (ngrams.length >= 80) {
          break;
        }
      }
      if (ngrams.length >= 80) {
        break;
      }
    }
    if (ngrams.length >= 80) {
      break;
    }
  }
  const uniqueCandidates = Array.from(new Set([normalized, ...sentenceChunks, ...ngrams]))
    .filter((candidate) => candidate.length >= 10)
    .slice(0, 120);
  const firstSentenceLead =
    firstSentence && uniqueCandidates.includes(firstSentence) ? [firstSentence] : [];
  const rankedRemainder = uniqueCandidates
    .filter((candidate) => candidate !== firstSentence)
    .sort((a, b) => b.length - a.length);
  return [...firstSentenceLead, ...rankedRemainder].slice(0, 80);
}

export function overlayRectsEqual(a: OverlayRect[], b: OverlayRect[]): boolean {
  if (a.length !== b.length) {
    return false;
  }
  for (let index = 0; index < a.length; index += 1) {
    const left = a[index];
    const right = b[index];
    if (
      Math.abs(left.leftPct - right.leftPct) > 0.01 ||
      Math.abs(left.topPct - right.topPct) > 0.01 ||
      Math.abs(left.widthPct - right.widthPct) > 0.01 ||
      Math.abs(left.heightPct - right.heightPct) > 0.01
    ) {
      return false;
    }
  }
  return true;
}

export function normalizeExternalOverlayRects(
  boxes: CitationHighlightBox[] | undefined,
): OverlayRect[] {
  if (!Array.isArray(boxes) || !boxes.length) {
    return [];
  }
  const normalized: OverlayRect[] = [];
  for (const box of boxes) {
    if (!box || typeof box !== "object") {
      continue;
    }
    const x = Number(box.x);
    const y = Number(box.y);
    const width = Number(box.width);
    const height = Number(box.height);
    if (![x, y, width, height].every((value) => Number.isFinite(value))) {
      continue;
    }
    const left = Math.max(0, Math.min(1, x));
    const top = Math.max(0, Math.min(1, y));
    const normalizedWidth = Math.max(0, Math.min(1 - left, width));
    const normalizedHeight = Math.max(0, Math.min(1 - top, height));
    if (normalizedWidth < 0.002 || normalizedHeight < 0.002) {
      continue;
    }
    normalized.push({
      leftPct: Number((left * 100).toFixed(4)),
      topPct: Number((top * 100).toFixed(4)),
      widthPct: Number((normalizedWidth * 100).toFixed(4)),
      heightPct: Number((normalizedHeight * 100).toFixed(4)),
    });
    if (normalized.length >= 24) {
      break;
    }
  }
  return normalized;
}

function mergeRectsByLine(rects: PixelRect[]): PixelRect[] {
  if (!rects.length) {
    return [];
  }
  const sorted = [...rects].sort((a, b) => {
    const topDiff = a.top - b.top;
    if (Math.abs(topDiff) > 1) {
      return topDiff;
    }
    return a.left - b.left;
  });
  const merged: PixelRect[] = [];
  for (const rect of sorted) {
    const previous = merged[merged.length - 1];
    if (!previous) {
      merged.push({ ...rect });
      continue;
    }

    const verticalOverlap =
      Math.min(previous.top + previous.height, rect.top + rect.height) -
      Math.max(previous.top, rect.top);
    const sameLine =
      verticalOverlap >= Math.min(previous.height, rect.height) * 0.45 &&
      Math.abs(previous.top - rect.top) <= Math.max(previous.height, rect.height) * 0.7;
    const closeHorizontally = rect.left <= previous.left + previous.width + 10;

    if (sameLine && closeHorizontally) {
      const left = Math.min(previous.left, rect.left);
      const right = Math.max(previous.left + previous.width, rect.left + rect.width);
      const top = Math.min(previous.top, rect.top);
      const bottom = Math.max(previous.top + previous.height, rect.top + rect.height);
      previous.left = left;
      previous.top = top;
      previous.width = right - left;
      previous.height = bottom - top;
      continue;
    }
    merged.push({ ...rect });
  }
  return merged;
}

export function buildOverlayRectsForRange(
  pageSurface: HTMLElement,
  segments: SpanSegment[],
  range: SpanRange,
): OverlayRect[] {
  const surfaceRect = pageSurface.getBoundingClientRect();
  if (surfaceRect.width <= 0 || surfaceRect.height <= 0) {
    return [];
  }

  const rawRects: PixelRect[] = [];
  for (let index = range.startIndex; index <= range.endIndex; index += 1) {
    const node = segments[index]?.node;
    if (!node) {
      continue;
    }
    const rect = node.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      continue;
    }
    rawRects.push({
      left: rect.left - surfaceRect.left,
      top: rect.top - surfaceRect.top,
      width: rect.width,
      height: rect.height,
    });
  }

  const mergedRects = mergeRectsByLine(rawRects);
  return mergedRects
    .map((rect) => {
      const padX = 1.2;
      const padY = 0.8;
      const leftPx = Math.max(0, rect.left - padX);
      const topPx = Math.max(0, rect.top - padY);
      const widthPx = Math.min(surfaceRect.width - leftPx, rect.width + padX * 2);
      const heightPx = Math.min(surfaceRect.height - topPx, rect.height + padY * 2);
      if (widthPx <= 0 || heightPx <= 0) {
        return null;
      }
      return {
        leftPct: (leftPx / surfaceRect.width) * 100,
        topPct: (topPx / surfaceRect.height) * 100,
        widthPct: (widthPx / surfaceRect.width) * 100,
        heightPct: (heightPx / surfaceRect.height) * 100,
      };
    })
    .filter((rect): rect is OverlayRect => Boolean(rect));
}

export function collectSpanSegments(pageContainer: HTMLElement): {
  segments: SpanSegment[];
  combined: string;
} {
  const textLayer =
    pageContainer.querySelector<HTMLElement>(".react-pdf__Page__textContent") ||
    pageContainer.querySelector<HTMLElement>(".textLayer");
  let spanNodes = Array.from(textLayer?.querySelectorAll<HTMLSpanElement>("span") || []);
  if (!spanNodes.length) {
    // Fallback for renderer/classname variants.
    spanNodes = Array.from(
      pageContainer.querySelectorAll<HTMLSpanElement>(".react-pdf__Page span"),
    );
  }
  const segments: SpanSegment[] = [];
  let cursor = 0;
  let combined = "";
  for (const node of spanNodes) {
    const text = normalizeSearchText(node.textContent || "");
    if (!text) {
      continue;
    }
    const start = cursor;
    combined += text;
    cursor += text.length;
    const end = cursor;
    combined += " ";
    cursor += 1;
    segments.push({ node, start, end, text });
  }
  return { segments, combined };
}

function rangeForMatch(
  params: {
    segments: SpanSegment[];
    matchStart: number;
    matchEnd: number;
  },
): SpanRange | null {
  const { segments, matchStart, matchEnd } = params;
  if (!segments.length || matchEnd <= matchStart) {
    return null;
  }
  let startIndex = -1;
  let endIndex = -1;
  for (let idx = 0; idx < segments.length; idx += 1) {
    const segment = segments[idx];
    if (segment.end <= matchStart) {
      continue;
    }
    if (segment.start >= matchEnd) {
      break;
    }
    if (startIndex === -1) {
      startIndex = idx;
    }
    endIndex = idx;
  }
  if (startIndex === -1 || endIndex === -1) {
    return null;
  }
  return { startIndex, endIndex };
}

export function findRangeByCharOffsets(
  segments: SpanSegment[],
  charStart?: number,
  charEnd?: number,
): SpanRange | null {
  const start = Number(charStart);
  const end = Number(charEnd);
  if (!segments.length || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start) {
    return null;
  }
  return rangeForMatch({
    segments,
    matchStart: start,
    matchEnd: end,
  });
}

export function findHighlightRange(
  params: {
    segments: SpanSegment[];
    combined: string;
    candidates: string[];
  },
): SpanRange | null {
  const { segments, combined, candidates } = params;
  if (!segments.length || !combined) {
    return null;
  }
  for (const candidate of candidates) {
    const hitIndex = combined.indexOf(candidate);
    if (hitIndex < 0) {
      continue;
    }
    const range = rangeForMatch({
      segments,
      matchStart: hitIndex,
      matchEnd: hitIndex + candidate.length,
    });
    if (range) {
      return range;
    }
  }
  return null;
}

function rectToRoundedPath(rect: OverlayRect, radius = 0.5): string {
  const x = Number(rect.leftPct.toFixed(4));
  const y = Number(rect.topPct.toFixed(4));
  const width = Number(rect.widthPct.toFixed(4));
  const height = Number(rect.heightPct.toFixed(4));
  const rx = Math.min(radius, width / 2, height / 2);
  const right = x + width;
  const bottom = y + height;
  return [
    `M ${x + rx} ${y}`,
    `H ${right - rx}`,
    `Q ${right} ${y} ${right} ${y + rx}`,
    `V ${bottom - rx}`,
    `Q ${right} ${bottom} ${right - rx} ${bottom}`,
    `H ${x + rx}`,
    `Q ${x} ${bottom} ${x} ${bottom - rx}`,
    `V ${y + rx}`,
    `Q ${x} ${y} ${x + rx} ${y}`,
    "Z",
  ].join(" ");
}

export function buildOverlayPath(rects: OverlayRect[]): string {
  if (!rects.length) {
    return "";
  }
  return rects.map((rect) => rectToRoundedPath(rect)).join(" ");
}
