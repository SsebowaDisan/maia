import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import type { CitationHighlightBox } from "../types";
import {
  buildOverlayPath,
  buildOverlayRectsForRange,
  buildSearchCandidates,
  collectSpanSegments,
  findHighlightRange,
  normalizeExternalOverlayRects,
  normalizeSearchText,
  overlayRectsEqual,
  parsePageNumber,
  type OverlayRect,
} from "./citationPdfHighlight";
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
  viewerHeight?: number;
  initialZoom?: number;
  onZoomChange?: (zoom: number) => void;
  onPageChange?: (page: number) => void;
}

type PageRenderState = "loading" | "ready" | "error" | "stalled";

function buildPdfPageUrl(fileUrl: string, pageNumber: number): string {
  try {
    const base = typeof window !== "undefined" ? window.location.origin : "http://127.0.0.1";
    const resolved = new URL(fileUrl, base);
    resolved.hash = `page=${Math.max(1, Math.round(pageNumber))}`;
    return resolved.toString();
  } catch {
    return fileUrl;
  }
}

function PageLoadingState() {
  return (
    <div className="flex min-h-[440px] w-full min-w-[240px] items-center justify-center rounded-[14px] bg-[#fbfbfd] text-[#6e6e73]">
      <div className="flex flex-col items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        <p className="text-[11px] font-medium">Rendering page preview</p>
      </div>
    </div>
  );
}

