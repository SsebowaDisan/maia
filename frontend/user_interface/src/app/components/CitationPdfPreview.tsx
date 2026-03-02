import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
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
}

function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeWhitespace(input: string): string {
  return String(input || "").replace(/\s+/g, " ").trim();
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

function buildExactPhrases(text: string): string[] {
  const normalized = normalizeWhitespace(text).toLowerCase();
  if (!normalized) {
    return [];
  }
  const sentenceParts = normalized
    .split(/(?<=[.!?])\s+|[\n\r]+/)
    .map((part) => normalizeWhitespace(part))
    .filter((part) => part.length >= 12 && part.length <= 320);
  const candidates = [normalized, ...sentenceParts].filter(
    (part) => part.length >= 12 && part.length <= 320,
  );
  return Array.from(new Set(candidates)).slice(0, 10);
}

function buildPhraseFragments(phrases: string[]): string[] {
  const fragments: string[] = [];
  for (const phrase of phrases) {
    const words = phrase.split(" ").filter(Boolean);
    if (words.length < 4) {
      continue;
    }
    const windowSize = Math.min(8, words.length);
    for (let idx = 0; idx <= words.length - windowSize; idx += 1) {
      const fragment = words.slice(idx, idx + windowSize).join(" ").trim();
      if (fragment.length >= 16) {
        fragments.push(fragment);
      }
      if (fragments.length >= 28) {
        return Array.from(new Set(fragments));
      }
    }
  }
  return Array.from(new Set(fragments));
}

function applyHighlights(text: string, terms: string[]): { html: string; matched: boolean } {
  if (!text || !terms.length) {
    return { html: text, matched: false };
  }
  let highlighted = text;
  let matched = false;
  for (const term of terms) {
    const regex = new RegExp(`(${escapeRegExp(term)})`, "gi");
    if (regex.test(highlighted)) {
      regex.lastIndex = 0;
      highlighted = highlighted.replace(
        regex,
        `<mark class="citation-pdf-hit">$1</mark>`,
      );
      matched = true;
    }
  }
  return { html: highlighted, matched };
}

export function CitationPdfPreview({ fileUrl, page, highlightText }: CitationPdfPreviewProps) {
  const requestedPageSafe = parsePageNumber(page);
  const [numPages, setNumPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(requestedPageSafe);
  const [pageWidth, setPageWidth] = useState(300);
  const [docReady, setDocReady] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const syncLockRef = useRef(false);
  const highlightFocusAttemptsRef = useRef(0);
  const highlightFocusTimerRef = useRef<number | null>(null);
  const [activeTargetPage, setActiveTargetPage] = useState(
    requestedPageSafe,
  );
  const highlightPhrases = useMemo(() => buildExactPhrases(highlightText), [highlightText]);
  const highlightFragments = useMemo(
    () => buildPhraseFragments(highlightPhrases),
    [highlightPhrases],
  );

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

  const tryFocusHighlight = (targetPage: number) => {
    const safePage = clampPage(targetPage);
    const target = pageRefs.current[safePage];
    if (!target) {
      return false;
    }
    const hit = target.querySelector<HTMLElement>("mark.citation-pdf-hit");
    if (!hit) {
      return false;
    }
    syncLockRef.current = true;
    hit.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    setCurrentPage(safePage);
    window.setTimeout(() => {
      syncLockRef.current = false;
    }, 240);
    return true;
  };

  const scheduleHighlightFocus = (targetPage: number) => {
    stopHighlightFocusTimer();
    highlightFocusAttemptsRef.current = 0;
    const maxAttempts = 12;
    const tick = () => {
      const hitFound = tryFocusHighlight(targetPage);
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

  const buildCustomTextRenderer = (pageNumber: number) => ({ str }: { str: string }) => {
    if (!str || pageNumber !== activeTargetPage) {
      return str;
    }
    const exactMatch = applyHighlights(str, highlightPhrases);
    if (exactMatch.matched) {
      return exactMatch.html;
    }
    return applyHighlights(str, highlightFragments).html;
  };

  useEffect(() => {
    setDocReady(false);
    setNumPages(1);
    setCurrentPage(requestedPageSafe);
    setActiveTargetPage(requestedPageSafe);
    stopHighlightFocusTimer();
    highlightFocusAttemptsRef.current = 0;
    pageRefs.current = {};
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
      if (highlightPhrases.length || highlightFragments.length) {
        scheduleHighlightFocus(target);
      }
    }, 80);
    return () => window.clearTimeout(timer);
  }, [docReady, numPages, requestedPageSafe, highlightPhrases, highlightFragments]);

  useEffect(() => {
    return () => {
      stopHighlightFocusTimer();
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
              <Page
                pageNumber={pageNumber}
                width={pageWidth}
                renderAnnotationLayer
                renderTextLayer
                customTextRenderer={buildCustomTextRenderer(pageNumber)}
              />
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}
