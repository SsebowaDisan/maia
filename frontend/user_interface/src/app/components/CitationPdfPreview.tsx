import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import type { CitationEvidenceUnit, CitationHighlightBox } from "../types";
import {
  buildOverlayPath,
  buildSearchCandidates,
  normalizeExternalOverlayRects,
  normalizeSearchText,
  overlayRectsEqual,
  parsePageNumber,
  type OverlayRect,
} from "./citationPdfHighlight";
import {
  PageFallbackState,
  PageLoadingState,
  PdfPreviewToolbar,
} from "./CitationPdfPreviewChrome";
import { tryFocusHighlight } from "./citationPdfPreviewFocus";
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
  charStart?: number;
  charEnd?: number;
  highlightBoxes?: CitationHighlightBox[];
  evidenceUnits?: CitationEvidenceUnit[];
  viewerHeight?: number;
  initialZoom?: number;
  onZoomChange?: (zoom: number) => void;
  onPageChange?: (page: number) => void;
}

type PageRenderState = "loading" | "ready" | "error" | "stalled";

export function CitationPdfPreview({
  fileUrl,
  page,
  highlightText,
  highlightQuery,
  charStart,
  charEnd,
  highlightBoxes,
  evidenceUnits,
  viewerHeight = 420,
  initialZoom = 1,
  onZoomChange,
  onPageChange,
}: CitationPdfPreviewProps) {
  const effectiveViewerHeight = Math.max(360, Math.min(1200, Math.round(Number(viewerHeight) || 560)));
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
    const primary = buildSearchCandidates(highlightText);
    const secondary = buildSearchCandidates(highlightQuery || "");
    const merged = [...primary, ...secondary];
    return Array.from(new Set(merged)).slice(0, 80);
  }, [highlightQuery, highlightText]);
  const externalOverlayRects = useMemo(
    () => normalizeExternalOverlayRects(highlightBoxes),
    [highlightBoxes],
  );
  const evidenceUnitsKey = useMemo(
    () =>
      (evidenceUnits || [])
        .map((unit) => {
          const boxes = (unit.highlightBoxes || [])
            .map((item) => `${item.x},${item.y},${item.width},${item.height}`)
            .join("|");
          return `${unit.charStart ?? ""}:${unit.charEnd ?? ""}:${String(unit.text || "").slice(0, 64)}:${boxes}`;
        })
        .join("~"),
    [evidenceUnits],
  );
  const highlightRequestKey = useMemo(() => {
    const normalizedEvidence = normalizeSearchText(highlightText).slice(0, 220);
    const normalizedQuery = normalizeSearchText(highlightQuery || "").slice(0, 220);
    const overlayKey = externalOverlayRects
      .map((item) => `${item.leftPct},${item.topPct},${item.widthPct},${item.heightPct}`)
      .join("|");
    return `${fileUrl}::${requestedPageSafe}::${normalizedEvidence}::${normalizedQuery}::${overlayKey}::${evidenceUnitsKey}`;
  }, [evidenceUnitsKey, externalOverlayRects, fileUrl, highlightQuery, highlightText, requestedPageSafe]);

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
    const maxAttempts = externalOverlayRects.length ? 10 : 25;
    const TICK_MS = 80;
    const tick = () => {
      const hitFound = tryFocusHighlight({
        targetPage: safePage,
        appliedKey,
        charStart,
        charEnd,
        evidenceUnits,
        searchCandidates,
        externalOverlayRects,
        pageSurfaceRefs,
        overlayRectsByPageRef,
        appliedHighlightKeyRef,
        clampPage,
        applyOverlayRects,
        scrollToOverlayRect,
      });
      if (hitFound) {
        stopHighlightFocusTimer();
        return;
      }
      highlightFocusAttemptsRef.current += 1;
      if (highlightFocusAttemptsRef.current >= maxAttempts) {
        stopHighlightFocusTimer();
        return;
      }
      highlightFocusTimerRef.current = window.setTimeout(tick, TICK_MS);
    };
    highlightFocusTimerRef.current = window.setTimeout(tick, TICK_MS);
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
  }, [docReady, numPages, requestedPageSafe, searchCandidates, highlightText, externalOverlayRects, evidenceUnitsKey]);

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
        }, 4000),
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
    <div className="citation-pdf overflow-hidden rounded-xl border border-black/[0.08] bg-white">
      <PdfPreviewToolbar
        currentPage={currentPage}
        numPages={numPages}
        zoomLevel={zoomLevel}
        onPreviousPage={() => {
          const next = clampPage(currentPage - 1);
          setActiveTargetPage(next);
          scrollToPage(next, "smooth");
          scheduleHighlightFocus(next);
        }}
        onNextPage={() => {
          const next = clampPage(currentPage + 1);
          setActiveTargetPage(next);
          scrollToPage(next, "smooth");
          scheduleHighlightFocus(next);
        }}
        onZoomOut={() => {
          setZoomLevel((previous) => {
            const next = Math.max(0.75, Number((previous - 0.2).toFixed(2)));
            onZoomChange?.(next);
            return next;
          });
        }}
        onZoomIn={() => {
          setZoomLevel((previous) => {
            const next = Math.min(2.25, Number((previous + 0.2).toFixed(2)));
            onZoomChange?.(next);
            return next;
          });
        }}
        onResetZoom={() => {
          setZoomLevel(1);
          onZoomChange?.(1);
        }}
      />

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

