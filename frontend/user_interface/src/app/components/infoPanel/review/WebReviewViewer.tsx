import { Globe, AlignLeft } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { WebReviewSource } from "./webReviewContent";
import { findBestParagraphIndex, resolveWebReviewParagraphs } from "./webReviewContent";

type WebReviewViewerProps = {
  sourceTitle: string;
  sourceUrl: string;
  reviewQuery: string;
  focusText: string;
  focusSelector?: string;
  reviewSource: WebReviewSource | null;
  viewerHeight: number;
};

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function tokenizeQuery(value: string): string[] {
  return String(value || "")
    .toLowerCase()
    .split(/\s+/)
    .map((row) => row.trim())
    .filter((row) => row.length >= 3)
    .slice(0, 6);
}

function renderHighlightedText(text: string, query: string): ReactNode {
  const normalizedText = String(text || "");
  const tokens = tokenizeQuery(query);
  if (!tokens.length) {
    return normalizedText;
  }
  const pattern = new RegExp(`(${tokens.map((token) => escapeRegExp(token)).join("|")})`, "ig");
  const parts = normalizedText.split(pattern);
  if (parts.length <= 1) {
    return normalizedText;
  }
  return parts.map((part, index) => {
    const lowered = part.toLowerCase();
    if (tokens.includes(lowered)) {
      return (
        <mark key={`highlight-${index}`} className="rounded bg-[#ffe792] px-0.5 text-[#1d1d1f]">
          {part}
        </mark>
      );
    }
    return <span key={`text-${index}`}>{part}</span>;
  });
}