function PageFallbackState({
  fileUrl,
  pageNumber,
  stalled = false,
}: {
  fileUrl: string;
  pageNumber: number;
  stalled?: boolean;
}) {
  return (
    <div className="flex min-h-[440px] w-full min-w-[240px] items-center justify-center rounded-[14px] bg-[#fbfbfd] px-6 text-center">
      <div className="max-w-[280px] space-y-3">
        <p className="text-[12px] font-medium text-[#1d1d1f]">
          {stalled ? "Page preview is taking too long." : "Unable to render this PDF page."}
        </p>
        <p className="text-[11px] leading-5 text-[#6e6e73]">
          Open the document directly if you need the full page immediately.
        </p>
        <a
          href={buildPdfPageUrl(fileUrl, pageNumber)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-3 py-1.5 text-[11px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f3f3f5]"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open document
        </a>
      </div>
    </div>
  );
}

export function CitationPdfPreview({
  fileUrl,
  page,
  highlightText,
  highlightQuery,
  highlightBoxes,
  viewerHeight = 420,
  initialZoom = 1,
  onZoomChange,
  onPageChange,
}: CitationPdfPreviewProps) {
  const effectiveViewerHeight = Math.max(220, Math.min(1200, Math.round(Number(viewerHeight) || 420)));
  const requestedPageSafe = parsePageNumber(page);
  const [numPages, setNumPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(requestedPageSafe);
  const [pageWidth, setPageWidth] = useState(300);
  const [zoomLevel, setZoomLevel] = useState(() => {
    const parsed = Number(initialZoom);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return 1;
    }
    return Math.max(0.75, Math.min(2.25, parsed));
  });
  const [docReady, setDocReady] = useState(false);
  const [pageRenderState, setPageRenderState] = useState<Record<number, PageRenderState>>({});
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
    setPageRenderState({});
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
    setPageRenderState({});
  }, [fileUrl, pageWidth, zoomLevel]);

  useEffect(() => {
    setZoomLevel(() => {
      const parsed = Number(initialZoom);
      if (!Number.isFinite(parsed) || parsed <= 0) {
        return 1;
      }
      return Math.max(0.75, Math.min(2.25, parsed));
    });
  }, [fileUrl, initialZoom]);

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
    if (!docReady) {
      return;
    }
    const timers: number[] = [];
    for (let pageNumber = 1; pageNumber <= numPages; pageNumber += 1) {
      const state = pageRenderState[pageNumber];
      if (state === "ready" || state === "error" || state === "stalled") {
        continue;
      }
      timers.push(
        window.setTimeout(() => {
          setPageRenderState((previous) => {
            const current = previous[pageNumber];
            if (current === "ready" || current === "error") {
              return previous;
            }
            return {
              ...previous,
              [pageNumber]: "stalled",
            };
          });
        }, 9000),
      );
    }
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [docReady, numPages, pageRenderState]);

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

  useEffect(() => {
    if (!docReady) {
      return;
    }
    onPageChange?.(currentPage);
  }, [currentPage, docReady, onPageChange]);

  return (
    <div className="citation-pdf rounded-xl border border-black/[0.08] bg-white overflow-hidden">
      <div className="h-8 px-2.5 flex items-center justify-between border-b border-black/[0.06] bg-[#f8f8fa]">
        <div className="flex items-center gap-1">
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
          <button
            type="button"
            onClick={() => {
              setZoomLevel((previous) => {
                const next = Math.max(0.75, Number((previous - 0.2).toFixed(2)));
                onZoomChange?.(next);
                return next;
              });
            }}
            className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
            aria-label="Zoom out"
          >
            -
          </button>
        </div>
        <p className="text-[10px] text-[#6e6e73]">
          Page {currentPage} of {numPages} | {Math.round(zoomLevel * 100)}%
        </p>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setZoomLevel((previous) => {
                const next = Math.min(2.25, Number((previous + 0.2).toFixed(2)));
                onZoomChange?.(next);
                return next;
              });
            }}
            className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => {
              setZoomLevel(1);
              onZoomChange?.(1);
            }}
            className="rounded-md border border-black/[0.08] px-1.5 py-0.5 text-[10px] text-[#4c4c50] hover:bg-black/[0.03]"
            aria-label="Reset zoom"
          >
            1x
          </button>
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
      </div>

      <div
        ref={scrollRef}
        className="overflow-y-auto overflow-x-hidden bg-[#f2f2f7] p-2"
        style={{ height: `${effectiveViewerHeight}px` }}
      >
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
                  width={Math.round(pageWidth * zoomLevel)}
                  renderAnnotationLayer
                  renderTextLayer
                  loading={<PageLoadingState />}
                  error={<PageFallbackState fileUrl={fileUrl} pageNumber={pageNumber} />}
                  onLoadSuccess={() => {
                    setPageRenderState((previous) => {
                      if (previous[pageNumber] === "ready") {
                        return previous;
                      }
                      return {
                        ...previous,
                        [pageNumber]: "loading",
                      };
                    });
                  }}
                  onRenderSuccess={() => {
                    setPageRenderState((previous) => {
                      if (previous[pageNumber] === "ready") {
                        return previous;
                      }
                      return {
                        ...previous,
                        [pageNumber]: "ready",
                      };
                    });
                  }}
                  onRenderError={() => {
                    setPageRenderState((previous) => ({
                      ...previous,
                      [pageNumber]: "error",
                    }));
                  }}
                  onRenderTextLayerSuccess={() => {
                    if (pageNumber === activeTargetPage && !overlayRectsByPage[pageNumber]?.length) {
                      scheduleHighlightFocus(pageNumber);
                    }
                  }}
                />
                {pageRenderState[pageNumber] === "stalled" ? (
                  <div className="absolute inset-0">
                    <PageFallbackState fileUrl={fileUrl} pageNumber={pageNumber} stalled />
                  </div>
                ) : null}
                <div className="citation-pdf-overlay" aria-hidden>
                  {overlayRectsByPage[pageNumber]?.length ? (
                    <svg
                      className={`citation-pdf-overlay-svg ${pageNumber === activeTargetPage ? "is-active" : ""}`}
                      viewBox="0 0 100 100"
                      preserveAspectRatio="none"
                    >
                      <path
                        className="citation-pdf-overlay-path"
                        d={buildOverlayPath(overlayRectsByPage[pageNumber] || [])}
                      />
                    </svg>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}

