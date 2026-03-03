import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import type { CitationHighlightBox } from "../types";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

interface CitationPdfPreviewProps {
  fileUrl: string;
  page?: string;
  highlightText: string;
  highlightQuery?: string;
  highlightBoxes?: CitationHighlightBox[];
}

function normalizeWhitespace(input: string): string {
  return String(input || "").replace(/\s+/g, " ").trim();
}

function normalizeSearchText(input: string): string {
  return normalizeWhitespace(input)
    .toLowerCase()
    .replace(/[^a-z0-9\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parsePageNumber(pageLabel?: string): number {
  const raw = normalizeWhitespace(pageLabel || "");
  const match = raw.match(/(\d{1,4})/);
  if (!match?.[1]) {
    return 1;
  }
  const parsed = Number.parseInt(match[1], 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

function buildSearchCandidates(rawText: string): string[] {
  const normalized = normalizeSearchText(rawText);
  if (!normalized || normalized.length < 8) {
    return [];
  }
  const primaryChunks = normalized
    .split(/[.!?;\n\r]+/)
    .map((chunk) => normalizeSearchText(chunk))
    .filter((chunk) => chunk.length >= 10);

  const ngrams: string[] = [];
  const seededChunks = [normalized, ...primaryChunks.slice(0, 8)];
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
  return Array.from(new Set([normalized, ...primaryChunks, ...ngrams]))
    .filter((candidate) => candidate.length >= 10)
    .sort((a, b) => b.length - a.length)
    .slice(0, 80);
}

type SpanSegment = {
  node: HTMLSpanElement;
  start: number;
  end: number;
  text: string;
};

type SpanRange = {
  startIndex: number;
  endIndex: number;
};

type OverlayRect = {
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

function overlayRectsEqual(a: OverlayRect[], b: OverlayRect[]): boolean {
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

function normalizeExternalOverlayRects(
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

function buildOverlayRectsForRange(
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

function collectSpanSegments(pageContainer: HTMLElement): {
  segments: SpanSegment[];
  combined: string;
} {
  const textLayer =
    pageContainer.querySelector<HTMLElement>(".react-pdf__Page__textContent") ||
    pageContainer.querySelector<HTMLElement>(".textLayer");
  let spanNodes = Array.from(textLayer?.querySelectorAll<HTMLSpanElement>("span") || []);
  if (!spanNodes.length) {
    // Fallback for renderer/classname variants.
    spanNodes = Array.from(pageContainer.querySelectorAll<HTMLSpanElement>(".react-pdf__Page span"));
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

function findHighlightRange(
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

export function CitationPdfPreview({
  fileUrl,
  page,
  highlightText,
  highlightQuery,
  highlightBoxes,
}: CitationPdfPreviewProps) {
  const requestedPageSafe = parsePageNumber(page);
  const [numPages, setNumPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(requestedPageSafe);
  const [pageWidth, setPageWidth] = useState(300);
  const [docReady, setDocReady] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const pageSurfaceRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const overlayRectsByPageRef = useRef<Record<number, OverlayRect[]>>({});
  const appliedHighlightKeyRef = useRef("");
  const syncLockRef = useRef(false);
  const highlightFocusAttemptsRef = useRef(0);
  const highlightFocusTimerRef = useRef<number | null>(null);
  const [overlayRectsByPage, setOverlayRectsByPage] = useState<Record<number, OverlayRect[]>>({});
  const [activeTargetPage, setActiveTargetPage] = useState(
    requestedPageSafe,
  );
  const searchCandidates = useMemo(() => {
    const merged = [
      ...buildSearchCandidates(highlightText),
      ...buildSearchCandidates(highlightQuery || ""),
    ];
    return Array.from(new Set(merged)).sort((a, b) => b.length - a.length).slice(0, 80);
  }, [highlightQuery, highlightText]);
  const externalOverlayRects = useMemo(
    () => normalizeExternalOverlayRects(highlightBoxes),
    [highlightBoxes],
  );
  const highlightRequestKey = useMemo(() => {
    const normalizedEvidence = normalizeSearchText(highlightText).slice(0, 220);
    const normalizedQuery = normalizeSearchText(highlightQuery || "").slice(0, 220);
    const overlayKey = externalOverlayRects
      .map((item) => `${item.leftPct},${item.topPct},${item.widthPct},${item.heightPct}`)
      .join("|");
    return `${fileUrl}::${requestedPageSafe}::${normalizedEvidence}::${normalizedQuery}::${overlayKey}`;
  }, [externalOverlayRects, fileUrl, highlightQuery, highlightText, requestedPageSafe]);

  const clampPage = (value: number) => Math.min(Math.max(1, value), Math.max(1, numPages));

  const scrollToPage = (targetPage: number, behavior: ScrollBehavior) => {
    const safePage = clampPage(targetPage);
    const target = pageRefs.current[safePage];
    if (!target) return;
    syncLockRef.current = true;
    target.scrollIntoView({ behavior, block: "start" });
    setCurrentPage(safePage);
    window.setTimeout(() => {
      syncLockRef.current = false;
    }, 220);
  };

  const stopHighlightFocusTimer = () => {
    if (highlightFocusTimerRef.current !== null) {
      window.clearTimeout(highlightFocusTimerRef.current);
      highlightFocusTimerRef.current = null;
    }
  };

  const applyOverlayRects = (targetPage: number, rects: OverlayRect[]) => {
    const nextPayload = { [targetPage]: rects };
    const currentPayload = overlayRectsByPageRef.current;
    const currentRects = currentPayload[targetPage] || [];
    const hasOnlyTargetPage =
      Object.keys(currentPayload).length === 1 && Boolean(currentPayload[targetPage]);
    if (hasOnlyTargetPage && overlayRectsEqual(currentRects, rects)) {
      return;
    }
    overlayRectsByPageRef.current = nextPayload;
    setOverlayRectsByPage(nextPayload);
  };

  const clearHighlights = () => {
    const hasHighlights = Object.keys(overlayRectsByPageRef.current).length > 0;
    overlayRectsByPageRef.current = {};
    if (hasHighlights) {
      setOverlayRectsByPage({});
    }
    appliedHighlightKeyRef.current = "";
  };

  const scrollToOverlayRect = (params: {
    pageSurface: HTMLElement;
    page: number;
    overlayRect: OverlayRect;
  }) => {
    const { pageSurface, page: targetPage, overlayRect } = params;
    const container = scrollRef.current;
    if (!container) {
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const pageRect = pageSurface.getBoundingClientRect();
    const targetTopPx = pageRect.top - containerRect.top + container.scrollTop;
    const overlayCenterPx =
      (overlayRect.topPct / 100) * pageRect.height + ((overlayRect.heightPct / 100) * pageRect.height) / 2;
    const desiredTop =
      targetTopPx + overlayCenterPx - Math.max(56, container.clientHeight * 0.35);
    syncLockRef.current = true;
    container.scrollTo({
      top: Math.max(0, desiredTop),
      behavior: "smooth",
    });
    setCurrentPage(targetPage);
    window.setTimeout(() => {
      syncLockRef.current = false;
    }, 240);
  };

  const tryFocusHighlight = (targetPage: number, appliedKey: string) => {
    const safePage = clampPage(targetPage);
    const pageSurface = pageSurfaceRefs.current[safePage];
    if (!pageSurface) {
      return false;
    }
    const currentRects = overlayRectsByPageRef.current[safePage] || [];
    if (appliedHighlightKeyRef.current === appliedKey && currentRects.length > 0) {
      return true;
    }
    if (externalOverlayRects.length) {
      applyOverlayRects(safePage, externalOverlayRects);
      scrollToOverlayRect({
        pageSurface,
        page: safePage,
        overlayRect: externalOverlayRects[0],
      });
      appliedHighlightKeyRef.current = appliedKey;
      return true;
    }
    if (!searchCandidates.length) {
      appliedHighlightKeyRef.current = appliedKey;
      return true;
    }
    const { segments, combined } = collectSpanSegments(pageSurface);
    const highlightRange = findHighlightRange({
      segments,
      combined,
      candidates: searchCandidates,
    });
    if (!highlightRange) {
      return false;
    }

    const overlayRects = buildOverlayRectsForRange(pageSurface, segments, highlightRange);
    if (!overlayRects.length) {
      return false;
    }
    applyOverlayRects(safePage, overlayRects);
    scrollToOverlayRect({
      pageSurface,
      page: safePage,
      overlayRect: overlayRects[0],
    });
    appliedHighlightKeyRef.current = appliedKey;
    return true;
  };

  const scheduleHighlightFocus = (targetPage: number, options?: { force?: boolean }) => {
    const force = Boolean(options?.force);
    const safePage = clampPage(targetPage);
    const appliedKey = `${highlightRequestKey}::${safePage}`;
    const currentRects = overlayRectsByPageRef.current[safePage] || [];
    if (!force && appliedHighlightKeyRef.current === appliedKey && currentRects.length > 0) {
      return;
    }
    stopHighlightFocusTimer();
    clearHighlights();
    highlightFocusAttemptsRef.current = 0;
    const maxAttempts = externalOverlayRects.length ? 18 : 80;
    const tick = () => {
      const hitFound = tryFocusHighlight(safePage, appliedKey);
      if (hitFound) {
        stopHighlightFocusTimer();
        return;
      }
      highlightFocusAttemptsRef.current += 1;
      if (highlightFocusAttemptsRef.current >= maxAttempts) {
        stopHighlightFocusTimer();
        return;
      }
      highlightFocusTimerRef.current = window.setTimeout(tick, 140);
    };
    highlightFocusTimerRef.current = window.setTimeout(tick, 140);
  };

  useEffect(() => {
    setDocReady(false);
    setNumPages(1);
    setCurrentPage(requestedPageSafe);
    setActiveTargetPage(requestedPageSafe);
    stopHighlightFocusTimer();
    highlightFocusAttemptsRef.current = 0;
    appliedHighlightKeyRef.current = "";
    pageRefs.current = {};
    pageSurfaceRefs.current = {};
    overlayRectsByPageRef.current = {};
    setOverlayRectsByPage({});
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [fileUrl, requestedPageSafe]);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const updateWidth = () => {
      const nextWidth = Math.max(240, Math.floor(container.clientWidth) - 24);
      setPageWidth(nextWidth);
    };
    updateWidth();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", updateWidth);
      return () => window.removeEventListener("resize", updateWidth);
    }
    const observer = new ResizeObserver(updateWidth);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!docReady) return;
    const target = clampPage(requestedPageSafe);
    setActiveTargetPage(target);
    const timer = window.setTimeout(() => {
      scrollToPage(target, "smooth");
      scheduleHighlightFocus(target);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [docReady, numPages, requestedPageSafe, searchCandidates, highlightText, externalOverlayRects]);

  useEffect(() => {
    return () => {
      stopHighlightFocusTimer();
      clearHighlights();
    };
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !docReady) return;

    const onScroll = () => {
      if (syncLockRef.current) return;
      const containerRect = container.getBoundingClientRect();
      let bestPage = currentPage;
      let bestDistance = Number.POSITIVE_INFINITY;
      for (let pageNumber = 1; pageNumber <= numPages; pageNumber += 1) {
        const node = pageRefs.current[pageNumber];
        if (!node) continue;
        const rect = node.getBoundingClientRect();
        const distance = Math.abs(rect.top - containerRect.top);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestPage = pageNumber;
        }
      }
      if (bestPage !== currentPage) {
        setCurrentPage(bestPage);
      }
    };

    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, [currentPage, docReady, numPages]);

  return (
    <div className="citation-pdf rounded-xl border border-black/[0.08] bg-white overflow-hidden">
      <div className="h-8 px-2.5 flex items-center justify-between border-b border-black/[0.06] bg-[#f8f8fa]">
        <button
          type="button"
          onClick={() => {
            const next = clampPage(currentPage - 1);
            setActiveTargetPage(next);
            scrollToPage(next, "smooth");
            scheduleHighlightFocus(next);
          }}
          disabled={currentPage <= 1}
          className="p-1 rounded-md text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Previous page"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        <p className="text-[10px] text-[#6e6e73]">
          Page {currentPage} of {numPages}
        </p>
        <button
          type="button"
          onClick={() => {
            const next = clampPage(currentPage + 1);
            setActiveTargetPage(next);
            scrollToPage(next, "smooth");
            scheduleHighlightFocus(next);
          }}
          disabled={currentPage >= numPages}
          className="p-1 rounded-md text-[#6e6e73] hover:bg-black/[0.05] disabled:opacity-30"
          aria-label="Next page"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>

      <div ref={scrollRef} className="h-[420px] overflow-y-auto overflow-x-hidden bg-[#f2f2f7] p-2">
        <Document
          file={fileUrl}
          onLoadSuccess={({ numPages: loadedPages }) => {
            const safePages = loadedPages > 0 ? loadedPages : 1;
            setNumPages(safePages);
            setDocReady(true);
            const target = Math.min(Math.max(1, activeTargetPage), safePages);
            setCurrentPage(target);
          }}
          loading={
            <div className="h-[240px] flex items-center justify-center text-[#6e6e73]">
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          }
          error={
            <div className="h-[240px] flex items-center justify-center px-4 text-center text-[11px] text-[#6e6e73]">
              Unable to render PDF preview.
            </div>
          }
        >
          {Array.from({ length: numPages }, (_, idx) => idx + 1).map((pageNumber) => (
            <div
              key={`page-${pageNumber}`}
              ref={(node) => {
                pageRefs.current[pageNumber] = node;
              }}
              className={`mb-3 rounded-lg border ${
                pageNumber === currentPage
                  ? "border-[#1d1d1f]/25 ring-2 ring-[#1d1d1f]/10"
                  : "border-black/[0.08]"
              } bg-white p-1`}
            >
              <div className="px-2 py-1 text-[10px] text-[#6e6e73]">Page {pageNumber}</div>
              <div
                ref={(node) => {
                  pageSurfaceRefs.current[pageNumber] = node;
                }}
                className="citation-pdf-page-surface relative mx-auto w-fit"
              >
                <Page
                  pageNumber={pageNumber}
                  width={pageWidth}
                  renderAnnotationLayer
                  renderTextLayer
                  onRenderTextLayerSuccess={() => {
                    if (pageNumber === activeTargetPage && !overlayRectsByPage[pageNumber]?.length) {
                      scheduleHighlightFocus(pageNumber);
                    }
                  }}
                />
                <div className="citation-pdf-overlay" aria-hidden>
                  {(overlayRectsByPage[pageNumber] || []).map((rect, index) => (
                    <div
                      key={`${pageNumber}:${index}:${Math.round(rect.leftPct * 10)}:${Math.round(rect.topPct * 10)}`}
                      className="citation-pdf-overlay-rect"
                      style={{
                        left: `${rect.leftPct}%`,
                        top: `${rect.topPct}%`,
                        width: `${rect.widthPct}%`,
                        height: `${rect.heightPct}%`,
                      }}
                    />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}