function WebReviewViewer({
  sourceTitle,
  sourceUrl,
  reviewQuery,
  focusText,
  focusSelector = "",
  reviewSource,
  viewerHeight,
}: WebReviewViewerProps) {
  const paragraphs = useMemo(
    () => resolveWebReviewParagraphs(reviewSource, 24),
    [reviewSource],
  );
  const hasExtractedText = paragraphs.length > 0;
  const activeParagraphIndex = useMemo(
    () => findBestParagraphIndex(paragraphs, focusText || reviewQuery),
    [focusText, paragraphs, reviewQuery],
  );
  const paragraphRefs = useRef<Array<HTMLParagraphElement | null>>([]);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const [viewMode, setViewMode] = useState<"page" | "text">("page");
  const [iframeLoaded, setIframeLoaded] = useState(false);

  useEffect(() => {
    setIframeLoaded(false);
    setViewMode(hasExtractedText ? "text" : "page");
  }, [hasExtractedText, sourceUrl]);

  useEffect(() => {
    if (viewMode !== "text") return;
    const node = paragraphRefs.current[activeParagraphIndex];
    if (!node) return;
    node.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeParagraphIndex, paragraphs, viewMode]);

  // Scroll the iframe to the highlighted citation text.
  // Uses multiple strategies with retries to ensure the highlight is found.
  const scrollToHighlight = useCallback(() => {
    const iframeDoc =
      iframeRef.current?.contentDocument ??
      iframeRef.current?.contentWindow?.document;
    if (!iframeDoc) return false;

    let target: HTMLElement | null = null;

    // Strategy 1: Exact CSS selector (provided by the agent)
    if (focusSelector) {
      try {
        target = iframeDoc.querySelector(focusSelector) as HTMLElement | null;
      } catch { /* invalid selector */ }
    }

    // Strategy 2: Backend-injected <mark> highlight
    if (!target) {
      target = iframeDoc.querySelector("mark.maia-citation-highlight") as HTMLElement | null;
    }

    // Strategy 3: Any <mark> element on the page
    if (!target) {
      target = iframeDoc.querySelector("mark") as HTMLElement | null;
    }

    // Strategy 4: Text content search — find a paragraph containing the focus text
    if (!target && focusText && focusText.length >= 10) {
      const searchTerms = focusText.toLowerCase().split(/\s+/).filter((w) => w.length >= 4).slice(0, 5);
      if (searchTerms.length >= 2) {
        const paragraphs = iframeDoc.querySelectorAll("p, li, td, h1, h2, h3, h4, blockquote, span");
        for (const el of paragraphs) {
          const text = (el as HTMLElement).innerText?.toLowerCase() || "";
          const matches = searchTerms.filter((term) => text.includes(term)).length;
          if (matches >= Math.min(3, searchTerms.length)) {
            target = el as HTMLElement;
            // Add a visual highlight to the found element
            target.style.outline = "3px solid #fbbf24";
            target.style.outlineOffset = "2px";
            target.style.borderRadius = "4px";
            break;
          }
        }
      }
    }

    if (target) {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
      return true;
    }
    return false;
  }, [focusSelector, focusText]);

  // After iframe loads, retry scrolling with increasing delays until highlight is found
  const handleIframeLoad = useCallback(() => {
    setIframeLoaded(true);
    let attempts = 0;
    const maxAttempts = 8;
    const tryScroll = () => {
      attempts += 1;
      const found = scrollToHighlight();
      if (!found && attempts < maxAttempts) {
        setTimeout(tryScroll, attempts < 3 ? 200 : 500);
      }
    };
    setTimeout(tryScroll, 150);
  }, [scrollToHighlight]);

  // Re-scroll when focus changes while page is already loaded
  useEffect(() => {
    if (!iframeLoaded) return;
    const t = setTimeout(scrollToHighlight, 100);
    return () => clearTimeout(t);
  }, [focusText, focusSelector, iframeLoaded, scrollToHighlight]);

  const effectiveHeight = Math.max(360, viewerHeight);
  const hasUrl = Boolean(sourceUrl);

  // Route through the backend proxy so X-Frame-Options never blocks rendering.
  // The proxy fetches server-side, injects citation highlight, and rewrites relative URLs.
  const highlightParam = focusText || reviewQuery;
  const previewSrc = hasUrl
    ? `/api/web/preview?url=${encodeURIComponent(sourceUrl)}${
        highlightParam
          ? `&highlight=${encodeURIComponent(highlightParam)}&claim=${encodeURIComponent(reviewQuery)}&question=${encodeURIComponent(reviewQuery)}`
          : ""
      }&viewport=desktop&highlight_strategy=heuristic`
    : "";

  return (
    <div className="overflow-hidden rounded-xl border border-black/[0.06] bg-[#f8f8fb]">
      {/* Toolbar */}
      {hasUrl && (
        <div className="flex items-center justify-between gap-2 border-b border-black/[0.06] bg-white px-3 py-1.5">
          <div className="flex min-w-0 items-center gap-1.5 text-[11px] text-[#6e6e73]">
            <Globe className="h-3 w-3 shrink-0" />
            <span className="truncate">{(() => { try { return new URL(sourceUrl).hostname.replace(/^www\./, ""); } catch { return sourceUrl; } })()}</span>
          </div>
          {hasExtractedText && (
            <div className="flex shrink-0 items-center gap-0.5 rounded-lg border border-black/[0.08] bg-[#f5f5f7] p-0.5">
              <button
                type="button"
                onClick={() => setViewMode("page")}
                title="Show webpage"
                className={`flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] transition-colors ${
                  viewMode === "page"
                    ? "bg-white text-[#1d1d1f] shadow-sm"
                    : "text-[#6e6e73] hover:text-[#3a3a3c]"
                }`}
              >
                <Globe className="h-3 w-3" />
                Page
              </button>
              <button
                type="button"
                onClick={() => setViewMode("text")}
                title="Show extracted text"
                className={`flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] transition-colors ${
                  viewMode === "text"
                    ? "bg-white text-[#1d1d1f] shadow-sm"
                    : "text-[#6e6e73] hover:text-[#3a3a3c]"
                }`}
              >
                <AlignLeft className="h-3 w-3" />
                Text
              </button>
            </div>
          )}
        </div>
      )}

      {/* Iframe view */}
      {viewMode === "page" && hasUrl && (
        <div className="relative" style={{ height: `${effectiveHeight}px` }}>
          {!iframeLoaded && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#f8f8fb]">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#d2d2d7] border-t-[#6e6e73]" />
              <p className="text-[11px] text-[#8e8e93]">Loading page…</p>
            </div>
          )}
          <iframe
            ref={iframeRef}
            key={previewSrc}
            src={previewSrc}
            title={sourceTitle || "Source page"}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
            loading="eager"
            className={`h-full w-full border-0 bg-white transition-opacity duration-200 ${iframeLoaded ? "opacity-100" : "opacity-0"}`}
            onLoad={handleIframeLoad}
          />
          {iframeLoaded && (
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-[#f8f8fb]/60 to-transparent" />
          )}
        </div>
      )}

      {/* Extracted text view */}
      {(viewMode === "text" || (!hasUrl && hasExtractedText)) && (
        <div style={{ maxHeight: `${effectiveHeight}px`, overflowY: "auto" }}>
          {paragraphs.length ? (
            <div className="space-y-0 divide-y divide-black/[0.04] px-3 py-2">
              {paragraphs.map((paragraph, index) => (
                <p
                  key={`paragraph-${index}`}
                  ref={(node) => { paragraphRefs.current[index] = node; }}
                  className={`py-2 text-[12px] leading-[1.6] text-[#2f2f33] transition-colors ${
                    index === activeParagraphIndex
                      ? "rounded-md bg-[#fff3c4] px-2 ring-1 ring-[#f2d57c]"
                      : "px-1"
                  }`}
                >
                  {renderHighlightedText(paragraph, reviewQuery)}
                </p>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-2 px-3 py-4 text-[12px] text-[#6e6e73]">
              <Globe className="h-4 w-4 shrink-0 text-[#8e8e93]" />
              No readable passage was extracted for this citation yet.
            </div>
          )}
        </div>
      )}

      {/* No URL, no text */}
      {!hasUrl && !hasExtractedText && (
        <div className="flex items-center gap-2 px-3 py-4 text-[12px] text-[#6e6e73]">
          <Globe className="h-4 w-4 shrink-0 text-[#8e8e93]" />
          No readable passage was extracted for this citation yet.
        </div>
      )}
    </div>
  );
}

export { WebReviewViewer };
